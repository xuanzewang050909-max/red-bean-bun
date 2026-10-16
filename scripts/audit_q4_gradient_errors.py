"""Post-screen fixed ablations only; no new candidate or held-out evaluation."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_q1_bilateral import require, sha, write_json


def count(mask, truth):
    return {'tp': int((mask & truth).sum()), 'fp': int((mask & ~truth).sum())}


def main():
    source = ROOT/'build/q4_gradient_2026-10-14_r4'
    previous = ROOT/'build/q4_fusion_2026-10-14_r3'
    output = ROOT/'build/q4_gradient_error_audit_2026-10-14'
    require(not output.exists(), 'Preserve previous audit')
    report = json.loads((source/'training_report.json').read_text())
    old = json.loads((previous/'training_report.json').read_text())
    for directory in (source, previous):
        verified = json.loads((directory/'independent_verification.json').read_text())
        require(verified['experiment_report_sha256'] == sha(directory/'training_report.json'), 'Unverified input')
    require(report['eligible_count'] == old['eligible_count'] == 0, 'Rejected experiment diagnosis only')
    # Fixed same upstream r3 retention rule as the r4 union arm, not a new grid.
    old_name = 'C5_l5_9_r8_m1_noadd'
    names = ['C6_r2_gradient_noadd', 'C6_r2_union_noadd', 'C6_r4_gradient_noadd', 'C6_r4_union_noadd']
    cases = {}; panels = None
    for record in report['array_records']:
        image_id, side = record['file'].split('_')[:2]
        earlier = next(x for x in old['array_records'] if x['file'] == record['file'])
        require(sha(source/record['file']) == record['sha256'], 'Changed new array')
        require(sha(previous/record['file']) == earlier['sha256'], 'Changed old array')
        with np.load(source/record['file'], allow_pickle=False) as z, np.load(previous/record['file'], allow_pickle=False) as q:
            for field in ('rgb', 'truth_AH', 'fov', 'filtered', 'C2'):
                require(np.array_equal(z[field], q[field]), 'Different case geometry or input')
            truth, fov = z['truth_AH'], z['fov']
            def mask(container, name):
                return np.unpackbits(container[name])[:fov.size].reshape(fov.shape).astype(bool)
            old_mask, c2 = mask(q, old_name), mask(z, 'C2')
            core = (z['filtered'] >= 192) & fov
            band = cv2.dilate(core.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool) & ~core & fov
            entry = {}
            for name in names:
                current = mask(z, name)
                entry[name] = {region: {
                    'restored_vs_r3_seed': count(current & ~old_mask & area, truth),
                    'removed_vs_r3_seed': count(old_mask & ~current & area, truth),
                    'removed_vs_C2': count(c2 & ~current & area, truth)}
                    for region, area in (('fov', fov), ('bright_band', band))}
            cases[image_id+'_'+side] = entry
            if image_id == 'im0001' and side == '512':
                crop = np.s_[145:385, 180:340]; rgb = z['rgb'][crop]; t = truth[crop]; area = fov[crop]
                panels = [('Input RGB: train im0001', rgb)]
                for title, pred in [('Verified C2 baseline', c2), ('r3 seed: rejected CPU', old_mask),
                                    ('r4 union seed: rejected CPU', mask(z, 'C6_r2_union_noadd'))]:
                    im = (rgb.astype(np.uint16)//5).astype(np.uint8); p = pred[crop]
                    im[p & t & area] = [0, 230, 110]
                    im[p & ~t & area] = [255, 40, 55]
                    im[~p & t & area] = [30, 120, 255]
                    panels.append((title, im))
    pooled = {}
    for side in ('256', '512'):
        entries = [v for k, v in cases.items() if k.endswith('_'+side)]
        pooled[side] = {name: {region: {kind: {field: sum(x[name][region][kind][field] for x in entries)
                    for field in ('tp', 'fp')}
                    for kind in ('restored_vs_r3_seed', 'removed_vs_r3_seed', 'removed_vs_C2')}
                    for region in ('fov', 'bright_band')}
                    for name in names}
    context = {}
    for side in ('256', '512'):
        context[side] = {str(k): report['scores'][f'C6_r2_union_e{k}_g3'][side]['summary']['bridges']
                         for k in (1, 3, 5)}
    output.mkdir()
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 18)
    canvas = Image.new('RGB', (1390, 620), 'white'); draw = ImageDraw.Draw(canvas)
    draw.text((16, 8), 'OFFLINE CPU ERROR AUDIT - ALL NEW CANDIDATES REJECTED - NOT NEW FPGA OUTPUT', font=font, fill='#a02020')
    for i, (title, im) in enumerate(panels):
        x = 16+i*344
        draw.text((x, 44), title, font=font, fill='black')
        canvas.paste(Image.fromarray(im).resize((320, 480), Image.Resampling.NEAREST), (x, 76))
    draw.text((16, 571), 'Green: AH true positive; red: false positive; blue: missed vessel. Same central crop, 512 pixels.', font=font, fill='black')
    draw.text((16, 594), 'r4 protects more labelled vessels but restores too many false candidates. Do not replace the board C2.', font=font, fill='black')
    canvas.save(output/'retention_tradeoff.png')
    result = {'status': 'POST_SCREEN_TRAIN_AH_FIXED_ABLATION_AUDIT', 'board_execution': False,
              'old_seed': old_name, 'new_seeds': names, 'cases': cases, 'pooled': pooled,
              'endpoint_context_fixed_ratio2_union_gap3': context,
              'source_report_sha256': sha(source/'training_report.json'),
              'previous_report_sha256': sha(previous/'training_report.json'),
              'script_sha256': sha(Path(__file__)), 'figure_sha256': sha(output/'retention_tradeoff.png'),
              'note': 'Labels used only for diagnosis. No new candidate prediction, selection, held-out or VK reading.'}
    write_json(output/'audit.json', result)
    print(json.dumps({'pooled': pooled, 'context': context, 'output': str(output)}, indent=2))


if __name__ == '__main__':
    main()
