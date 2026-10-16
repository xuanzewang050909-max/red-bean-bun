"""Finite C8 training-AH screen against verified C7 real DMA. No board writes."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from software.q4f_continuity import candidates,candidate_mask
from software.q4d_features import integer_features
from software.reference import gaussian3
from software.continuity_metrics import continuity
from verify_q1_training import independent_regions,independent_metrics,require
from evaluate_q1_bilateral import summarize

PROTOCOL=ROOT/'docs/q4f_continuity_protocol_r1.json'
BASELINE=ROOT/'results/q4d_detector_2017_4_r1/board_execution_2026-10-15/verification.json'
ARCHIVE=ROOT/'build/board_results/q4d_quality_2026-10-15/q4d_results_bundle.zip'
PACKAGE=ROOT/'build/deploy/q4d_c7_experimental_r1'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,o):p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def load_cases(ids,sizes):
    baseline=json.loads(BASELINE.read_bytes())
    require('REAL_PL_DATA_VERIFIED' in baseline['status'],'Unverified real baseline')
    require(sha(ARCHIVE)==baseline['archive']['sha256'],'Real archive changed')
    manifest=json.loads((PACKAGE/'browser_manifest.json').read_bytes())
    records={(r['request']['image_id'],r['request']['side'],r['request']['algorithm']):r for r in baseline['runs'][:160]}
    with zipfile.ZipFile(ARCHIVE) as z:
        for image in ids:
            for side in sizes:
                load=lambda path:np.load(io.BytesIO(z.read(path)),allow_pickle=False)
                c7r=records[(image,side,'C7')];c5r=records[(image,side,'C5')]
                source=load(c7r['run_id']+'/input_packed.npy')
                c7=load(c7r['run_id']+'/output_packed.npy');c5=load(c5r['run_id']+'/output_packed.npy')
                green=((source>>8)&255).astype(np.uint8);fov=source>>24!=0
                names,features=integer_features(green)
                truth_path=manifest['images'][image][str(side)]['evaluation_only']['AH']['path']
                truth=np.load(PACKAGE/truth_path,allow_pickle=False).astype(bool)
                yield image,side,dict(green=green,fov=fov,features=features,
                    score=(c7>>24).astype(np.uint8),c5=((c5>>16)&255)!=0,
                    seed=((c7>>16)&255)!=0,truth=truth,
                    regions=independent_regions({'filtered':gaussian3(green)},truth,fov),
                    source=source,baseline_words=c7)


def score(mask,d):
    result={k:independent_metrics(mask,d['truth'],region) for k,region in d['regions'].items()}
    result['continuity']=continuity(mask,d['truth'],d['fov'])
    added=mask&~d['seed']
    result['changes']=dict(added_tp=int((added&d['truth']).sum()),added_fp=int((added&~d['truth']).sum()),
        removed=int((d['seed']&~mask).sum()),bright_changed=int(((mask^d['seed'])&(d['regions']['bright_core']|d['regions']['bright_band'])).sum()))
    return result


def aggregate(per):
    summary=summarize({i:{k:v for k,v in d.items() if k not in ('continuity','changes')} for i,d in per.items()})
    summary['continuity']={k:float(np.mean([d['continuity'][k] for d in per.values()]))
        for k in ('cldice','topology_recall','adjacent_edge_coverage')}
    summary['changes']={k:sum(d['changes'][k] for d in per.values())
        for k in ('added_tp','added_fp','removed','bright_changed')}
    n=summary['changes']['added_tp']+summary['changes']['added_fp']
    summary['added_precision']=summary['changes']['added_tp']/n if n else 0
    return summary


def assess(sizes,base,gates):
    failures=[];deltas={}
    for side,data in sizes.items():
        s,b=data['summary'],base[side]['summary']
        ds=dict(dice=s['macro_fov']['dice']-b['macro_fov']['dice'],
            thin=s['pooled']['thin_label_proxy']['recall']-b['pooled']['thin_label_proxy']['recall'],
            skeleton=s['continuity']['topology_recall']-b['continuity']['topology_recall'],
            cldice=s['continuity']['cldice']-b['continuity']['cldice'],added_precision=s['added_precision'])
        deltas[side]=ds
        for key,minimum in [('dice',gates['each_size_macro_dice_gain_min']),('cldice',gates['each_size_macro_cldice_gain_min']),
                            ('added_precision',gates['each_size_added_precision_min'])]:
            if ds[key]<minimum-1e-12:failures.append(side+':'+key)
        if side=='512':
            if ds['thin']<gates['512_pooled_thin_recall_gain_min']-1e-12:failures.append(side+':thin')
            if ds['skeleton']<gates['512_macro_skeleton_recall_gain_min']-1e-12:failures.append(side+':skeleton')
        for image,row in data['per_image'].items():
            old=base[side]['per_image'][image]
            if row['changes']['removed'] or row['changes']['bright_changed']:failures.append(side+':invariant:'+image)
            if row['fov']['dice']<old['fov']['dice']-1e-12:failures.append(side+':image_dice:'+image)
            for k in ('thin_label_proxy',):
                if row[k]['recall'] is not None and row[k]['recall']<old[k]['recall']-1e-12:failures.append(side+':thin:'+image)
            if row['continuity']['topology_recall']<old['continuity']['topology_recall']-1e-12:failures.append(side+':skeleton:'+image)
    return dict(eligible=not failures,failures=failures,deltas=deltas)


def main(out):
    require(not out.exists(),'Preserve prior screen')
    protocol=json.loads(PROTOCOL.read_bytes());commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    for name in protocol['sources']+['docs/q4f_continuity_protocol_r1.json']:
        committed=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
        require(committed.replace(b'\r\n',b'\n')==(ROOT/name).read_bytes().replace(b'\r\n',b'\n'),'Unfrozen source '+name)
    require(sha(ROOT/'software/models/c7_d6_r1.json')==protocol['model_sha256'],'C7 model changed')
    grid=list(candidates(protocol));require(len(grid)==protocol['candidate_count'],'Wrong count')
    out.mkdir(parents=True)
    save(out/'provenance.json',dict(status='TRAIN_AH_CPU_SCREEN_NOT_NEW_BOARD',commit=commit,protocol=protocol,
        baseline_verification_sha256=sha(BASELINE),sources={s:sha(ROOT/s) for s in protocol['sources']},VK_opened=False,reused_evaluation_opened=False))
    scores={name:{str(s):{'per_image':{}} for s in protocol['sizes']} for name in ['C7']+[c['id'] for c in grid]}
    artifacts=[]
    for image,side,d in load_cases(protocol['train_ids'],protocol['sizes']):
        require(np.array_equal(d['seed'],(d['score']>=112)&d['fov']),'Actual C7 threshold mismatch')
        scores['C7'][str(side)]['per_image'][image]=score(d['seed'],d)
        saved={k:v for k,v in d.items() if k!='regions'}
        for cfg in grid:
            result,debug=candidate_mask(d['green'],d['fov'],d['features'],d['score'],d['c5'],cfg)
            require(not (result^d['seed'])[debug['protected']].any(),'Protected pixels changed')
            require(not (d['seed']&~result).any(),'Baseline removed')
            scores[cfg['id']][str(side)]['per_image'][image]=score(result,d)
            saved[cfg['id']]=np.packbits(result)
        path=out/f'{image}_{side}.npz';np.savez_compressed(path,**saved)
        artifacts.append(dict(file=path.name,sha256=sha(path)))
        print('C8_TRAIN_CASE_COMPLETE',image,side,flush=True)
    for sizes in scores.values():
        for d in sizes.values():d['summary']=aggregate(d['per_image'])
    assessments={c['id']:assess(scores[c['id']],scores['C7'],protocol['training_gates']) for c in grid}
    eligible=[c for c in grid if assessments[c['id']]['eligible']]
    eligible.sort(key=lambda c:(-sum(scores[c['id']][str(s)]['summary']['macro_fov']['dice']+scores[c['id']][str(s)]['summary']['continuity']['cldice'] for s in protocol['sizes']),c['steps'],c['include_c5'],c['id']))
    save(out/'training_report.json',dict(status='CPU_SCREEN_COMPLETE_NOT_BOARD',candidates=grid,scores=scores,assessments=assessments,
        eligible_count=len(eligible),selected=eligible[0] if eligible else None,artifacts=artifacts))
    print(json.dumps(dict(eligible_count=len(eligible),selected=eligible[0] if eligible else None,
        decisions={k:v for k,v in assessments.items()}),ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);main(p.parse_args().output)
