"""Fine-angle residual fitting with grouped training-only contrast augmentation."""
import argparse,json,subprocess,sys
from pathlib import Path
import numpy as np
from sklearn.ensemble import RandomForestClassifier
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from software.q4f_residual import residual_features,combine,NORMALIZED
from software.q4f_continuity import protection
from software.q4f_fine_features import fine_features
from software.q4d_features import integer_features
from software.q4d_forest import predict_integer
from software.q4d_forest import export_forest,predict_integer
from evaluate_q4f_continuity import load_cases,score,aggregate,assess,sha,save,require,BASELINE

def main(out):
    require(not out.exists(),'Preserve prior experiment')
    pp=ROOT/'docs/q4f_fine_protocol_r5.json';p=json.loads(pp.read_bytes())
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    for name in p['sources']+[pp.relative_to(ROOT).as_posix()]:
        blob=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
        require(blob.replace(b'\r\n',b'\n')==(ROOT/name).read_bytes().replace(b'\r\n',b'\n'),'Unfrozen source '+name)
    out.mkdir(parents=True)
    save(out/'provenance.json',dict(protocol=p,commit=commit,baseline_sha256=sha(BASELINE),
        sources={s:sha(ROOT/s) for s in p['sources']},VK_opened=False,reused_evaluation_opened=False,
        caveat='C7 base was trained using all original train AH; grouped residual folds do not erase this base-model reuse. Not independent new validation.'))
    data={};samples={};base_model=json.loads((ROOT/'software/models/c7_d6_r1.json').read_bytes())
    base_names=base_model['features']+['c7_score']+[f'normalized_{base_model["features"][i]}' for i in NORMALIZED]
    for ix,(image,side,d) in enumerate(load_cases(p['train_ids'],p['sizes'])):
        tail,x=fine_features(d['green'],d['features'],d['score']);names=base_names+tail
        d['residual_features']=x;data[(image,str(side))]=d
        for aug,(num,den,shift) in enumerate(p['augmentations']):
            g=np.clip((d['green'].astype(np.int32)*num+den//2)//den+shift,0,255).astype(np.uint8)
            if aug==0:features=d['features'];c7_score=d['score'];xx=x
            else:
                _,features=integer_features(g);c7_score=predict_integer(features,base_model)
                _,xx=fine_features(g,features,c7_score)
            eligible=~protection(g,d['fov'])&~((c7_score>=112)&d['fov'])&d['fov']
            pos=np.flatnonzero(eligible&d['truth']);neg=np.flatnonzero(eligible&~d['truth'])
            rng=np.random.default_rng(p['random_seed']+ix*len(p['augmentations'])+aug)
            chosen=rng.choice(neg,min(len(neg),p['negative_samples_per_case']),replace=False)
            indices=np.concatenate([pos,chosen]);weights=np.concatenate([np.ones(len(pos)),np.full(len(chosen),len(neg)/max(1,len(chosen)))])
            samples[(image,str(side),aug)]=(xx.reshape(-1,len(names))[indices],d['truth'].ravel()[indices].astype(np.uint8),weights)
            np.save(out/f'{image}_{side}_a{aug}_sample_indices.npy',indices,allow_pickle=False)
        print('C8F_FEATURES_READY',image,side,len(names),flush=True)
    names_grid=[(n,depth,t,f'C8F_n{n}_d{depth}_t{t}') for n in p['trees'] for depth in p['depths'] for t in p['thresholds']]
    scores={name:{str(s):{'per_image':{}} for s in p['sizes']} for name in ['C7']+[c[3] for c in names_grid]}
    for (image,side),d in data.items():scores['C7'][side]['per_image'][image]=score(d['seed'],d)
    for n in p['trees']:
        for depth in p['depths']:
            for fold,excluded in enumerate(p['folds']):
                selected=[v for (i,s,a),v in samples.items() if i not in excluded]
                x=np.concatenate([v[0] for v in selected]);y=np.concatenate([v[1] for v in selected]);weights=np.concatenate([v[2] for v in selected])
                forest=RandomForestClassifier(n_estimators=n,max_depth=depth,min_samples_leaf=p['min_samples_leaf'],max_features=1.0,n_jobs=2,random_state=p['random_seed']+fold).fit(x,y,sample_weight=weights)
                model=export_forest(forest,names);save(out/f'n{n}_d{depth}_fold{fold}_model.json',model)
                for (image,side),d in data.items():
                    if image not in excluded:continue
                    result=predict_integer(d['residual_features'],model)
                    np.save(out/f'{image}_{side}_n{n}_d{depth}_oof_score.npy',result,allow_pickle=False)
                    for t in p['thresholds']:
                        mask=combine(d['green'],d['fov'],d['score'],result,t)
                        scores[f'C8F_n{n}_d{depth}_t{t}'][side]['per_image'][image]=score(mask,d)
                print('C8F_FOLD_COMPLETE',n,depth,fold,flush=True)
    for sizes in scores.values():
        for d in sizes.values():d['summary']=aggregate(d['per_image'])
    assessments={c[3]:assess(scores[c[3]],scores['C7'],p['training_gates']) for c in names_grid}
    eligible=[c for c in names_grid if assessments[c[3]]['eligible']]
    eligible.sort(key=lambda c:(-sum(scores[c[3]][str(s)]['summary']['macro_fov']['dice']+scores[c[3]][str(s)]['summary']['continuity']['cldice'] for s in p['sizes']),c[0]*(2**c[1]),c[3]))
    save(out/'training_report.json',dict(status='CPU_GROUPED_FINE_ANGLE_SCREEN_NOT_BOARD',scores=scores,assessments=assessments,
        eligible_count=len(eligible),selected=eligible[0] if eligible else None,candidates=names_grid))
    print('C8F_SCREEN_COMPLETE',len(eligible),'eligible',eligible[0] if eligible else None,flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('output',type=Path);main(a.parse_args().output)
