"""Read-only, same-region error audit of verified Q4 real DMA outputs.

Annotations and diagnostic regions are used only here, never to change masks.
All figures are scientific overlays of existing pixels, with nearest scaling.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.morphology import skeletonize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from software.reference import gaussian3
from software.metrics import evaluate
from software.continuity_metrics import continuity

ROI = (180, 145, 340, 385)  # Same half-open rectangle as the original W1 audit.
BINS = [('1', 1, 1), ('2-3', 2, 3), ('4-7', 4, 7),
        ('8-15', 8, 15), ('16+', 16, 2**31 - 1)]


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def missing_components(mask, truth, fov):
    skeleton = skeletonize(truth & fov, method='zhang')
    missed = skeleton & ~mask
    _, _, stats, _ = cv2.connectedComponentsWithStats(missed.astype(np.uint8), connectivity=8)
    sizes = stats[1:, cv2.CC_STAT_AREA]
    bins = {name: {'components': int(((sizes >= lo) & (sizes <= hi)).sum()),
                   'pixels': int(sizes[(sizes >= lo) & (sizes <= hi)].sum())}
            for name, lo, hi in BINS}
    require(sum(x['pixels'] for x in bins.values()) == int(missed.sum()), 'Miss partition')
    return {'truth_skeleton_pixels': int(skeleton.sum()), 'missed_pixels': int(missed.sum()),
            'missed_pixels_in_components_over_three': int(sizes[sizes > 3].sum()), 'bins': bins}


def figure(path, panels, cols, size, footnotes):
    margin, heading = 16, 36
    w, h = size
    rows = (len(panels) + cols - 1) // cols
    canvas = Image.new('RGB', (margin + cols * (w + margin),
                               margin + rows * (h + heading + margin) + 24 * len(footnotes)), 'white')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 17)
    for i, (title, pixels) in enumerate(panels):
        x, y = margin + (i % cols) * (w + margin), margin + (i // cols) * (h + heading + margin)
        draw.text((x, y), title, font=font, fill='black')
        canvas.paste(Image.fromarray(pixels).resize(size, Image.Resampling.NEAREST), (x, y + heading))
    y = margin + rows * (h + heading + margin)
    for line in footnotes:
        draw.text((margin, y), line, font=font, fill='black')
        y += 24
    canvas.save(path)


def run(verified_path, archive_path, package, destination):
    require(not destination.exists(), 'Preserve earlier audit; use a new directory')
    verified = json.loads(verified_path.read_bytes())
    require(verified['status'].startswith('Q4_REAL_PL_DATA_VERIFIED_'), 'Unverified archive')
    require(sha(archive_path.read_bytes()) == verified['archive']['sha256'], 'Archive changed')
    manifest = json.loads((package / 'browser_manifest.json').read_bytes())
    selected = [r for r in verified['runs'][:120]
                if r['request']['image_id'] == 'im0001' and r['request']['side'] == 512]
    require(len(selected) == 3, 'Missing fixed comparisons')
    records = {r['request']['algorithm']: r for r in selected}
    masks = {}
    with zipfile.ZipFile(archive_path) as archive:
        inputs = []
        for alg, r in records.items():
            source = np.load(io.BytesIO(archive.read(r['run_id'] + '/input_packed.npy')), allow_pickle=False)
            output = np.load(io.BytesIO(archive.read(r['run_id'] + '/output_packed.npy')), allow_pickle=False)
            require(source.shape == output.shape == (512, 512), 'Wrong geometry')
            require(sha(source.astype('<u4').tobytes()) == r['input_sha256'], 'Input changed')
            require(sha(output.astype('<u4').tobytes()) == r['output_sha256'], 'Output changed')
            inputs.append(source)
            masks[alg] = ((output >> 16) & 255) != 0
        require(all(np.array_equal(inputs[0], x) for x in inputs), 'Inputs differ')
    source = inputs[0]
    entry = manifest['images']['im0001']['512']
    require(np.array_equal(source, np.load(package / entry['input'], allow_pickle=False)), 'Release input differs')
    # Match the final user screenshot's actual task to the fixed cohort C5 output.
    last = verified['runs'][-1]
    require(all(last['request'][k] == v for k, v in
                dict(image_id='im0001', side=512, algorithm='C5', threshold=28, mode='final').items()),
            'Final screenshot request differs')
    require(last['output_sha256'] == records['C5']['output_sha256'], 'Displayed C5 differs from cohort')
    rgb = np.stack([(source >> 16) & 255, (source >> 8) & 255, source & 255], axis=-1).astype(np.uint8)
    fov = (source >> 24) != 0
    truth, label_sources = {}, {}
    for observer, meta in entry['evaluation_only'].items():
        data = (package / meta['path']).read_bytes()
        require(sha(data) == meta['file']['sha256'], 'GT changed')
        truth[observer] = np.load(io.BytesIO(data), allow_pickle=False).astype(bool)
        label_sources[observer] = meta
    x0, y0, x1, y1 = ROI
    rect = np.zeros_like(fov); rect[y0:y1, x0:x1] = True; rect &= fov
    core = rect & (gaussian3(rgb[..., 1]) >= 192)
    band = cv2.dilate(core.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool) & ~core & rect
    both_negative = ~truth['AH'] & ~truth['VK']
    scopes = dict(original_fov=fov, original_rectangle=rect, original_bright_core=core,
                  original_seven_pixel_square_band=band)
    metrics, missed, changes = {}, {}, {}
    for alg, mask in masks.items():
        metrics[alg] = {name: dict(region_pixels=int(region.sum()), predicted_pixels=int((mask & region).sum()),
            negative_in_both=int((mask & region & both_negative).sum()),
            annotations={o: evaluate(mask, t, region) for o, t in truth.items()})
            for name, region in scopes.items()}
        missed[alg] = {o: missing_components(mask, t, fov) for o, t in truth.items()}
        for o, t in truth.items():
            item = verified['quality']['groups']['train_' + o]['scores'][alg]['512']['per_image']['im0001']
            actual = metrics[alg]['original_fov']['annotations'][o]
            require(all(actual[k] == item['fov'][k] for k in actual), 'Independent confusion counts differ')
            require(continuity(mask, t, fov) == item['continuity'], 'Continuity differs')
    for name, changed in [('added', masks['C5'] & ~masks['C2']), ('removed', masks['C2'] & ~masks['C5'])]:
        changes[name] = {scope: dict(pixels=int((changed & region).sum()), annotations={
            o: dict(labeled_vessel=int((changed & region & t).sum()),
                    labeled_background=int((changed & region & ~t).sum())) for o, t in truth.items()})
            for scope, region in scopes.items()}
    # Same historic diagnostic band must reproduce the A/C2 counts before showing C5.
    require(metrics['A']['original_seven_pixel_square_band']['negative_in_both'] == 3108, 'Historic A ROI differs')
    require(metrics['C2']['original_seven_pixel_square_band']['negative_in_both'] == 2491, 'Historic C2 ROI differs')
    destination.mkdir(parents=True)
    backdrop = (rgb.astype(np.uint16) // 4).astype(np.uint8)
    crop = np.s_[y0:y1, x0:x1]
    panels = []
    for alg in ('C2', 'C5'):
        p = masks[alg]
        real = np.repeat((p.astype(np.uint8) * 255)[..., None], 3, axis=2)
        errors = backdrop.copy()
        errors[p & truth['AH'] & fov] = [40, 220, 80]
        errors[p & ~truth['AH'] & fov] = [255, 45, 45]
        errors[~p & truth['AH'] & fov] = [50, 190, 255]
        bright = backdrop.copy(); bright[core] = [255, 210, 0]; bright[band] = [60, 70, 85]
        bright[p & band & both_negative] = [255, 45, 45]
        count = metrics[alg]['original_seven_pixel_square_band']['negative_in_both']
        panels += [(alg + ': actual DMA mask', real[crop]),
                   (alg + ': AH TP green / FP red / FN cyan', errors[crop]),
                   (alg + f': original band FP* = {count}', bright[crop])]
    figure(destination / 'central_c2_c5_actual.png', panels, 3, (320, 480), [
        'im0001 / 512 / mode 3 / T28. Same old crop and bright-band definition; no masks changed.',
        '*Predicted pixels labeled as background by BOTH AH and VK. Yellow: bright core; gray: band.',
        'Illustrative RGB-defined region, not a lesion label or full-dataset quality acceptance.'])
    panels = [('Input RGB - full field', rgb)]
    skel = skeletonize(truth['AH'] & fov, method='zhang')
    for alg in ('C2', 'C5'):
        view = backdrop.copy()
        view[skel & masks[alg]] = [40, 220, 80]
        view[skel & ~masks[alg]] = [50, 190, 255]
        panels.append((alg + ': AH centerline covered / missed', view))
    for name, p in [('AH manual mask', truth['AH']), ('C2 actual DMA mask', masks['C2']), ('C5 actual DMA mask', masks['C5'])]:
        panels.append((name, np.repeat((p.astype(np.uint8) * 255)[..., None], 3, axis=2)))
    figure(destination / 'continuity_c2_c5_actual.png', panels, 3, (512, 512), [
        'Green: original AH centerline covered by actual PL mask; cyan: missed. Full image at native 512 pixels.',
        'Skeleton color is offline evaluation only. It is NOT a new segmentation output or a line drawn into the PL mask.',
        'Improved clDice does not mean all vessel paths are continuous. AH/VK are separate reference annotations.'])
    result = dict(status='REAL_Q4_C5_RESIDUAL_ERRORS_CONFIRMED_NOT_QUALITY_ACCEPTANCE',
        archive_sha256=verified['archive']['sha256'], verification_sha256=sha(verified_path.read_bytes()),
        script_sha256=sha(Path(__file__).read_bytes()),
        records={alg: dict(run_id=r['run_id'], input_sha256=r['input_sha256'], output_sha256=r['output_sha256']) for alg, r in records.items()},
        final_display_run=dict(run_id=last['run_id'], matches_fixed_c5=True), annotation_sources=label_sources,
        original_rectangle_xyxy=ROI, core_rule='Gaussian3(raw G)>=192 within original rectangle/FOV',
        band_rule='15x15 square dilation(core) minus core within original rectangle/FOV',
        metrics=metrics, actual_c5_vs_c2_pixel_changes=changes, missing_skeleton_components=missed,
        component_limit='8-connected missing GT skeleton component size is NOT straight gap length; can curve, branch, or be wholly missed.',
        figures={p.name: sha(p.read_bytes()) for p in destination.glob('*.png')},
        quality_accepted=False, new_algorithm_implemented=False, production_changed=False,
        scope='Post hoc diagnosis of an existing training-image example, not parameter selection. Figures local research only.')
    (destination / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'bright_band_both_negative': {
        a: m['original_seven_pixel_square_band']['negative_in_both'] for a, m in metrics.items()},
        'missed_skeleton': missed, 'destination': str(destination)}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('verification', type=Path); p.add_argument('archive', type=Path)
    p.add_argument('destination', type=Path)
    p.add_argument('--package', type=Path, default=ROOT / 'build/deploy/q4_c5_experimental_r1')
    args = p.parse_args()
    run(args.verification, args.archive, args.package, args.destination)
