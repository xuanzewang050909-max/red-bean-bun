"""Independent audit of completed CPU Q1-r1 evidence; never a PL claim.

Load the exact committed experiment source snapshot, not later Q1 revisions.
Recreate training RGB/AH/FOV from original archives, every candidate mask and
all confusion counts; a high Dice cannot override the frozen recall gates.
"""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def independent_counts(mask, truth, region):
    tp = int(np.count_nonzero(mask & truth & region))
    fp = int(np.count_nonzero(mask & ~truth & region))
    fn = int(np.count_nonzero(~mask & truth & region))
    tn = int(np.count_nonzero(~mask & ~truth & region))
    return {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn, 'region_pixels': int(region.sum()),
            'dice': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.0,
            'iou': tp / (tp + fp + fn) if tp + fp + fn else 1.0,
            'precision': tp / (tp + fp) if tp + fp else (1.0 if not fn else 0.0),
            'recall': tp / (tp + fn) if tp + fn else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--source-snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Retain earlier review output')
    report = json.loads((args.trial / 'training_report.json').read_bytes())
    provenance = json.loads((args.trial / 'protocol_snapshot.json').read_bytes())
    commit, protocol = report['source_commit'], provenance['protocol']
    require(commit == provenance['source_commit'] and report['candidate_count'] == 64 and report['training_cases'] == 20,
            'Unexpected trial/commit/count')
    for name, expected in provenance['source_sha256'].items():
        require(digest(args.source_snapshot / name) == expected, 'Snapshot source differs: ' + name)
        blob = subprocess.run(['git', 'show', commit + ':' + name], cwd=ROOT, capture_output=True, check=True).stdout
        require(blob == (args.source_snapshot / name).read_bytes(), 'Snapshot does not match original commit')
    require(provenance['decoded_heldout_ids'] == [] and not provenance['vk_opened'] and
            not report['heldout_evaluated'] and not report['VK_evaluated'], 'Annotation boundary differs')
    for name, expected in protocol['frozen_source_sha256'].items():
        require(digest(ROOT / name) == expected, 'Frozen baseline/data changed')
    sys.path.insert(0, str(args.source_snapshot.resolve()))
    from scripts.evaluate_q1_bilateral import read_training_archive, diagnostic_regions, summarize, assess_candidate
    from software.preprocessing import prepare_sample, pack_input
    from software.reference import features, segment
    from software.q1_bilateral import candidates, directional_evidence, support_mask, candidate_mask
    train, heldout = protocol['train_ids'], protocol['heldout_ids_not_decoded']
    images = read_training_archive(ROOT / 'data/raw/stare/stare-images.tar', '', train, train + heldout)
    annotations = read_training_archive(ROOT / 'data/raw/stare/labels-ah.tar', '.ah', train, train + heldout)
    grid = list(candidates())
    require(json.loads(json.dumps(grid)) == report['candidates'] and set(images) == set(annotations) == set(train),
            'Grid or training split changed')
    csv_rows = list(csv.DictReader((args.trial / 'metrics.csv').open(encoding='utf-8')))
    index = {(row['candidate'], row['image_id'], row['side'], row['scope']): row for row in csv_rows}
    require(len(csv_rows) == len(index) == 9100, 'CSV missing or duplicate cases')
    matched_pixels, matched_masks, compared_scores = 0, 0, 0
    seen = set()
    for entry in report['array_records']:
        name = entry['file']
        require(Path(name).name == name and name.endswith('.npz'), 'Unsafe array filename')
        require(name not in seen and digest(args.trial / name) == entry['sha256'], 'Array identity differs')
        seen.add(name)
        sample, side = name.split('_')[:2]
        side = int(side)
        require(sample in train and side in (256, 512), 'Nontraining array')
        with np.load(args.trial / name, allow_pickle=False) as saved:
            rgb, labels, geometry = prepare_sample(images[sample]['pixels'], {'AH': annotations[sample]['pixels'] != 0}, side)
            truth, fov = labels['AH'], labels['fov']
            require(np.array_equal(rgb, saved['rgb']) and np.array_equal(truth, saved['truth_AH']) and
                    np.array_equal(fov, saved['fov']) and geometry == entry['geometry'], 'Original RGB/AH/FOV geometry differs')
            require(entry['image_member_sha256'] == images[sample]['sha256'] and entry['AH_member_sha256'] == annotations[sample]['sha256'],
                    'Original member hashes differ')
            require(hashlib.sha256(pack_input(rgb, fov).astype('<u4').tobytes()).hexdigest() == entry['input_word_sha256'], 'Input packed hash differs')
            feat = features(rgb, fov, 'A')
            require(all(np.array_equal(saved[key], feat[key]) for key in ('enhanced', 'response', 'filtered')), 'Frozen M0 feature differs')
            regions = diagnostic_regions(feat, fov, truth)
            cache = {length: {d: directional_evidence(feat['enhanced'], length, d) for d in (1, 2, 3)} for length in (5, 9)}
            baseline = segment(feat['response'], fov, 28)
            initial = (feat['response'] >= 28) & fov
            for cfg in [None] + grid:
                identifier = 'M0_A28' if cfg is None else cfg['id']
                support = np.ones_like(fov) if cfg is None else support_mask(cache[cfg['length']], cfg['length'],
                          cfg['distances'], cfg['margin'], cfg['persistence'])
                expected = baseline if cfg is None else candidate_mask(feat['response'], fov, support)
                require(saved[identifier].dtype == np.uint8 and saved[identifier].shape == (side * side // 8,), 'Packed mask shape differs')
                mask = np.unpackbits(saved[identifier]).reshape(side, side).astype(bool)
                require(np.array_equal(mask, expected), 'Stored CPU candidate mask differs from committed model')
                require(hashlib.sha256(mask.astype(np.uint8).tobytes()).hexdigest() == entry['mask_sha256'][identifier], 'Mask hash differs')
                require(not (mask & ~baseline).any() and not (mask & ~fov).any(), 'Candidate violates subset/original FOV')
                matched_pixels += side * side
                matched_masks += 1
                for scope, region in {**regions, 'initial_fov': fov}.items():
                    observed = independent_counts(initial & support if scope == 'initial_fov' else mask, truth, region)
                    require(observed == report['scores'][identifier][str(side)]['per_image'][sample][scope], 'Independent confusion count/metric differs')
                    row = index[(identifier, sample, str(side), scope)]
                    require(row['annotation'] == 'AH_TRAIN' and all(row[key] == '' if value is None else float(row[key]) == value
                            for key, value in observed.items()), 'CSV metric differs')
                    compared_scores += 1
        print('Q1_INDEPENDENT_CASE_VERIFIED', sample, side, flush=True)
    require(len(seen) == 20 and matched_masks == 1300 and matched_pixels == 212992000 and compared_scores == 9100, 'Incomplete independent coverage')
    for candidate, sizes in report['scores'].items():
        for side, entry in sizes.items():
            require(summarize(entry['per_image']) == entry['summary'], 'Macro/pooled summary differs')
    eligible = []
    for cfg in grid:
        checked = assess_candidate(report['scores'][cfg['id']], report['scores']['M0_A28'], protocol['selection_gates'])
        require(checked == report['assessments'][cfg['id']], 'Frozen selection gate differs')
        if checked['eligible_for_Q2_feasibility']:
            eligible.append(cfg)
    require(len(eligible) == report['eligible_count'] == 0 and report['selected_candidate'] is None and
            report['decision'] == 'REJECT_R1_FAMILY_FOR_PL', 'Unsafe r1 family was not rejected')
    for name, expected in provenance['preserved_files_before'].items():
        require(digest(ROOT / name) == expected, 'Preserved original runtime/release changed')
    result = {'status': 'INDEPENDENT_CPU_Q1_R1_EVIDENCE_VERIFIED_FAMILY_REJECTED_FOR_PL', 'source_commit': commit,
              'trial': str(args.trial.resolve()), 'matched_cpu_masks': matched_masks, 'matched_cpu_pixels': matched_pixels,
              'independent_confusion_and_csv_rows': compared_scores, 'eligible_count': 0, 'selected_candidate': None,
              'heldout_or_VK_decoded': False, 'production_files_unchanged': True,
              'new_PL_algorithm_verified': False, 'new_board_performance': None,
              'source_sha256': digest(Path(__file__)), 'training_report_sha256': digest(args.trial / 'training_report.json')}
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(result['status'], matched_masks, 'CPU masks;', matched_pixels, 'pixels;', compared_scores, 'rows', flush=True)


if __name__ == '__main__':
    main()
