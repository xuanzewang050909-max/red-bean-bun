"""Independently recompute Q4 masks with dense OpenCV filters, no Q4 algorithm import."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from skimage.morphology import skeletonize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_q1_bilateral import require, sha, write_json

DIRS = ((0,1),(1,0),(1,1),(1,-1))


def kernel_sum(im, offsets, border=cv2.BORDER_CONSTANT):
    r = max(max(abs(y),abs(x)) for y,x in offsets)
    k = np.zeros((2*r+1,2*r+1),np.int16)
    for y,x in offsets:
        k[r+y,r+x] += 1
    return cv2.filter2D(im.astype(np.uint8), cv2.CV_16S, k, borderType=border)


def pairs(im):
    result=[]
    for dy,dx in DIRS:
        center=kernel_sum(im,[(t*dy,t*dx) for t in range(-4,5)],cv2.BORDER_REPLICATE)
        row=[]
        for d in range(1,6):
            l=kernel_sum(im,[(t*dy-d*dx,t*dx+d*dy) for t in range(-4,5)],cv2.BORDER_REPLICATE)-center
            r=kernel_sum(im,[(t*dy+d*dx,t*dx-d*dy) for t in range(-4,5)],cv2.BORDER_REPLICATE)-center
            row.append((l.astype(np.int32),r.astype(np.int32)))
        result.append(row)
    return result


def supports(evidence,ratio,margin):
    return [np.logical_or.reduce([(l>=9*margin)&(r>=9*margin)&(l<=ratio*r)&(r<=ratio*l)
                                  for l,r in row]) for row in evidence]


def segmentation(response,fov):
    cross=cv2.getStructuringElement(cv2.MORPH_CROSS,(3,3))
    initial=((response>=28)&fov).astype(np.uint8)
    close=cv2.erode(cv2.dilate(initial,cross,borderType=cv2.BORDER_CONSTANT,borderValue=0),
                   cross,borderType=cv2.BORDER_CONSTANT,borderValue=0).astype(bool)
    count=kernel_sum(close,[(y,x) for y in (-1,0,1) for x in (-1,0,1)],cv2.BORDER_REPLICATE)
    return close&(count>=2)&fov


def bridges(seed,weak,fov,gmax):
    final=seed.copy()
    for (dy,dx),support in zip(DIRS,weak):
        valid=support&fov
        for gap in range(1,gmax+1):
            n=gap+1
            endpoints=kernel_sum(seed,[(0,0),(n*dy,n*dx)])==2
            interiors=kernel_sum(seed,[(t*dy,t*dx) for t in range(1,n)])==0
            allsupported=kernel_sum(valid,[(t*dy,t*dx) for t in range(n+1)])==n+1
            anchors=endpoints&interiors&allsupported
            projected=kernel_sum(anchors,[(-t*dy,-t*dx) for t in range(1,n)])>0
            final|=projected
    return final&fov


def ridge(evidence,fov,c):
    seeds=[];grown=[]
    for (dy,dx),row in zip(DIRS,evidence):
        signed=np.maximum.reduce([np.where((l>0)&(r>0)&(l<=c['ratio']*r)&(r<=c['ratio']*l),
                                           np.minimum(l,r),0) for l,r in row])
        score=np.minimum(255,(signed*c['gain']+4)//9)
        seed=(score>=28)&fov;current=seed.copy();weak=(score>=c['low'])&fov
        for _ in range(c['steps']):
            neighbour=kernel_sum(current,[(dy,dx),(-dy,-dx)])>0
            current|=neighbour&weak
        seeds.append(seed);grown.append(current)
    return segmentation(np.logical_or.reduce(grown).astype(np.uint8)*255,fov),segmentation(np.logical_or.reduce(seeds).astype(np.uint8)*255,fov)


def independent_regions(filtered,fov,truth):
    core=(filtered>=192)&fov
    band=cv2.dilate(core.astype(np.uint8),np.ones((15,15),np.uint8),borderType=cv2.BORDER_CONSTANT,borderValue=0).astype(bool)&~core&fov
    s5=kernel_sum(truth,[(y,x) for y in range(-2,3) for x in range(-2,3)],cv2.BORDER_REPLICATE)
    s3=kernel_sum(truth,[(y,x) for y in range(-1,2) for x in range(-1,2)],cv2.BORDER_REPLICATE)
    inner=cv2.erode(fov.astype(np.uint8),np.ones((15,15),np.uint8),borderType=cv2.BORDER_CONSTANT,borderValue=0).astype(bool)
    return {'fov':fov,'full_image':np.ones_like(fov),'bright_core':core,'bright_band':band,
            'thin_label_proxy':truth&fov&(s5<=10)&(s3<=6),'fov_edge':fov&~inner}


def main(candidate_oracle=None):
    p=argparse.ArgumentParser();p.add_argument('experiment',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    require(not a.output.exists(),'Preserve earlier verification')
    report=json.loads((a.experiment/'training_report.json').read_text(encoding='utf-8'))
    prov=json.loads((a.experiment/'provenance.json').read_text(encoding='utf-8'));proto=prov['protocol']
    matched=0;pixels=0;regions_checked=0
    for rec in report['array_records']:
        path=a.experiment/rec['file'];require(sha(path)==rec['sha256'],'NPZ changed')
        image_id,side=rec['file'].split('_')[:2]
        with np.load(path,allow_pickle=False) as z:
            fov=z['fov'];truth=z['truth_AH'];response=z['response'];ev={k:pairs(z[k]) for k in ('enhanced','filtered')}
            plain=np.logical_or.reduce([(l>=9)&(r>=9) for row in ev['enhanced'] for l,r in row])
            c2=segmentation(np.where(plain,response,np.maximum(0,response.astype(np.int16)-28)),fov)
            masks={'A':segmentation(response,fov),'C2':c2}
            seeds=dict(masks)
            weak=supports(ev['filtered'],4,1)
            extra_cache={}
            for c in proto['candidates']:
                if candidate_oracle is not None:
                    masks[c['id']],seeds[c['id']]=candidate_oracle(z,fov,c2,extra_cache,c)
                    continue
                if proto['protocol']=='Q4_RIDGE_R2':
                    masks[c['id']],seeds[c['id']]=ridge(ev['filtered'],fov,c)
                    continue
                if c['feature']=='C2':seed=c2
                else:
                    support=np.logical_or.reduce(supports(ev[c['feature']],c['ratio'],c['margin']))
                    seed=segmentation(np.where(support,response,np.maximum(0,response.astype(np.int16)-28)),fov)
                masks[c['id']]=bridges(seed,weak,fov,c['gap'])
                seeds[c['id']]=seed
            regions=independent_regions(z['filtered'],fov,truth)
            for name,mask in masks.items():
                saved=np.unpackbits(z[name])[:mask.size].reshape(mask.shape).astype(bool)
                require(np.array_equal(mask,saved),'Independent mask differs: '+rec['file']+name)
                require(hashlib.sha256(mask.astype(np.uint8).tobytes()).hexdigest()==rec['mask_sha256'][name],'Hash differs')
                entry=report['scores'][name][side]['per_image'][image_id]
                added=mask&~seeds[name]&fov
                require((int((added&truth).sum()),int((added&~truth).sum()))==
                        (entry['bridges']['added_tp'],entry['bridges']['added_fp']),'Added TP/FP differ')
                for region,area in regions.items():
                    confusion=[int((mask&truth&area).sum()),int((mask&~truth&area).sum()),
                               int((~mask&truth&area).sum()),int((~mask&~truth&area).sum())]
                    require(confusion==[entry[region][k] for k in ('tp','fp','fn','tn')],'Confusion count differs')
                    regions_checked+=1
                sp=skeletonize(mask&fov,method='zhang');st=skeletonize(truth&fov,method='zhang')
                e=entry['continuity'];hp=int((sp&truth).sum());ht=int((st&mask).sum())
                require((hp,ht,int(sp.sum()),int(st.sum()))==(e['prediction_skeleton_inside_truth'],e['truth_skeleton_inside_prediction'],
                         e['prediction_skeleton_pixels'],e['truth_skeleton_pixels']),'Skeleton counts differ')
                precision=hp/int(sp.sum()) if sp.any() else 0
                recall=ht/int(st.sum()) if st.any() else 0
                cl=2*precision*recall/(precision+recall) if precision+recall else 0
                require(abs(cl-e['cldice'])<1e-12,'clDice arithmetic differs')
                # Graph edge count via coordinate pairs, independent of padded sampling.
                coords=set(zip(*np.nonzero(st)));total=covered=0
                for y,x in coords:
                    for dy,dx in ((0,1),(1,-1),(1,0),(1,1)):
                        if (y+dy,x+dx) in coords:
                            total+=1;covered+=int(mask[y,x] and mask[y+dy,x+dx])
                require((total,covered)==(e['truth_adjacent_edges'],e['covered_adjacent_edges']),'Graph-edge counts differ')
                matched+=1;pixels+=mask.size
        print('Q4_INDEPENDENT_CASE_PASS',image_id,side,flush=True)
    for path,digest in prov['protected_before'].items():require(sha(ROOT/path)==digest,'Protected source changed')
    result={'status':'Q4_OFFLINE_INDEPENDENT_MASK_AND_METRIC_COUNTS_PASS','matched_masks':matched,
            'matched_pixels':pixels,'region_confusion_tables':regions_checked,
            'experiment_report_sha256':sha(a.experiment/'training_report.json'),'verifier_sha256':sha(Path(__file__)),
            'source_commit':prov['source_commit'],'production_files_unchanged':True,
            'board_execution':False,'candidate_decision':report['decision']}
    if candidate_oracle is not None:
        module_path=Path(sys.modules[candidate_oracle.__module__].__file__)
        result['candidate_oracle_sha256']=sha(module_path)
        result['candidate_oracle_source']=module_path.relative_to(ROOT).as_posix()
    write_json(a.output,result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
