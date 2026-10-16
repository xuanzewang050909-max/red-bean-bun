"""Frozen image-grouped training screen for C7. Offline fitting only, never PL evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from software.q4d_features import integer_features
from software.q4d_forest import export_forest, predict_integer
from software.continuity_metrics import continuity
from scripts.evaluate_q1_bilateral import diagnostic_regions, score_mask, summarize, sha, write_json, require
from scripts.evaluate_q4_refinement import protected

PROTOCOL = 'docs/q4d_detector_protocol_r1.json'


def metrics(mask, data):
    truth, fov = data['truth'], data['fov']
    r = {k: score_mask(mask, truth, area) for k, area in data['regions'].items()}
    r['continuity'] = continuity(mask, truth, fov)
    c5 = data['C5']
    r['change_from_C5'] = dict(added_tp=int((mask & ~c5 & truth).sum()),
        added_fp=int((mask & ~c5 & ~truth).sum()), removed_tp=int((c5 & ~mask & truth).sum()),
        removed_fp=int((c5 & ~mask & ~truth).sum()))
    return r


def aggregate(items):
    result = summarize(items)
    result['continuity'] = {k: float(np.mean([x['continuity'][k] for x in items.values()]))
        for k in ('cldice', 'topology_precision', 'topology_recall', 'adjacent_edge_coverage')}
    result['change_from_C5'] = {k: sum(x['change_from_C5'][k] for x in items.values())
        for k in ('added_tp', 'added_fp', 'removed_tp', 'removed_fp')}
    return result


def run(destination):
    protocol = json.loads((ROOT / PROTOCOL).read_bytes())
    require(not destination.exists(), 'Use new output; preserve earlier runs')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    for name in protocol['sources'] + [PROTOCOL]:
        # Text Git normalization does not change the reviewed program.
        blob = subprocess.check_output(['git', 'show', commit + ':' + name], cwd=ROOT)
        require(blob.replace(b'\r\n', b'\n') == (ROOT / name).read_bytes().replace(b'\r\n', b'\n'), 'Uncommitted source: ' + name)
    require(sklearn.__version__ == protocol['sklearn_version'], 'Unexpected sklearn version')
    source = ROOT / protocol['input_experiment']
    require(sha(source / 'training_report.json') == protocol['input_report_sha256'], 'Source changed')
    old = json.loads((source / 'training_report.json').read_bytes())
    verification = json.loads((source / 'independent_verification.json').read_bytes())
    require(verification['experiment_report_sha256'] == protocol['input_report_sha256'], 'Unverified source')
    old_split = json.loads((ROOT / 'results/m0_stare_2026-10-11/evaluation.json').read_bytes())['split']
    require(protocol['train_ids'] == old_split['train'], 'Training split changed')
    require(sorted(sum(protocol['folds'], [])) == sorted(protocol['train_ids']), 'Invalid image folds')
    before = protected(); destination.mkdir(parents=True)
    write_json(destination / 'provenance.json', dict(source_commit=commit, protocol=protocol,
        sources={s: sha(ROOT / s) for s in protocol['sources'] + [PROTOCOL]}, protected_before=before,
        status='CPU_GROUPED_TRAINING_NOT_PL', started_utc=datetime.now(timezone.utc).isoformat(),
        heldout_decoded=False, VK_decoded=False, label_use='Original train AH for offline fitting/evaluation only; no label input to inference.'))
    data = {}; feature_names = None; sample_x = {}; sample_y = {}
    for index, record in enumerate(old['array_records']):
        image, side = record['file'].split('_')[:2]
        require(image in protocol['train_ids'] and side in ('256', '512'), 'Forbidden case')
        require(sha(source / record['file']) == record['sha256'], 'Changed input arrays')
        with np.load(source / record['file'], allow_pickle=False) as z:
            names, features = integer_features(z['green'])
            require(feature_names is None or feature_names == names, 'Feature schema changed')
            feature_names = names
            fov, truth = z['fov'].astype(bool), z['truth_AH'].astype(bool)
            record_data = dict(features=features, fov=fov, truth=truth,
                regions=diagnostic_regions({'filtered': z['filtered']}, fov, truth),
                C5=np.unpackbits(z[protocol['c5_key']])[:fov.size].reshape(fov.shape).astype(bool),
                C2=np.unpackbits(z['C2'])[:fov.size].reshape(fov.shape).astype(bool),
                A=np.unpackbits(z['A'])[:fov.size].reshape(fov.shape).astype(bool))
            data[(image, side)] = record_data
            rng = np.random.default_rng(protocol['random_seed'] + index)
            available = np.flatnonzero(fov)
            selected = rng.choice(available, size=min(len(available), protocol['samples_per_image_size']), replace=False)
            sample_x[(image, side)] = features.reshape(-1, len(names))[selected]
            sample_y[(image, side)] = truth.ravel()[selected].astype(np.uint8)
            np.save(destination / f'{image}_{side}_training_indices.npy', selected, allow_pickle=False)
        print('C7_FEATURES_READY', image, side, len(names), flush=True)
    require(len(data) == 20, 'Missing training cases')
    scores = {name: {s: {'per_image': {}} for s in ('256', '512')} for name in ('A', 'C2', 'C5')}
    for (image, side), case in data.items():
        for name in scores:
            scores[name][side]['per_image'][image] = metrics(case[name], case)
    candidate_names = []
    for depth in protocol['depths']:
        for t in protocol['score_thresholds']:
            name = f'C7_d{depth}_t{t}'; candidate_names.append(name)
            scores[name] = {s: {'per_image': {}} for s in ('256', '512')}
        for fold_index, held_images in enumerate(protocol['folds']):
            fit_keys = [k for k in data if k[0] not in held_images]
            x = np.concatenate([sample_x[k] for k in fit_keys]); y = np.concatenate([sample_y[k] for k in fit_keys])
            clf = RandomForestClassifier(n_estimators=protocol['trees'], max_depth=depth,
                min_samples_leaf=protocol['min_samples_leaf'], max_features=protocol['max_features'],
                class_weight={0: 1, 1: protocol['vessel_weight']}, n_jobs=2,
                random_state=protocol['random_seed'] + fold_index, bootstrap=True).fit(x, y)
            model = export_forest(clf, feature_names)
            write_json(destination / f'd{depth}_fold{fold_index}_model.json', model)
            for (image, side), case in data.items():
                if image not in held_images:
                    continue
                prediction = predict_integer(case['features'], model)
                np.save(destination / f'{image}_{side}_d{depth}_oof_score.npy', prediction, allow_pickle=False)
                for t in protocol['score_thresholds']:
                    scores[f'C7_d{depth}_t{t}'][side]['per_image'][image] = metrics((prediction >= t) & case['fov'], case)
            print('C7_GROUPED_FOLD_COMPLETE', depth, fold_index, held_images, flush=True)
    for name in scores:
        for side, obj in scores[name].items():
            require(len(obj['per_image']) == 10, 'Incomplete OOF coverage')
            obj['summary'] = aggregate(obj['per_image'])
    decisions = {}
    for name in candidate_names:
        deficits, deltas = [], {}
        for side in ('256', '512'):
            c = scores[name][side]['summary']; b = scores['C5'][side]['summary']
            d = dict(dice=c['macro_fov']['dice']-b['macro_fov']['dice'],
                thin_recall=c['pooled']['thin_label_proxy']['recall']-b['pooled']['thin_label_proxy']['recall'],
                bright_recall=c['pooled']['bright_band']['recall']-b['pooled']['bright_band']['recall'],
                bright_fp_reduction=1-c['pooled']['bright_band']['fp']/b['pooled']['bright_band']['fp'],
                skeleton_recall=c['continuity']['topology_recall']-b['continuity']['topology_recall'],
                cldice=c['continuity']['cldice']-b['continuity']['cldice'])
            for field, minimum in protocol['minimum_deltas'][side].items():
                if d[field] < minimum:
                    deficits.append(side + ':' + field)
            deltas[side] = d
        # A transparent ranking, not an automatic quality acceptance.
        rank = sum(scores[name][side]['summary']['macro_fov']['dice'] +
                   scores[name][side]['summary']['continuity']['cldice'] for side in ('256', '512'))
        decisions[name] = dict(eligible_for_experimental_review=not deficits, unmet=deficits, deltas=deltas, rank=rank)
    ranked = sorted(candidate_names, key=lambda n: (bool(decisions[n]['unmet']), -decisions[n]['rank'], n))
    require(protected() == before, 'Protected source changed')
    report = dict(status='C7_GROUPED_TRAIN_SCREEN_COMPLETE_NOT_PL', source_commit=commit,
        protocol_sha256=sha(ROOT / PROTOCOL), feature_names=feature_names, scores=scores,
        decisions=decisions, ranked=ranked, selected_for_review=ranked[0],
        independently_unseen_external_validation=False, heldout_or_VK_used=False,
        new_hardware_status='NOT_IMPLEMENTED', protected_unchanged=True,
        warning='Old train images reused, grouped OOF only for new forest fitting. No external generalization or PL claim.')
    write_json(destination / 'training_report.json', report)
    print('C7_TRAINING_COMPLETE', ranked[0], decisions[ranked[0]], flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); run(args.output)
