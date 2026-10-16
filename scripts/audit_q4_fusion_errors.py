"""Post-screen training diagnostics only; no new candidates, scoring or deployment."""
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_q1_bilateral import require, sha, write_json
from software.q4_fusion import fusion_mask
from software.q4_refinement import sample


def counts(mask, truth):
    return {'tp': int((mask & truth).sum()), 'fp': int((mask & ~truth).sum())}


def main():
    source = ROOT / 'build/q4_fusion_2026-10-14_r3'
    output = ROOT / 'build/q4_fusion_error_audit_2026-10-14'
    require(not output.exists(), 'Preserve prior audit')
    report = json.loads((source / 'training_report.json').read_text())
    prov = json.loads((source / 'provenance.json').read_text())
    verification = json.loads((source / 'independent_verification.json').read_text())
    require(verification['experiment_report_sha256'] == sha(source / 'training_report.json'), 'Unverified report')
    require(report['eligible_count'] == 0, 'Diagnostic is for rejected family only')
    # Explicitly a diagnostic display rule, NOT the deployment selection rule.
    name = max(report['assessments'], key=lambda n: (report['scores'][n]['512']['summary']['macro_fov']['dice'], n))
    c = next(c for c in prov['protocol']['candidates'] if c['id'] == name)
    cases = {}; figures = None
    for record in report['array_records']:
        require(sha(source / record['file']) == record['sha256'], 'Changed source arrays')
        image_id, side = record['file'].split('_')[:2]
        with np.load(source / record['file'], allow_pickle=False) as z:
            truth, fov = z['truth_AH'], z['fov']
            c2 = np.unpackbits(z['C2'])[:fov.size].reshape(fov.shape).astype(bool)
            cached = {}
            final, seed, links = fusion_mask({'filtered': z['filtered']}, fov, c2, cached, c)
            stored = np.unpackbits(z[name])[:fov.size].reshape(fov.shape).astype(bool)
            require(np.array_equal(final, stored), 'Diagnostic candidate changed')
            # Every missing pixel is attributed to its best-supported pair of
            # endpoints among all proposing links (labels only in this audit).
            best_endpoints = np.full(fov.shape, -1, np.int8)
            link_groups = {str(k): 0 for k in (0, 1, 2)}
            for dy, dx, gap, anchors in links:
                end_count = truth.astype(np.uint8) + sample(truth, (gap+1)*dy, (gap+1)*dx, 'constant').astype(np.uint8)
                for k in (0, 1, 2):
                    selected = anchors & (end_count == k)
                    link_groups[str(k)] += int(selected.sum())
                    for t in range(1, gap+1):
                        hit = sample(selected, -t*dy, -t*dx, 'constant')
                        best_endpoints[hit] = np.maximum(best_endpoints[hit], k)
            added = final & ~seed
            require(not (added & (best_endpoints < 0)).any(), 'Unexplained added pixel')
            added_groups = {str(k): counts(added & (best_endpoints == k), truth) for k in (0, 1, 2)}
            for field in ('tp', 'fp'):
                require(sum(g[field] for g in added_groups.values()) == counts(added, truth)[field], 'Overlap in pixel groups')
            bright_core = (z['filtered'] >= 192) & fov
            import cv2
            band = cv2.dilate(bright_core.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool) & ~bright_core & fov
            positive = np.zeros_like(fov); balanced = np.zeros_like(fov)
            for rows in cached['r3_multiscale'].values():
                for row in rows:
                    for small, large, _, _ in row:
                        positive |= small > 0
                        balanced |= (small > 0) & (large.astype(np.int32) <= c['ratio'] * small.astype(np.int32))
            removed = c2 & ~final & band
            reasons = {'no_positive_bilateral': ~positive, 'imbalance': positive & ~balanced,
                       'below_retain_margin': balanced}
            removed_groups = {key: counts(removed & mask, truth) for key, mask in reasons.items()}
            cases[image_id + '_' + side] = {'links_by_labeled_endpoint_count': link_groups,
                'added_by_best_labeled_endpoint_count': added_groups,
                'bright_removed_by_feature_reason': removed_groups,
                'bright_removed_total': counts(removed, truth)}
            if image_id == 'im0001' and side == '512':
                crop = np.s_[145:385, 180:340]
                rgb = z['rgb'][crop]; t = truth[crop]; area = fov[crop]
                plots = [('RGB: training example', rgb), ('AH manual vessels', np.repeat(t[..., None]*255, 3, 2).astype(np.uint8))]
                for label, mask in (('Verified C2 baseline', c2), ('Rejected CPU candidate', final)):
                    p = mask[crop]
                    im = (rgb.astype(np.uint16)//5).astype(np.uint8)
                    im[p & t & area] = [0, 230, 110]; im[p & ~t & area] = [255, 40, 55]
                    im[~p & t & area] = [30, 120, 255]
                    plots.append((label, im))
                figures = plots
    output.mkdir()
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 19)
    canvas = Image.new('RGB', (1360, 620), 'white'); draw = ImageDraw.Draw(canvas)
    draw.text((16, 8), 'OFFLINE CPU RESEARCH - REJECTED FOR DEPLOYMENT - NOT A NEW FPGA RESULT', font=font, fill='#a02020')
    for i, (title, im) in enumerate(figures):
        x = 16+i*336
        draw.text((x, 44), title, font=font, fill='black')
        canvas.paste(Image.fromarray(im).resize((320, 480), Image.Resampling.NEAREST), (x, 76))
    draw.text((16, 570), 'Green = true positive; red = false positive; blue = missed vessel. im0001 / 512 / AH / same central crop.', font=font, fill='black')
    draw.text((16, 594), 'A cleaner crop does not override failed full-training bright-vessel protection and connection-precision gates.', font=font, fill='black')
    canvas.save(output / 'rejected_candidate_comparison.png')
    pooled = {}
    for side in ('256', '512'):
        entries = [v for k, v in cases.items() if k.endswith('_' + side)]
        pooled[side] = {
            'links_by_labeled_endpoint_count': {str(k): sum(x['links_by_labeled_endpoint_count'][str(k)] for x in entries) for k in (0, 1, 2)},
            'added_by_best_labeled_endpoint_count': {str(k): {field: sum(x['added_by_best_labeled_endpoint_count'][str(k)][field] for x in entries) for field in ('tp', 'fp')} for k in (0, 1, 2)},
            'bright_removed_by_feature_reason': {reason: {field: sum(x['bright_removed_by_feature_reason'][reason][field] for x in entries) for field in ('tp', 'fp')} for reason in reasons}}
    result = {'status': 'POST_SCREEN_TRAIN_AH_ERROR_AUDIT_NOT_NEW_SELECTION', 'candidate': c,
        'display_rule': 'highest 512 train Dice among rejected candidates, no adoption',
        'annotation': 'train AH only, no heldout or VK', 'source_report_sha256': sha(source / 'training_report.json'),
        'image_sha256': sha(output / 'rejected_candidate_comparison.png'), 'script_sha256': sha(Path(__file__)),
        'cases': cases, 'pooled': pooled, 'note': 'Endpoint classes use annotations for diagnosis ONLY; forbidden as runtime masks or selection features.'}
    write_json(output / 'audit.json', result)
    print(json.dumps({'candidate': name, 'pooled': pooled, 'output': str(output)}, indent=2))


if __name__ == '__main__':
    main()
