"""Validated requests and data-only package access, without FPGA or GT evaluation."""
import hashlib
import json
import re
from pathlib import Path

import numpy as np

REVISION = 'browser_a4_w1_r1_fixed28_real_dma'
MODES = {'bypass': 0, 'threshold_candidate': 1, 'closed_candidate': 2, 'final': 3}


class RequestError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_info(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': sha(data)}


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def validate_package(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'browser_manifest.json').read_bytes())
    require(manifest.get('revision') == REVISION and manifest.get('board_status') == 'NOT_RUN', 'Wrong browser release')
    expected = {'pynq_app/' + name + '.py' for name in ('__init__', 'protocol', 'hardware', 'evaluation', 'service', 'launch')}
    expected.update({'ui/index.html', 'ui/style.css', 'ui/app.js'})
    expected.update(manifest['baseline_original_files'])
    for sides in manifest['images'].values():
        for entry in sides.values():
            expected.add(entry['input'])
            expected.update(spec['path'] for spec in entry['evaluation_only'].values())
    require(set(manifest['artifacts']) == expected, 'Incomplete/unexpected package inventory')
    for name, info in manifest['artifacts'].items():
        require(re.fullmatch(r'[A-Za-z0-9_./-]+|使用说明\.txt', name) is not None and
                not name.startswith('/') and '..' not in Path(name).parts, 'Unsafe manifest path')
        require(file_info(root / name) == info, 'Package mismatch: ' + name)
    baseline = json.loads((root / 'a4_manifest.json').read_bytes())
    require(file_info(root / 'a4_manifest.json') == manifest['baseline_manifest'], 'A4 release changed')
    require(baseline['revision'] == 'a4_segmentation_r1_vendor_morphology', 'Wrong A4 hardware')
    for name, info in baseline['artifacts'].items():
        require(file_info(root / name) == info, 'Original A4 bytes changed: ' + name)
    require(set(manifest['baseline_original_files']) == set(baseline['artifacts']) | {'a4_manifest.json'}, 'Original A4 inventory differs')
    require(all(file_info(root / name) == info for name, info in manifest['baseline_original_files'].items()), 'Original 12-file snapshot differs')
    return manifest


class Inputs:
    """RGB/FOV/packed inputs only. Ground truth is not opened by this class."""
    def __init__(self, root, catalog):
        self.root = Path(root)
        self.catalog = catalog

    def public_images(self):
        return [{'image_id': name, 'sides': sorted(int(side) for side in sides)}
                for name, sides in sorted(self.catalog.items())]

    def request(self, body):
        if not isinstance(body, dict) or set(body) != {'image_id', 'side', 'threshold', 'mode', 'client_nonce'}:
            raise RequestError('Required fields: image_id, side, threshold, mode, client_nonce')
        image_id, side, mode, nonce = (body[key] for key in ('image_id', 'side', 'mode', 'client_nonce'))
        if not isinstance(image_id, str) or image_id not in self.catalog or type(side) is not int or str(side) not in self.catalog[image_id]:
            raise RequestError('Choose an available image and 256/512 resolution')
        if type(body['threshold']) is not int or body['threshold'] != 28:
            raise RequestError('This verified A4 firmware supports threshold 28 only')
        if not isinstance(mode, str) or mode not in MODES:
            raise RequestError('Choose an existing PL processing mode; algorithm B is not implemented')
        if not isinstance(nonce, str) or re.fullmatch(r'[A-Za-z0-9_-]{8,80}', nonce) is None:
            raise RequestError('Invalid client nonce')
        return {**body, 'algorithm': 'A', 'mode_code': MODES[mode]}

    def load(self, request):
        entry = self.catalog[request['image_id']][str(request['side'])]
        path = self.root / entry['input']
        require(file_info(path) == entry['input_file'], 'Input file changed')
        words = np.load(path, allow_pickle=False)
        side = request['side']
        require(words.dtype == np.dtype('<u4') and words.shape == (side, side) and np.all((words >> 24) <= 1),
                'Invalid RGB/FOV input format')
        require(sha(words.tobytes()) == entry['input_word_sha256'], 'Input word hash changed')
        words.setflags(write=False)
        return words, entry


def rgb_from_input(words):
    return np.stack([(words >> 16) & 255, (words >> 8) & 255, words & 255], axis=2).astype(np.uint8)
