"""Independent spatial-sum oracle for the committed coefficient tables."""
import numpy as np


def scalar_plane(image, kernel):
    h, w = image.shape; ry, rx = np.array(kernel.shape)//2
    padded = np.pad(image.astype(np.int64), ((ry, ry), (rx, rx)), mode='edge')
    result = np.zeros(image.shape, np.int64)
    for y, x in zip(*np.nonzero(kernel)):
        result += int(kernel[y, x])*padded[y:y+h, x:x+w]
    return result


def oracle(image, bank):
    responses = []; edges = []
    for item in bank:
        planes = []
        for name in ('mf', 'dog'):
            kernel = np.asarray(item[name], np.int32)
            den = sum(int(x) for x in kernel[kernel > 0])
            planes.append((scalar_plane(image, kernel)*256+den//2)//den)
        responses.append(planes[0])
        # Separable sliding sums have the same replicated boundary as 31x31.
        tmp = scalar_plane(planes[1], np.ones((31, 1), np.int32))
        tmp = scalar_plane(tmp, np.ones((1, 31), np.int32))
        edges.append(np.abs((tmp+480)//961))
    shape = image.shape
    best = np.full(shape, np.iinfo(np.int64).min, np.int64)
    direction = np.zeros(shape, np.uint8); edge = np.zeros(shape, np.int64)
    for i, response in enumerate(responses):
        update = response > best
        best[update] = response[update]; direction[update] = i % 8; edge[update] = edges[i][update]
    best = np.maximum(best, 0)
    coherence = np.zeros(shape, np.int64)
    for d in range(8):
        neighbors = (direction == d) | (direction == (d+1)%8) | (direction == (d-1)%8)
        votes = scalar_plane(neighbors & (best > 0), np.ones((7, 7), np.int32))
        coherence[direction == d] = (votes[direction == d]*256+24)//49
    ratio = best*256//(256+edge)
    return {'mf_small': np.maximum(0, np.maximum.reduce(responses[:8])).astype(np.uint16),
            'mf_large': np.maximum(0, np.maximum.reduce(responses[8:])).astype(np.uint16),
            'mf_max': best.astype(np.uint16), 'paired_edge': edge.astype(np.uint16),
            'shape': ratio.astype(np.uint16), 'coherence': coherence.astype(np.uint16),
            'coherent_shape': ((ratio*coherence+128)//256).astype(np.uint16)}


def independent_statistics(hist):
    p, n = [int(row.sum()) for row in hist]
    result = {'positives': p, 'negatives': n, 'prevalence': p/(p+n) if p+n else None,
              'auc': None, 'average_precision': None}
    if not p or not n: return result
    total = hist.sum(axis=0)
    # Mann-Whitney mean ranks, including tied values; a different formulation.
    rank = np.cumsum(total)-(total-1)/2
    result['auc'] = float(((hist[0]*rank).sum()-p*(p+1)/2)/(p*n))
    present = np.flatnonzero(total)[::-1]
    tp = np.cumsum(hist[0, present]); ntotal = np.cumsum(total[present])
    result['average_precision'] = float((tp/ntotal*hist[0, present]).sum()/p)
    return result


def independent_bounds(hist, allowed_loss=None):
    levels = np.flatnonzero(hist.sum(axis=0))[::-1]
    tp = np.cumsum(hist[0, levels]); fp = np.cumsum(hist[1, levels])
    if allowed_loss is not None:
        indices = np.flatnonzero(hist[0].sum()-tp <= allowed_loss)
        if not len(indices): return None
        i = int(indices[0])
        return {'threshold_q8': int(levels[i]), 'retained_tp': int(tp[i]), 'retained_fp': int(fp[i]),
                'removed_tp': int(hist[0].sum()-tp[i]), 'removed_fp': int(hist[1].sum()-fp[i])}
    eligible = np.flatnonzero((tp > 0) & (tp >= 4*fp))
    if not len(eligible): return None
    i = int(eligible[np.argmax(tp[eligible])])
    return {'threshold_q8': int(levels[i]), 'added_tp': int(tp[i]), 'added_fp': int(fp[i]),
            'precision': float(tp[i]/(tp[i]+fp[i]))}


def main():
    import argparse
    import hashlib
    import json
    from pathlib import Path
    import cv2
    from skimage.morphology import skeletonize
    parser = argparse.ArgumentParser(); parser.add_argument('experiment', type=Path); parser.add_argument('output', type=Path)
    a = parser.parse_args(); root = Path(__file__).resolve().parents[1]
    if a.output.exists(): raise RuntimeError('Preserve previous verification')
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report = json.loads((a.experiment/'feature_report.json').read_text())
    prov = json.loads((a.experiment/'provenance.json').read_text()); proto = prov['protocol']
    source = root/proto['input_experiment']; pools = {}; matched = pixels = tables = 0
    assert digest(source/'training_report.json') == proto['source_report_sha256']
    expected_cases = {(i, str(s)) for i in proto['train_ids'] for s in proto['sizes']}
    cases = [tuple(r['input_file'].split('_')[:2]) for r in report['array_records']]
    assert len(cases) == len(expected_cases) and set(cases) == expected_cases
    bright_totals = {str(s): 0 for s in proto['sizes']}
    def same_statistics(actual, expected):
        for key, value in actual.items():
            if value is None: assert expected[key] is None
            else: assert abs(value-expected[key]) < 1e-12, (key, value, expected[key])
    for rec in report['array_records']:
        assert digest(source/rec['input_file']) == rec['input_sha256']
        assert digest(a.experiment/rec['feature_file']) == rec['feature_sha256']
        assert digest(a.experiment/rec['histogram_file']) == rec['histogram_sha256']
        image_id, side = rec['input_file'].split('_')[:2]
        assert image_id in proto['train_ids']
        with np.load(source/rec['input_file'], allow_pickle=False) as z, np.load(a.experiment/rec['feature_file'], allow_pickle=False) as saved, np.load(a.experiment/rec['histogram_file'], allow_pickle=False) as recorded_hist:
            fov, truth = z['fov'], z['truth_AH']
            c2 = np.unpackbits(z['C2'])[:fov.size].reshape(fov.shape).astype(bool)
            core = (z['filtered'] >= 192) & fov
            band = cv2.dilate(core.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool) & ~core & fov
            bright_count = int((band & truth).sum())
            assert bright_count == rec['bright_truth_pixels']
            bright_totals[side] += bright_count
            skeleton = skeletonize(truth & fov, method='zhang')
            _, components = cv2.connectedComponents((skeleton & ~c2).astype(np.uint8), connectivity=8)
            component_sizes = np.bincount(components.ravel()); component_sizes[0] = 0
            long_missing = (components != 0) & (component_sizes[components] > 3)
            near = cv2.dilate(skeleton.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool) & fov & ~truth & ~c2
            areas = {'fov': fov, 'bright_C2': c2 & band, 'outside_C2': fov & ~c2, 'long_missing_vs_near_bg': long_missing | near}
            expected = {'A_response': (z['response'].astype(np.uint16)*256)}
            for branch in ('green', 'filtered'):
                for name, value in oracle(z[branch], proto['coefficient_tables']).items():
                    expected[branch+'_'+name] = 65535-value if name == 'paired_edge' else value
            assert set(expected) == set(saved.files)
            for name, plane in expected.items():
                assert np.array_equal(plane, saved[name]), name
                matched += 1; pixels += plane.size
                for kind, area in areas.items():
                    hist = np.zeros((2, 65536), np.int64)
                    for i, category in enumerate((truth, ~truth)):
                        values, counts = np.unique(plane[area & category], return_counts=True)
                        hist[i, values] = counts
                    assert np.array_equal(hist, recorded_hist[name+'__'+kind])
                    same_statistics(independent_statistics(hist), report['cases'][image_id+'_'+side][name][kind])
                    pools.setdefault(side, {}).setdefault(name, {}).setdefault(kind, np.zeros_like(hist))
                    pools[side][name][kind] += hist
                    tables += 1
        print('PROFILE_INDEPENDENT_CASE_PASS', image_id, side, flush=True)
    assert bright_totals == report['bright_truth_totals']
    for side, byfeature in pools.items():
        with np.load(a.experiment/f'pooled_{side}_histograms.npz', allow_pickle=False) as stored:
            for name, scopes in byfeature.items():
                entry = report['pooled'][side][name]
                for kind, hist in scopes.items():
                    assert np.array_equal(hist, stored[name+'__'+kind])
                    same_statistics(independent_statistics(hist), entry[kind])
                assert independent_bounds(scopes['bright_C2'], report['bright_truth_totals'][side]//50) == entry['optimistic_bright_removal']
                assert independent_bounds(scopes['outside_C2']) == entry['optimistic_outside_addition_at_80pct']
    for path, checksum in prov['protected_before'].items(): assert digest(root/path) == checksum
    result = {'status': 'INDEPENDENT_FEATURES_HISTOGRAMS_RANKS_AND_BOUNDS_PASS',
              'matched_feature_planes': matched, 'matched_feature_values': pixels,
              'case_histogram_tables': tables, 'production_files_unchanged': len(prov['protected_before']),
              'report_sha256': digest(a.experiment/'feature_report.json'), 'verifier_sha256': digest(Path(__file__)),
              'source_commit': report['source_commit'], 'board_execution': False, 'new_segmentation_candidates': 0}
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__': main()
