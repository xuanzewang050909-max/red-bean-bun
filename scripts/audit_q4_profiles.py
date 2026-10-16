"""Preregistered train-AH feature separability audit; no new segmentation mask."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np
import skimage
from skimage.morphology import skeletonize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from software.q4_profile_features import profile_features, kernels
from scripts.evaluate_q4_refinement import protected
from scripts.evaluate_q1_bilateral import require, sha, write_json

PROTOCOL = 'docs/q4_profile_audit_protocol_d1.json'


def histograms(score, truth, area):
    return np.stack([np.bincount(score[area & truth], minlength=65536),
                     np.bincount(score[area & ~truth], minlength=65536)]).astype(np.int64)


def metrics(hist):
    pos, neg = hist; p, n = int(pos.sum()), int(neg.sum())
    if not p or not n:
        return {'positives': p, 'negatives': n, 'prevalence': p/(p+n) if p+n else None,
                'auc': None, 'average_precision': None}
    auc = float((pos*(np.cumsum(neg)-neg+neg/2)).sum()/(p*n))
    tp, fp = np.cumsum(pos[::-1]), np.cumsum(neg[::-1])
    precision = np.divide(tp, tp+fp, out=np.zeros_like(tp, dtype=float), where=(tp+fp) > 0)
    ap = float((precision*pos[::-1]).sum()/p)
    return {'positives': p, 'negatives': n, 'prevalence': p/(p+n), 'auc': auc, 'average_precision': ap}


def bounds(hist, max_removed_tp=None):
    """Optimistic same-sample scalar threshold analysis, NOT adopted thresholds."""
    tp, fp = np.cumsum(hist[0, ::-1]), np.cumsum(hist[1, ::-1])
    if max_removed_tp is not None:
        ok = tp >= max(0, int(hist[0].sum())-max_removed_tp)
        indices = np.flatnonzero(ok)
        if not len(indices): return None
        i = int(indices[0])
        return {'threshold_q8': 65535-i, 'retained_tp': int(tp[i]), 'retained_fp': int(fp[i]),
                'removed_tp': int(hist[0].sum()-tp[i]), 'removed_fp': int(hist[1].sum()-fp[i])}
    ok = (tp > 0) & (tp*5 >= 4*(tp+fp))  # Exact >=80%; do not round acceptance.
    indices = np.flatnonzero(ok)
    if not len(indices): return None
    # Maximum recovered TP, then the highest threshold; no lower-precision fallback.
    i = int(indices[np.argmax(tp[indices])])
    return {'threshold_q8': 65535-i, 'added_tp': int(tp[i]), 'added_fp': int(fp[i]),
            'precision': float(tp[i]/(tp[i]+fp[i]))}


def groups(filtered, truth, fov, c2):
    core = (filtered >= 192) & fov
    band = cv2.dilate(core.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool) & ~core & fov
    skeleton = skeletonize(truth & fov, method='zhang')
    missing = skeleton & ~c2
    _, labels, stats, _ = cv2.connectedComponentsWithStats(missing.astype(np.uint8), connectivity=8)
    sizes = stats[:, cv2.CC_STAT_AREA].copy(); sizes[0] = 0
    long_missing = missing & (sizes[labels] > 3)
    near = cv2.dilate(skeleton.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool) & fov & ~truth & ~c2
    return {'fov': fov, 'bright_C2': band & c2, 'outside_C2': fov & ~c2,
            'long_missing_vs_near_bg': long_missing | near}, int((band & truth).sum())


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); require(not args.output.exists(), 'Preserve prior run')
    protocol = json.loads((ROOT/PROTOCOL).read_text(encoding='utf-8'))
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    for name in protocol['source_files']+[PROTOCOL]:
        require(subprocess.check_output(['git', 'show', commit+':'+name]) == (ROOT/name).read_bytes(), 'Commit source: '+name)
    source = ROOT/protocol['input_experiment']
    require(sha(source/'training_report.json') == protocol['source_report_sha256'], 'Changed source report')
    old = json.loads((source/'training_report.json').read_text())
    expected_cases = {(i, str(s)) for i in protocol['train_ids'] for s in protocol['sizes']}
    recorded_cases = [tuple(r['file'].split('_')[:2]) for r in old['array_records']]
    require(len(recorded_cases) == len(expected_cases) and set(recorded_cases) == expected_cases, 'Changed training inventory')
    verified = json.loads((source/'independent_verification.json').read_text())
    require(verified['experiment_report_sha256'] == protocol['source_report_sha256'], 'Unverified source')
    require(skimage.__version__ == protocol['skeleton_library_version'], 'Skeleton version changed')
    for name, checksum in protocol['frozen_sha256'].items():
        require(sha(ROOT/name) == checksum, 'Frozen source changed: '+name)
    bank = [{k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in x.items()} for x in kernels()]
    require(bank == protocol['coefficient_tables'], 'Coefficient bank changed')
    before = protected(); args.output.mkdir(parents=True)
    write_json(args.output/'provenance.json', {'source_commit': commit, 'protocol': protocol,
        'source_sha256': {n: sha(ROOT/n) for n in protocol['source_files']+[PROTOCOL]},
        'protected_before': before, 'started_utc': datetime.now(timezone.utc).isoformat(),
        'location': 'WINDOWS_CPU_FEATURE_DIAGNOSTIC_NOT_PL', 'decoded_heldout': [], 'VK_opened': False})
    all_hist = {}; cases = {}; records = []; bright_totals = {'256': 0, '512': 0}
    for record in old['array_records']:
        image_id, side = record['file'].split('_')[:2]
        require(image_id in protocol['train_ids'] and int(side) in protocol['sizes'], 'Forbidden case')
        require(sha(source/record['file']) == record['sha256'], 'Changed verified input')
        with np.load(source/record['file'], allow_pickle=False) as z:
            fov, truth = z['fov'], z['truth_AH']
            c2 = np.unpackbits(z['C2'])[:fov.size].reshape(fov.shape).astype(bool)
            group, bright_truth = groups(z['filtered'], truth, fov, c2)
            bright_totals[side] += bright_truth
            features = {'A_response': z['response'].astype(np.uint16)*256}
            for branch in ('green', 'filtered'):
                for name, value in profile_features(z[branch]).items():
                    # Every stored rank has the same declared direction: larger => vessel-like.
                    features[branch+'_'+name] = 65535-value if name == 'paired_edge' else value
            require(sorted(features) == sorted(protocol['features']), 'Feature inventory changed')
            case = {}; hists = {}
            for name, score in features.items():
                case[name] = {}
                for kind, area in group.items():
                    hist = histograms(score, truth, area)
                    hists[name+'__'+kind] = hist
                    all_hist.setdefault(side, {}).setdefault(name, {}).setdefault(kind, np.zeros((2, 65536), np.int64))
                    all_hist[side][name][kind] += hist
                    case[name][kind] = metrics(hist)
            fname = image_id+'_'+side+'_features.npz'
            np.savez_compressed(args.output/fname, **features)
            hname = image_id+'_'+side+'_histograms.npz'
            np.savez_compressed(args.output/hname, **hists)
            records.append({'input_file': record['file'], 'input_sha256': record['sha256'],
                'feature_file': fname, 'feature_sha256': sha(args.output/fname),
                'histogram_file': hname, 'histogram_sha256': sha(args.output/hname),
                'pixel_count': fov.size, 'bright_truth_pixels': bright_truth})
            cases[image_id+'_'+side] = case
        print('PROFILE_FEATURE_CASE_COMPLETE', image_id, side, len(features), flush=True)
    require(len(records) == 20, 'Missing cases')
    pooled = {}
    for side, features in all_hist.items():
        pooled[side] = {}
        for name, scopes in features.items():
            result = {kind: metrics(hist) for kind, hist in scopes.items()}
            result['optimistic_bright_removal'] = bounds(scopes['bright_C2'], bright_totals[side]//50)
            result['optimistic_outside_addition_at_80pct'] = bounds(scopes['outside_C2'])
            pooled[side][name] = result
        np.savez_compressed(args.output/f'pooled_{side}_histograms.npz',
            **{name+'__'+kind: hist for name, scopes in features.items() for kind, hist in scopes.items()})
    require(protected() == before, 'Protected files changed')
    report = {'status': 'FEATURE_AUDIT_COMPLETE_NOT_A_SEGMENTATION_ACCEPTANCE', 'source_commit': commit,
        'protocol_sha256': sha(ROOT/PROTOCOL), 'cases': cases, 'pooled': pooled, 'array_records': records,
        'bright_truth_totals': bright_totals, 'training_cases': len(records), 'features_per_case': 15,
        'new_segmentation_candidates': 0, 'selected_candidate': None, 'new_hardware_status': 'NOT_IMPLEMENTED',
        'protected_files': len(before), 'production_unchanged': True, 'heldout_or_VK_scored': False,
        'threshold_warning': 'Same-sample optimistic separability limits only, not a deployed classifier, validation or quality-gate pass.',
        'finished_utc': datetime.now(timezone.utc).isoformat()}
    write_json(args.output/'feature_report.json', report)
    print('PROFILE_FEATURE_AUDIT_COMPLETE', flush=True)


if __name__ == '__main__': main()
