"""Same historical ROI: real C5 DMA versus frozen C7 CPU reference. No retuning."""
import io
import json
import zipfile
from pathlib import Path
import cv2
import numpy as np
from skimage.morphology import skeletonize
from audit_q4_board_residuals import ROI, figure, sha, require, missing_components
from software.reference import gaussian3
from software.metrics import evaluate
from software.continuity_metrics import continuity

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=ROOT/'build/q4d_original_region_review_01'
    require(not out.exists(),'Preserve earlier audit')
    old=json.loads((ROOT/'build/q4_board_residual_audit_2026-10-15/audit.json').read_bytes())
    archive=ROOT/'build/board_results/q4_quality_2026-10-15/q4_results_bundle.zip'
    require(sha(archive.read_bytes())==old['archive_sha256'],'Old real archive changed')
    record=old['records']['C5'];rid=record['run_id']
    with zipfile.ZipFile(archive) as z:
        source=np.load(io.BytesIO(z.read(rid+'/input_packed.npy')),allow_pickle=False)
        c5=np.load(io.BytesIO(z.read(rid+'/output_packed.npy')),allow_pickle=False)
    require(sha(source.astype('<u4').tobytes())==record['input_sha256'],'Input mismatch')
    require(sha(c5.astype('<u4').tobytes())==record['output_sha256'],'Actual C5 mismatch')
    c7path=ROOT/'build/q4d_board_references_01/im0001_512_C7_words.npy'
    c7=np.load(c7path,allow_pickle=False)
    refs=json.loads((ROOT/'build/q4d_board_references_01/reference_hashes.json').read_bytes())
    require(sha(c7.astype('<u4').tobytes())==refs['expected_output_sha256']['im0001_512_C7'],'Frozen C7 changed')
    require(np.array_equal(c5&65535,c7&65535),'Different raw/enhanced channels')
    package=ROOT/'build/deploy/q3_full_quality_r1'
    manifest=json.loads((package/'browser_manifest.json').read_bytes())
    entry=manifest['images']['im0001']['512']
    require(np.array_equal(source,np.load(package/entry['input'],allow_pickle=False)),'Image geometry changed')
    truth={}
    for observer,meta in entry['evaluation_only'].items():
        data=(package/meta['path']).read_bytes()
        require(sha(data)==meta['file']['sha256'],'Annotation changed')
        truth[observer]=np.load(io.BytesIO(data),allow_pickle=False).astype(bool)
    rgb=np.stack([(source>>16)&255,(source>>8)&255,source&255],axis=-1).astype(np.uint8)
    fov=source>>24!=0;x0,y0,x1,y1=ROI
    rect=np.zeros_like(fov);rect[y0:y1,x0:x1]=True;rect&=fov
    core=rect&(gaussian3(rgb[...,1])>=192)
    band=cv2.dilate(core.astype(np.uint8),np.ones((15,15),np.uint8)).astype(bool)&~core&rect
    both_negative=~truth['AH']&~truth['VK']
    masks={'C5 actual DMA':((c5>>16)&255)!=0,'C7 CPU reference':((c7>>16)&255)!=0}
    scopes={'fov':fov,'rectangle':rect,'bright_band':band}
    metrics={}
    for name,mask in masks.items():
        metrics[name]={'regions':{s:dict(pixels=int(region.sum()),predicted=int((mask&region).sum()),
                        negative_in_both=int((mask&region&both_negative).sum()),
                        annotations={o:evaluate(mask,t,region) for o,t in truth.items()}) for s,region in scopes.items()},
                       'continuity':{o:continuity(mask,t,fov) for o,t in truth.items()},
                       'missed_skeleton':{o:missing_components(mask,t,fov) for o,t in truth.items()}}
    require(metrics['C5 actual DMA']['regions']['bright_band']['negative_in_both']==1933,'Historic C5 band not reproduced')
    old_counts=old['metrics']['C5']['original_seven_pixel_square_band']
    require(metrics['C5 actual DMA']['regions']['bright_band']['annotations']==old_counts['annotations'],'Historic confusion counts changed')
    out.mkdir(parents=True)
    crop=np.s_[y0:y1,x0:x1];backdrop=(rgb.astype(np.uint16)//4).astype(np.uint8);panels=[]
    for name,mask in masks.items():
        error=backdrop.copy();error[mask&truth['AH']&fov]=[40,220,80];error[mask&~truth['AH']&fov]=[255,45,45];error[~mask&truth['AH']&fov]=[50,190,255]
        bright=backdrop.copy();bright[core]=[255,210,0];bright[band]=[60,70,85];bright[mask&band&both_negative]=[255,45,45]
        count=metrics[name]['regions']['bright_band']['negative_in_both']
        panels.extend([(name,np.repeat((mask.astype(np.uint8)*255)[...,None],3,axis=2)[crop]),
                       (name+': AH TP/FP/FN',error[crop]),(name+f': band FP* {count}',bright[crop])])
    figure(out/'same_roi_c5_real_c7_reference.png',panels,3,(320,480),[
        'C5: verified physical-board DMA, T28. C7: frozen CPU reference, T112; NOT new board output.',
        '*Same original im0001 crop/band. Both AH and VK label these predicted pixels as background.',
        'Green TP / red FP / cyan FN. Training-image resubstitution, not independent quality acceptance.'])
    skeleton=skeletonize(truth['AH']&fov,method='zhang')
    panels=[('Input RGB',rgb)]
    for name,mask in masks.items():
        view=backdrop.copy();view[skeleton&mask]=[40,220,80];view[skeleton&~mask]=[50,190,255]
        panels.append((name+': AH centerline',view))
    figure(out/'same_full_fov_centerline.png',panels,3,(512,512),[
        'Green: covered AH centerline. Cyan: missed. No pixels were drawn into either segmentation.',
        'C7 is a frozen CPU reference; actual-board confirmation and visual acceptance remain pending.'])
    report=dict(status='MIXED_REAL_C5_FROZEN_CPU_C7_DIAGNOSTIC_NOT_BOARD_ACCEPTANCE',metrics=metrics,
                original_roi=ROI,model_unchanged=True,retuned=False,quality_accepted=False,
                c5_archive_sha256=old['archive_sha256'],c5_run=record,c7_array_sha256=sha(c7path.read_bytes()),
                model_sha256=sha((ROOT/'software/models/c7_d6_r1.json').read_bytes()),
                figures={p.name:sha(p.read_bytes()) for p in out.glob('*.png')})
    (out/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({name:dict(band_FP=v['regions']['bright_band']['negative_in_both'],
                             band_AH=v['regions']['bright_band']['annotations']['AH'],
                             centerline=v['continuity']['AH']) for name,v in metrics.items()},indent=2))


if __name__=='__main__':main()
