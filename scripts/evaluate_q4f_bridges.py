"""Second finite family; two-arm alignment replaces uncontrolled weak thickening."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from software.q4f_bridges import bridge_mask,candidates
from software.continuity_metrics import bridge_audit
from evaluate_q4f_continuity import load_cases,score,aggregate,assess,sha,save,require,BASELINE

def main(out):
    require(not out.exists(),'Preserve prior experiment')
    pp=ROOT/'docs/q4f_continuity_protocol_r2.json';p=json.loads(pp.read_bytes())
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    for name in p['sources']+[str(pp.relative_to(ROOT)).replace('\\','/')]:
        blob=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
        require(blob.replace(b'\r\n',b'\n')==(ROOT/name).read_bytes().replace(b'\r\n',b'\n'),'Unfrozen source '+name)
    require(sha(ROOT/'build/q4f_continuity_r1/training_report.json')==p['previous_report_sha256'],'Previous failures changed')
    grid=list(candidates(p));require(len(grid)==p['candidate_count'],'Candidate count')
    out.mkdir(parents=True)
    save(out/'provenance.json',dict(protocol=p,commit=commit,baseline_sha256=sha(BASELINE),
        sources={s:sha(ROOT/s) for s in p['sources']},VK_opened=False,reused_evaluation_opened=False))
    scores={name:{str(s):{'per_image':{}} for s in p['sizes']} for name in ['C7']+[c['id'] for c in grid]};artifacts=[]
    for image,side,d in load_cases(p['train_ids'],p['sizes']):
        scores['C7'][str(side)]['per_image'][image]=score(d['seed'],d)
        saved={k:v for k,v in d.items() if k not in ('regions','features')}
        for c in grid:
            mask,debug=bridge_mask(d['green'],d['fov'],d['features'],d['score'],d['c5'],c)
            require(not (mask^d['seed'])[debug['protected']].any(),'Protection invariant failed')
            m=score(mask,d);m['bridge_audit']=bridge_audit(mask,d['seed'],debug['links'],d['truth'],d['fov'])
            scores[c['id']][str(side)]['per_image'][image]=m;saved[c['id']]=np.packbits(mask)
        path=out/f'{image}_{side}.npz';np.savez_compressed(path,**saved);artifacts.append(dict(file=path.name,sha256=sha(path)))
        print('C8B_TRAIN_CASE_COMPLETE',image,side,flush=True)
    for sizes in scores.values():
        for item in sizes.values():
            item['summary']=aggregate({i:{k:v for k,v in d.items() if k!='bridge_audit'} for i,d in item['per_image'].items()})
    assessments={c['id']:assess(scores[c['id']],scores['C7'],p['training_gates']) for c in grid}
    eligible=[c for c in grid if assessments[c['id']]['eligible']]
    eligible.sort(key=lambda c:(-sum(scores[c['id']][str(s)]['summary']['macro_fov']['dice']+scores[c['id']][str(s)]['summary']['continuity']['cldice'] for s in p['sizes']),c['max_gap'],c['id']))
    save(out/'training_report.json',dict(status='CPU_SCREEN_COMPLETE_NOT_BOARD',candidates=grid,scores=scores,assessments=assessments,
        eligible_count=len(eligible),selected=eligible[0] if eligible else None,artifacts=artifacts))
    print('C8B_SCREEN_COMPLETE',len(eligible),'eligible',eligible[0] if eligible else None,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);main(p.parse_args().output)
