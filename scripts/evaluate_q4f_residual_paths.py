"""Frozen postprocessing screen of existing grouped residual predictions."""
import argparse,json,subprocess,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from software.q4f_residual_paths import mask,candidates
from evaluate_q4f_continuity import load_cases,score,aggregate,assess,sha,save,require,BASELINE

def main(out):
    require(not out.exists(),'Preserve prior experiment')
    pp=ROOT/'docs/q4f_residual_paths_protocol_r4.json';p=json.loads(pp.read_bytes())
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    for name in p['sources']+[pp.relative_to(ROOT).as_posix()]:
        blob=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
        require(blob.replace(b'\r\n',b'\n')==(ROOT/name).read_bytes().replace(b'\r\n',b'\n'),'Unfrozen '+name)
    require(sha(ROOT/'build/q4f_residual_r3/training_report.json')==p['previous_report_sha256'],'Residual source changed')
    grid=list(candidates(p));require(len(grid)==p['candidate_count'],'Candidate count')
    out.mkdir(parents=True);save(out/'provenance.json',dict(protocol=p,commit=commit,baseline_sha256=sha(BASELINE),
        sources={s:sha(ROOT/s) for s in p['sources']},VK_opened=False,reused_evaluation_opened=False))
    scores={n:{str(s):{'per_image':{}} for s in p['sizes']} for n in ['C7']+[c['id'] for c in grid]};artifacts=[]
    for image,side,d in load_cases(p['train_ids'],p['sizes']):
        scores['C7'][str(side)]['per_image'][image]=score(d['seed'],d)
        residuals={n:np.load(ROOT/f'build/q4f_residual_r3/{image}_{side}_n{n}_d8_oof_score.npy',allow_pickle=False) for n in p['trees']}
        saved={k:v for k,v in d.items() if k not in ('regions','features')}
        for c in grid:
            result=mask(d['green'],d['fov'],d['score'],residuals[c['trees']],c)
            scores[c['id']][str(side)]['per_image'][image]=score(result,d);saved[c['id']]=np.packbits(result)
        path=out/f'{image}_{side}.npz';np.savez_compressed(path,**saved);artifacts.append(dict(file=path.name,sha256=sha(path)))
        print('C8P_TRAIN_CASE_COMPLETE',image,side,flush=True)
    for sizes in scores.values():
        for d in sizes.values():d['summary']=aggregate(d['per_image'])
    assessments={c['id']:assess(scores[c['id']],scores['C7'],p['training_gates']) for c in grid}
    eligible=[c for c in grid if assessments[c['id']]['eligible']]
    eligible.sort(key=lambda c:(-sum(scores[c['id']][str(s)]['summary']['macro_fov']['dice']+scores[c['id']][str(s)]['summary']['continuity']['cldice'] for s in p['sizes']),c['trees'],c['steps'],c['id']))
    save(out/'training_report.json',dict(status='CPU_GROUPED_RESIDUAL_POSTPROCESS_NOT_BOARD',scores=scores,assessments=assessments,
        eligible_count=len(eligible),selected=eligible[0] if eligible else None,candidates=grid,artifacts=artifacts))
    print('C8P_SCREEN_COMPLETE',len(eligible),'eligible',eligible[0] if eligible else None,flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('output',type=Path);main(a.parse_args().output)
