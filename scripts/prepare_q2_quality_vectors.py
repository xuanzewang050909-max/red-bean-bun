"""Independent Q2 full-pipeline RTL vectors, original RGB/FOV and no labels."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from software.preprocessing import prepare_sample, pack_input
from software.reference import gaussian3, LUT, box_mean15, CROSS, morphology, correlate
from scripts.verify_q1_training import independent_selected_response
from scripts.a4_segmentation_board_test import make_pattern

CASES = [(256,0,'A',28,'gradient'),(256,1,'A',28,'random'),(256,2,'A',28,'gradient'),
         (512,3,'A',28,'random'),(256,3,'A',28,'stare'),(512,3,'A',28,'stare'),
         (512,3,'C2',28,'stare'),(256,3,'C2',28,'stare'),(256,1,'C2',27,'fov_edge'),
         (512,2,'C2',29,'fov_edge'),(256,3,'C2',1,'broken_line'),(512,3,'C2',255,'random'),
         (256,0,'C2',28,'vessel_stripes'),(512,3,'C2',28,'bright_cross'),(256,3,'C2',28,'checker'),
         (256,3,'C2',28,'impulse'),(256,3,'C2',28,'random'),(512,3,'C2',28,'black')]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def expected_words(source, stage, algorithm, threshold, candidate):
    if stage == 0:
        return source.copy()
    raw = ((source >> 8) & 255).astype(np.uint8)
    enhanced = LUT[gaussian3(raw)]
    response = np.clip((box_mean15(enhanced).astype(np.int16) - enhanced.astype(np.int16)) * 4, 0, 255).astype(np.uint8)
    if algorithm == 'C2':
        response = independent_selected_response(enhanced, response, candidate)
    fov = (source >> 24) != 0
    initial = (response >= threshold) & fov
    closed = morphology(morphology(initial, CROSS, True), CROSS, False)
    count = correlate(closed.astype(np.uint8), np.ones((3, 3), np.int32))
    final = closed & (count >= 2) & fov
    selected = initial if stage == 1 else closed if stage == 2 else final
    return (raw.astype(np.uint32) | (enhanced.astype(np.uint32) << 8) |
            (selected.astype(np.uint32) * 255 << 16) | (response.astype(np.uint32) << 24))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.destination.exists() and any(args.destination.iterdir()):
        raise ValueError('Preserve earlier full-pipeline vectors')
    args.destination.mkdir(parents=True, exist_ok=True)
    candidate = json.loads((ROOT / 'results/q1_quality_2026-10-14/selected_candidate.json').read_text(encoding='utf-8'))['candidate']
    assert candidate['id'] == 'C2_l9_d12345_m1_p28'
    # Decode only the original training RGB im0001; no GT or held-out imagery.
    from scripts.evaluate_q1_bilateral import read_training_archive
    split = json.loads((ROOT / 'docs/q1_bilateral_protocol_r1.json').read_text(encoding='utf-8'))
    rgb_record = read_training_archive(ROOT / 'data/raw/stare/stare-images.tar', '', ['im0001'],
                                      split['train_ids'] + split['heldout_ids_not_decoded'])['im0001']
    geometry = {}
    for side in (256, 512):
        rgb, aligned, geometry[side] = prepare_sample(rgb_record['pixels'], {}, side)
        np.save(args.destination / f'stare_im0001_{side}.npy', pack_input(rgb, aligned['fov']))
    records = []
    for index, (side, stage, algorithm, threshold, pattern) in enumerate(CASES, start=1):
        if pattern == 'bright_cross':
            y, x = np.indices((side, side), dtype=np.uint32)
            green = np.where((x >= side//3) & (x < 2*side//3) & (y >= side//3) & (y < 2*side//3), 245,
                             120 + ((x*3+y*5) % 30)).astype(np.uint32)
            green = np.where(np.abs(y.astype(np.int32)-side//2) <= 2, 60, green)
            source = (np.uint32(1) << 24) | (np.uint32(100) << 16) | (green << 8) | 37
        else:
            source = make_pattern(side, pattern, index, args.destination)
        expected = expected_words(source, stage, algorithm, threshold, candidate)
        for name, data in (('input', source), ('expected', expected)):
            np.savetxt(args.destination / f'case_{index:02d}_{name}.hex', data.reshape(-1), fmt='%08x')
        record = {'case': index, 'side': side, 'stage': stage, 'algorithm': algorithm, 'threshold': threshold,
                  'pattern': pattern, 'control_word': stage | (4 if side == 256 else 0) | (8 if algorithm == 'C2' else 0) | (threshold << 8),
                  'input_sha256': sha(source.astype('<u4').tobytes()), 'expected_sha256': sha(expected.astype('<u4').tobytes()),
                  'words': source.size, 'labels_used': False, 'complete_frame_expected': index != 17}
        if pattern == 'stare':
            record.update(geometry=geometry[side], original_member_sha256=rgb_record['sha256'])
        records.append(record)
    manifest = {'status': 'Q2_FULL_PIPELINE_RTL_VECTORS_ONLY_NOT_BOARD_EVIDENCE',
                'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'candidate': candidate, 'cases': records,
                'hex_sha256': {p.name: sha(p.read_bytes()) for p in args.destination.glob('*.hex')},
                'complete_frames': 17, 'full_words': sum(r['words'] for r in records if r['complete_frame_expected']),
                'annotation_arrays_loaded': False, 'heldout_decoded': False, 'board_status': 'NOT_RUN'}
    (args.destination / 'vector_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('Q2_QUALITY_VECTORS_READY:', manifest['complete_frames'], 'full frames;', manifest['full_words'], 'words')


if __name__ == '__main__':
    main()
