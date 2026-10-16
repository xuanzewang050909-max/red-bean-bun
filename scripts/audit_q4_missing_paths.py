"""Training-only diagnostic of existing missed skeleton components; no algorithm fit."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from skimage.morphology import skeletonize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_q1_bilateral import require, sha, write_json


def main():
    source = ROOT/'build/q4_gradient_2026-10-14_r4'
    output = ROOT/'build/q4_missing_paths_2026-10-14'
    require(not output.exists(), 'Preserve earlier audit')
    report = json.loads((source/'training_report.json').read_text())
    verified = json.loads((source/'independent_verification.json').read_text())
    require(verified['experiment_report_sha256'] == sha(source/'training_report.json'), 'Unverified report')
    bins = [('1', 1, 1), ('2-3', 2, 3), ('4-7', 4, 7), ('8-15', 8, 15), ('16+', 16, 2**31-1)]
    cases = {}
    for rec in report['array_records']:
        require(sha(source/rec['file']) == rec['sha256'], 'Changed arrays')
        image_id, side = rec['file'].split('_')[:2]
        with np.load(source/rec['file'], allow_pickle=False) as z:
            truth = z['truth_AH']; fov = z['fov']
            skel = skeletonize(truth & fov, method='zhang')
            groups = {}
            for name in ('C2', 'C6_r2_union_e3_g3'):
                mask = np.unpackbits(z[name])[:fov.size].reshape(fov.shape).astype(bool)
                missed = skel & ~mask
                _, _, stats, _ = cv2.connectedComponentsWithStats(missed.astype(np.uint8), connectivity=8)
                sizes = stats[1:, cv2.CC_STAT_AREA]
                distribution = {label: {'components': int(((sizes >= lo) & (sizes <= hi)).sum()),
                    'pixels': int(sizes[(sizes >= lo) & (sizes <= hi)].sum())} for label, lo, hi in bins}
                require(sum(x['pixels'] for x in distribution.values()) == int(missed.sum()), 'Missing pixel partition differs')
                groups[name] = {'gt_skeleton_pixels': int(skel.sum()), 'missed_pixels': int(missed.sum()), 'bins': distribution}
            cases[image_id+'_'+side] = groups
    pooled = {}
    for side in ('256', '512'):
        rows = [v for k, v in cases.items() if k.endswith('_'+side)]
        pooled[side] = {}
        for name in ('C2', 'C6_r2_union_e3_g3'):
            pooled[side][name] = {field: sum(r[name][field] for r in rows) for field in ('gt_skeleton_pixels', 'missed_pixels')}
            pooled[side][name]['bins'] = {label: {field: sum(r[name]['bins'][label][field] for r in rows)
                for field in ('components', 'pixels')} for label, _, _ in bins}
    output.mkdir()
    result = {'status': 'TRAIN_AH_MISSING_SKELETON_COMPONENT_DIAGNOSTIC_NOT_NEW_SELECTION',
        'source_report_sha256': sha(source/'training_report.json'), 'script_sha256': sha(Path(__file__)),
        'cases': cases, 'pooled': pooled, 'board_execution': False,
        'definition': 'Eight-connected components of original AH Zhang skeleton pixels missing from prediction, within original FOV.',
        'limit': 'Component size is NOT straight gap length. Components can curve/branch or be entirely missing branches; not proof that any specific connector can recover them. Labels are evaluation-only.'}
    write_json(output/'audit.json', result)
    print(json.dumps(pooled, indent=2))


if __name__ == '__main__':
    main()
