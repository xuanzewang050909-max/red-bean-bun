"""Fit frozen C7 d6 choice on original train AH, export integer model and HLS constants."""
import json
from pathlib import Path
import sys
import hashlib
import subprocess
import numpy as np
from sklearn.ensemble import RandomForestClassifier

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from software.q4d_features import integer_features
from software.q4d_forest import export_forest, predict_integer
from scripts.train_q4d_detector import metrics,aggregate
from scripts.evaluate_q1_bilateral import diagnostic_regions,write_json,require,sha
from scripts.evaluate_q4_refinement import protected

def header(model):
    lines=['// Generated fixed C7 d6 forest. See frozen decision and model SHA.', '#ifndef RETINA_C7_MODEL_HPP', '#define RETINA_C7_MODEL_HPP']
    for index,tree in enumerate(model['trees']):
        lines += [f'static ap_uint<8> c7_tree_{index}(ap_int<10> f[36]) {{', '#pragma HLS INLINE']
        def emit(node,indent):
            if tree['left'][node]==-1:
                return [indent+f'return {tree["leaf_q8"][node]};']
            result=[indent+f'if(f[{tree["feature"][node]}] <= {tree["threshold"][node]}) {{']
            result+=emit(tree['left'][node],indent+'  ')
            result += [indent+'} else {']+emit(tree['right'][node],indent+'  ')+[indent+'}']
            return result
        lines+=emit(0,'  ')+['}']
    lines += ['static ap_uint<8> c7_forest(ap_int<10> f[36]) {','#pragma HLS INLINE',
              '  ap_uint<12> total=0;']
    for index in range(len(model['trees'])): lines += [f'  total+=c7_tree_{index}(f);']
    lines += ['  return (total+4)>>3;','}','#endif']
    return '\n'.join(lines)+'\n'

def run():
    out=ROOT/'build/q4d_final_2026-10-15_r1'
    require(not out.exists(),'Preserve existing final fit')
    decision=ROOT/'docs/q4d_c7_experiment_decision.md'
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    require(subprocess.check_output(['git','show',commit+':docs/q4d_c7_experiment_decision.md'],cwd=ROOT).replace(b'\r\n',b'\n')==decision.read_bytes().replace(b'\r\n',b'\n'),'Decision not committed')
    out.mkdir(); before=protected()
    p=json.loads((ROOT/'docs/q4d_detector_protocol_r1.json').read_bytes())
    src=ROOT/p['input_experiment']; oof=ROOT/'build/q4d_detector_2026-10-15_r1'
    records=json.loads((src/'training_report.json').read_bytes())['array_records']
    xs=[];ys=[];cases={};names=None
    for record in records:
        image,side=record['file'].split('_')[:2]
        require(image in p['train_ids'],'Nontrain record')
        require(sha(src/record['file'])==record['sha256'],'Changed arrays')
        with np.load(src/record['file'],allow_pickle=False) as z:
            names,features=integer_features(z['green']); truth=z['truth_AH'].astype(bool); fov=z['fov'].astype(bool)
            idx=np.load(oof/f'{image}_{side}_training_indices.npy',allow_pickle=False)
            require(fov.ravel()[idx].all(),'NonFOV samples')
            xs.append(features.reshape(-1,36)[idx]);ys.append(truth.ravel()[idx].astype(np.uint8))
            cases[(image,side)]=dict(features=features,truth=truth,fov=fov,
                C5=np.unpackbits(z[p['c5_key']])[:fov.size].reshape(fov.shape).astype(bool),
                regions=diagnostic_regions({'filtered':z['filtered']},fov,truth))
    clf=RandomForestClassifier(n_estimators=8,max_depth=6,min_samples_leaf=32,max_features=0.75,
         class_weight={0:1,1:2},n_jobs=2,random_state=615,bootstrap=True).fit(np.concatenate(xs),np.concatenate(ys))
    model=export_forest(clf,names)
    write_json(out/'c7_model.json',model)
    (out/'retina_c7_model.hpp').write_text(header(model),encoding='utf-8',newline='\n')
    report={'256':{},'512':{}}
    for (image,side),case in cases.items():
        score=predict_integer(case['features'],model)
        np.save(out/f'{image}_{side}_score.npy',score,allow_pickle=False)
        report[side][image]=metrics((score>=112)&case['fov'],case)
    require(protected()==before,'Protected files changed')
    write_json(out/'fit_report.json',dict(status='FINAL_FIXED_CPU_MODEL_NOT_PL',source_commit=commit,
        decision_sha256=sha(decision),protocol_sha256=sha(ROOT/'docs/q4d_detector_protocol_r1.json'),
        grouped_report_sha256=sha(oof/'training_report.json'),model_sha256=sha(out/'c7_model.json'),
        header_sha256=sha(out/'retina_c7_model.hpp'),training_samples=sum(len(y) for y in ys),
        training_resubstitution={s:dict(per_image=rows,summary=aggregate(rows)) for s,rows in report.items()},
        heldout_or_VK_used=False,quality_pass=False,board_status='NOT_RUN',protected_unchanged=True))
    print('C7_FINAL_FIXED_MODEL_READY',sha(out/'c7_model.json'),flush=True)

if __name__=='__main__':run()
