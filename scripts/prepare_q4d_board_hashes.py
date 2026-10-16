"""Frozen model all-case CPU references. Evaluation only; never retune heldout/VK."""
import json
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from scripts.prepare_q4d_detector_vectors import expected_words
from scripts.evaluate_q1_bilateral import diagnostic_regions,score_mask,sha,write_json
from scripts.train_q4d_detector import aggregate
from software.reference import gaussian3
from software.continuity_metrics import continuity
from pynq_q4d.protocol import file_info,require

def main():
    out=ROOT/'build/q4d_board_references_01';require(not out.exists(),'Preserve references');out.mkdir()
    p=json.loads((ROOT/'docs/q4d_board_protocol_r1.json').read_bytes())
    old=json.loads((ROOT/'build/deploy/q3_full_quality_r1/browser_manifest.json').read_bytes())
    candidate=json.loads((ROOT/'results/q1_quality_2026-10-14/selected_candidate.json').read_bytes())['candidate']
    base=ROOT/'build/deploy/q3_full_quality_r1';hashes={};rows={}
    for image in sorted(p['split']['train']+p['split']['heldout']):
        for side in p['sizes']:
            entry=old['images'][image][str(side)]
            require(file_info(base/entry['input'])==entry['input_file'],'Changed input')
            words=np.load(base/entry['input'],allow_pickle=False);fov=(words>>24)!=0
            filtered=gaussian3(((words>>8)&255).astype(np.uint8))
            outputs={alg:expected_words(words,3,alg,p['thresholds'][alg],candidate) for alg in p['algorithms']}
            for alg,result in outputs.items():
                hashes[f'{image}_{side}_{alg}']=__import__('hashlib').sha256(result.astype('<u4').tobytes()).hexdigest()
            for observer,spec in entry['evaluation_only'].items():
                require(file_info(base/spec['path'])==old['artifacts'][spec['path']],'Changed labels')
                truth=np.load(base/spec['path'],allow_pickle=False).astype(bool)
                areas=diagnostic_regions({'filtered':filtered},fov,truth)
                for alg,result in outputs.items():
                    mask=((result>>16)&255)!=0;c5=((outputs['C5']>>16)&255)!=0
                    metrics={name:score_mask(mask,truth,area) for name,area in areas.items()}
                    metrics['continuity']=continuity(mask,truth,fov)
                    metrics['change_from_C5']={k:int(v.sum()) for k,v in dict(added_tp=mask&~c5&truth,added_fp=mask&~c5&~truth,removed_tp=c5&~mask&truth,removed_fp=c5&~mask&~truth).items()}
                    split='train_resubstitution' if image in p['split']['train'] else 'reused_heldout'
                    rows.setdefault(split,{}).setdefault(observer,{}).setdefault(str(side),{}).setdefault(alg,{})[image]=metrics
            np.save(out/f'{image}_{side}_C7_words.npy',outputs['C7'],allow_pickle=False)
        print('C7_FROZEN_REFERENCE_READY',image,flush=True)
    groups={split:{obs:{side:{alg:dict(per_image=items,summary=aggregate(items)) for alg,items in algorithms.items()} for side,algorithms in sizes.items()} for obs,sizes in observers.items()} for split,observers in rows.items()}
    write_json(out/'reference_hashes.json',dict(status='HOST_REFERENCE_NOT_PL',protocol_sha256=sha(ROOT/'docs/q4d_board_protocol_r1.json'),model_sha256=sha(ROOT/'software/models/c7_d6_r1.json'),expected_output_sha256=hashes))
    write_json(out/'frozen_evaluation.json',dict(status='FROZEN_CPU_EVALUATION_NOT_BOARD',groups=groups,retuned=False,quality_accepted=False,warning='Training values are resubstitution; heldout benchmark previously examined. Neither is new external validation. No real C7 PL output yet.'))
    print('C7_FROZEN_ALL_CASE_REFERENCE_COMPLETE',len(hashes),flush=True)

if __name__=='__main__':main()
