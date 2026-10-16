"""Q4a finite training-only screen. No PYNQ, production modification, or GT input to algorithms."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys

import numpy as np
import cv2
import skimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_q1_bilateral import (assess_candidate, diagnostic_regions,
    read_training_archive, require, score_mask, sha, summarize, write_json)
from software.preprocessing import prepare_sample
from software.reference import features, segment
from software.q4_refinement import candidates, flank_features, refined_mask
from software.continuity_metrics import continuity, bridge_audit

PROTOCOL = "docs/q4_refinement_protocol_r1.json"


def protected():
    directories = ("pynq_app", "pynq_w3", "pynq_w4a", "ui", "ui_w3", "ui_w4a",
                   "build/deploy/w2_quality_2017_4_r1", "build/deploy/q3_full_quality_r1")
    return {p.relative_to(ROOT).as_posix(): sha(p) for name in directories
            for p in sorted((ROOT / name).rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


def extra_summary(per_image):
    macro = {key: float(np.mean([v['continuity'][key] for v in per_image.values()]))
             for key in ('cldice', 'topology_precision', 'topology_recall', 'adjacent_edge_coverage')}
    bridge = {key: sum(v['bridges'][key] for v in per_image.values())
              for key in next(iter(per_image.values()))['bridges']}
    n = bridge['added_tp'] + bridge['added_fp']
    bridge['added_precision'] = bridge['added_tp'] / n if n else None
    return {'macro_continuity': macro, 'bridges': bridge}


def assess_new(candidate, a, c2, protocol):
    old = assess_candidate(candidate, a, protocol['unchanged_A28_gates'])
    failures = ['A28:' + s for s in old['failed_gates']]
    deltas = {}
    gates = protocol['new_C2_gates']
    for side in ('256', '512'):
        c, b = candidate[side]['summary'], c2[side]['summary']
        cm, bm = c['macro_continuity'], b['macro_continuity']
        d = {key: cm[key] - bm[key] for key in cm}
        d['dice'] = c['macro_fov']['dice'] - b['macro_fov']['dice']
        d['recall'] = c['macro_fov']['recall'] - b['macro_fov']['recall']
        d['thin_recall'] = c['pooled']['thin_label_proxy']['recall'] - b['pooled']['thin_label_proxy']['recall']
        d['bright_recall'] = c['pooled']['bright_band']['recall'] - b['pooled']['bright_band']['recall']
        d['bright_fp_reduction'] = 1 - c['pooled']['bright_band']['fp'] / b['pooled']['bright_band']['fp']
        def limit(key, lower):
            if d[key] < lower - 1e-12:
                failures.append(side + ':' + key)
        limit('dice', -gates['each_size_dice_loss_max'])
        limit('recall', -gates['each_size_macro_recall_loss_max'])
        limit('bright_recall', -gates['each_size_bright_recall_loss_max'])
        limit('thin_recall', gates['512_thin_recall_gain_min'] if side == '512' else 0)
        limit('cldice', gates['512_cldice_gain_min'] if side == '512' else 0)
        limit('adjacent_edge_coverage', 0)
        if side == '512':
            limit('bright_fp_reduction', gates['512_bright_fp_reduction_min'])
        for name, item in candidate[side]['per_image'].items():
            delta = item['continuity']['topology_recall'] - c2[side]['per_image'][name]['continuity']['topology_recall']
            if delta < -gates['each_image_skeleton_recall_loss_max'] - 1e-12:
                failures.append(side + ':skeleton_recall:' + name)
        bridge = c['bridges']
        if bridge['added_precision'] is not None and bridge['added_precision'] < gates['added_pixel_precision_min']:
            failures.append(side + ':bridge_added_precision')
        deltas[side] = d
    return {'eligible_for_PL_feasibility': not failures, 'failed_gates': failures,
            'A28_comparison': old, 'C2_deltas': deltas}


def main(protocol_name=PROTOCOL, candidate_factory=candidates, mask_factory=refined_mask):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Preserve earlier attempts; use new output')
    protocol = json.loads((ROOT / protocol_name).read_text(encoding='utf-8'))
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    sources = protocol['source_files'] + [protocol_name]
    for name in sources:
        require(subprocess.check_output(['git', 'show', commit + ':' + name], cwd=ROOT) ==
                (ROOT / name).read_bytes(), 'Commit exact source before screening: ' + name)
    for name, digest in protocol['frozen_sha256'].items():
        require(sha(ROOT / name) == digest, 'Frozen source changed: ' + name)
    require(skimage.__version__ == protocol['skeleton_library_version'], 'Skeleton version differs')
    grid = list(candidate_factory())
    require(grid == protocol['candidates'], 'Candidate grid changed')
    train, heldout = protocol['train_ids'], protocol['heldout_ids']
    original = json.loads((ROOT / 'results/m0_stare_2026-10-11/evaluation.json').read_text())
    require(train == original['split']['train'] and heldout == original['split']['heldout'], 'Split changed')
    before = protected()
    args.output.mkdir(parents=True)
    write_json(args.output / 'provenance.json', {
        'source_commit': commit, 'source_sha256': {n: sha(ROOT/n) for n in sources},
        'protocol': protocol, 'started_utc': datetime.now(timezone.utc).isoformat(),
        'location': 'WINDOWS_OFFLINE_CPU_NOT_PL', 'decoded_train_ids': train,
        'decoded_heldout_ids_this_experiment': [], 'VK_opened_this_experiment': False,
        'old_heldout_previously_seen_in_Q3': True, 'protected_before': before,
        'environment': {'python': platform.python_version(), 'numpy': np.__version__,
                        'opencv': cv2.__version__, 'skimage': skimage.__version__}})
    raw = ROOT / 'data/raw/stare'
    images = read_training_archive(raw/'stare-images.tar', '', train, train+heldout)
    labels = read_training_archive(raw/'labels-ah.tar', '.ah', train, train+heldout)
    q3 = json.loads((ROOT / protocol['Q3_verification']).read_text(encoding='utf-8'))
    scores = {name: {s: {'per_image': {}} for s in ('256','512')}
              for name in ['A', 'C2'] + [c['id'] for c in grid]}
    arrays = []
    for image_id in train:
        for side in (256, 512):
            rgb, aligned, geometry = prepare_sample(images[image_id]['pixels'],
                {'AH': labels[image_id]['pixels'] != 0}, side)
            truth, fov = aligned['AH'], aligned['fov']
            feat = features(rgb, fov, 'A')
            regions = diagnostic_regions(feat, fov, truth)
            cache = {key: flank_features(feat[key]) for key in ('enhanced', 'filtered')}
            support = np.logical_or.reduce([s >= 9 for pairs in cache['enhanced'] for s, _ in pairs])
            c2_response = np.maximum(0, feat['response'].astype(np.int16) - (~support)*28).astype(np.uint8)
            a = segment(feat['response'], fov, 28); c2 = segment(c2_response, fov, 28)
            masks = {'A': a, 'C2': c2}
            for name, mask in masks.items():
                response = feat['response'] if name == 'A' else c2_response
                words = (feat['green'].astype(np.uint32) | (feat['enhanced'].astype(np.uint32) << 8)
                         | (mask.astype(np.uint32)*255 << 16) | (response.astype(np.uint32) << 24))
                native = next(r for r in q3['runs'] if r['request']['image_id'] == image_id
                              and r['request']['side'] == side and r['request']['algorithm'] == name)
                require(hashlib.sha256(words.astype('<u4').tobytes()).hexdigest() == native['output_sha256'],
                        'Reproduced training A/C2 pixels differ from verified real DMA')
                observed = q3['quality']['groups']['train_AH']['scores'][name][str(side)]['per_image'][image_id]
                for scope, region in regions.items():
                    score = score_mask(mask, truth, region)
                    for k in ('tp','fp','fn','tn'):
                        require(score[k] == observed[scope][k], 'Training baseline differs from real Q3')
            seeds_links = {name: (mask, []) for name, mask in masks.items()}
            for candidate in grid:
                mask, seed, links = mask_factory(feat,fov,c2,cache,candidate)
                require(not (mask & ~fov).any(), 'Candidate escaped original FOV')
                masks[candidate['id']] = mask; seeds_links[candidate['id']] = (seed,links)
            for name, mask in masks.items():
                seed, links = seeds_links[name]
                entry = {scope: score_mask(mask,truth,region) for scope,region in regions.items()}
                entry['continuity'] = continuity(mask,truth,fov)
                entry['bridges'] = bridge_audit(mask,seed,links,truth,fov)
                entry['difference_from_C2'] = {
                    'added_tp': int((mask & ~c2 & truth).sum()), 'added_fp': int((mask & ~c2 & ~truth).sum()),
                    'removed_tp': int((c2 & ~mask & truth).sum()), 'removed_fp': int((c2 & ~mask & ~truth).sum())}
                scores[name][str(side)]['per_image'][image_id] = entry
            dest = args.output/f'{image_id}_{side}_offline_masks.npz'
            np.savez_compressed(dest,rgb=rgb,truth_AH=truth,fov=fov,**feat,
                **{name: np.packbits(mask,axis=None) for name,mask in masks.items()})
            arrays.append({'file':dest.name,'sha256':sha(dest),'geometry':geometry,
                'input_member_sha256':images[image_id]['sha256'],'AH_member_sha256':labels[image_id]['sha256'],
                'mask_sha256':{name:hashlib.sha256(mask.astype(np.uint8).tobytes()).hexdigest() for name,mask in masks.items()}})
            print('Q4_TRAIN_CASE_COMPLETE',image_id,side,len(grid),'candidates + A/C2',flush=True)
    for name, bysize in scores.items():
        for side, data in bysize.items():
            data['summary'] = {**summarize(data['per_image']), **extra_summary(data['per_image'])}
    assessments = {c['id']:assess_new(scores[c['id']],scores['A'],scores['C2'],protocol) for c in grid}
    eligible = [c for c in grid if assessments[c['id']]['eligible_for_PL_feasibility']]
    eligible.sort(key=lambda c:(-scores[c['id']]['512']['summary']['macro_fov']['dice'],c['gap'],c['id']))
    require(protected() == before, 'Production/released bytes changed')
    report = {'status':'Q4_CPU_TRAINING_COMPLETE_NOT_PL','source_commit':commit,
        'protocol_sha256':sha(ROOT/protocol_name),'scores':scores,'assessments':assessments,'array_records':arrays,
        'candidate_count':len(grid),'training_cases':20,'selected_candidate':eligible[0] if eligible else None,
        'eligible_count':len(eligible),'decision':'PL_FEASIBILITY_ONLY' if eligible else 'REJECT_'+protocol['protocol']+'_FOR_PL',
        'Q3_train_baselines_reproduced':True,'preserved_file_count':len(before),'preserved_unchanged':True,
        'heldout_or_VK_scored_for_new_candidates':False,'new_hardware_status':'NOT_IMPLEMENTED',
        'board_performance':None,'finished_utc':datetime.now(timezone.utc).isoformat()}
    write_json(args.output/'training_report.json',report)
    print(report['decision'], 'eligible',len(eligible),flush=True)


if __name__ == '__main__':
    main()
