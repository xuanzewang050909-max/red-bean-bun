"""Q2 support probe RTL vectors; diagnostic/training intermediates, no GT read.

The integer dense-correlation oracle is independent of the new HLS functor.
These are module vectors, not complete PL segmentation or new quality scores.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_q1_training import independent_selected_response

SYNTHETIC = [(32, pattern) for pattern in range(22)] + [
    (256, 21), (512, 17), (256, 20), (512, 21), (32, 18)]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def diagnostic(side, pattern, rng):
    y, x = np.indices((side, side))
    cy = cx = side // 2
    conditions = {
        2: (x < cx, 0, 255), 3: (y < cy, 255, 0),
        4: (x + y < side, 0, 255), 5: (x - y < 0, 255, 0),
        6: (y == cy, 80, 180), 7: (x == cx, 80, 180),
        8: (x == y, 80, 180), 9: (x + y == side - 1, 80, 180),
        10: (np.abs(x - cx) <= 3, 80, 180),
        11: (np.abs(y - cy) <= 4, 80, 180),
        12: ((x == cx) | (y == cy) | (x == y), 80, 180),
        13: ((x + y) & 1, 255, 0),
        14: ((x == 0) | (y == 0) | (x == side - 1) | (y == side - 1), 0, 255),
        15: (((x == 0) & (y == 0)) | ((x == side - 1) & (y == side - 1)), 0, 255),
        16: ((np.abs(x - cx) <= 4) & (np.abs(y - cy) <= 8), 245, 100),
        18: (y == cy, 179, 180), 19: ((y == cy) & (x != cx), 179, 180),
    }
    if pattern in (0, 1):
        enhanced = np.full((side, side), pattern * 255, np.uint8)
    elif pattern in conditions:
        enhanced = np.where(*conditions[pattern]).astype(np.uint8)
    elif pattern == 17:
        enhanced = np.where(y == cy, 30, np.where(np.abs(x - cx) <= 6, 245, 130)).astype(np.uint8)
    elif pattern == 20:
        enhanced = ((x * 11 + y * 17) & 255).astype(np.uint8)
    elif pattern == 21:
        def values():
            for _ in range(side * side):
                state = rng[0]
                state = (state ^ (state << 13)) & 0xffffffff
                state = (state ^ (state >> 17)) & 0xffffffff
                state = (state ^ (state << 5)) & 0xffffffff
                rng[0] = state
                yield state & 255
        enhanced = np.fromiter(values(), np.uint8).reshape(side, side)
    else:
        raise ValueError('Unknown diagnostic')
    response = np.take(np.array([0, 1, 27, 28, 29, 55, 56, 255], np.uint8),
                       np.arange(side * side) % 8).reshape(side, side)
    tag = ((np.arange(side * side, dtype=np.uint32) * 137 + pattern * 31) & 65535).reshape(side, side)
    return enhanced, response, tag


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    require_new = not args.destination.exists() or not any(args.destination.iterdir())
    if not require_new:
        raise ValueError('Preserve earlier vector evidence')
    args.destination.mkdir(parents=True, exist_ok=True)
    frozen = json.loads((ROOT / 'results/q1_quality_2026-10-14/selected_candidate.json').read_text(encoding='utf-8'))
    candidate = frozen['candidate']
    assert candidate == {'id': 'C2_l9_d12345_m1_p28', 'length': 9,
                         'distances': [1, 2, 3, 4, 5], 'margin': 1,
                         'persistence': 'none', 'penalty': 28}
    records = []

    def save(enhanced, response, tag, metadata):
        support_response = independent_selected_response(enhanced, np.full(enhanced.shape, 255, np.uint8), candidate)
        support = support_response == 255
        softened = independent_selected_response(enhanced, response, candidate)
        assert np.array_equal(softened, np.maximum(0, response.astype(np.int32) - (~support) * 28))
        source = enhanced.astype(np.uint32) | (response.astype(np.uint32) << 8) | (tag << 16)
        expected = softened.astype(np.uint32) | (support.astype(np.uint32) << 8) | (tag << 16)
        index = len(records) + 1
        for suffix, data in (('input', source), ('expected', expected)):
            np.savetxt(args.destination / f'case_{index:02d}_{suffix}.hex', data.reshape(-1), fmt='%08x')
        record = {'case': index, 'side': enhanced.shape[0], 'words': source.size,
                  'input_sha256': digest(source.astype('<u4').tobytes()),
                  'expected_sha256': digest(expected.astype('<u4').tobytes()),
                  'enhanced_sha256': digest(enhanced.tobytes()),
                  'original_response_sha256': digest(response.tobytes()),
                  'support_pixels': int(support.sum()), 'labels_used': False, **metadata}
        records.append(record)
        print('Q2_SUPPORT_VECTOR_READY', index, metadata['kind'], enhanced.shape[0], flush=True)

    rng = [0x2c241014]
    for side, pattern in SYNTHETIC:
        save(*diagnostic(side, pattern, rng), {'kind': 'synthetic', 'pattern': pattern})
    trial = ROOT / 'build/q1_soft_support_2026-10-14_r2'
    training = json.loads((trial / 'training_report.json').read_text(encoding='utf-8'))
    assert training['selected_candidate'] == candidate
    for artifact in training['array_records']:
        path = trial / artifact['file']
        assert digest(path.read_bytes()) == artifact['sha256']
        image_id, side, *_ = path.stem.split('_')
        assert image_id in frozen['training_ids'] and side in ('256', '512')
        # Do not read RGB, AH, VK or held-out inputs here. E/A are existing Q1 intermediates.
        with np.load(path, allow_pickle=False) as arrays:
            enhanced, response = arrays['enhanced'], arrays['response']
        tag = ((np.arange(enhanced.size, dtype=np.uint32) * 137 + len(records) * 31) & 65535).reshape(enhanced.shape)
        save(enhanced, response, tag, {'kind': 'training_intermediate', 'image_id': image_id,
                                      'source_npz_sha256': artifact['sha256'], 'source_npz_file': str(path)})
    assert len(records) == 47
    files = {p.name: digest(p.read_bytes()) for p in args.destination.glob('*.hex')}
    manifest = {'status': 'Q2_SUPPORT_MODULE_VECTORS_ONLY_NOT_BOARD_RESULTS',
                'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'candidate': candidate, 'cases': records, 'hex_file_sha256': files,
                'completed_frame_words': sum(r['words'] for r in records),
                'training_intermediate_pixels': sum(r['words'] for r in records if r['kind'] == 'training_intermediate'),
                'heldout_decoded': False, 'annotation_arrays_loaded': False, 'board_test_status': 'NOT_RUN'}
    (args.destination / 'vector_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('Q2_SUPPORT_VECTORS_READY:', len(records), 'cases;', manifest['completed_frame_words'], 'words; no GT')


if __name__ == '__main__':
    main()
