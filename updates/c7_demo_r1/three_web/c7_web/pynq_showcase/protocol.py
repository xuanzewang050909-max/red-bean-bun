"""Validated requests and data-only package access, without FPGA or GT evaluation."""
import hashlib
import json
import re
from pathlib import Path

import numpy as np

REVISION = 'c7_showcase_r1'
MODES = {'bypass': 0, 'threshold_candidate': 1, 'closed_candidate': 2, 'final': 3}
PNG_PROFILES = {'baseline': {}, 'fast': {'compress_level': 1}}


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
    require(manifest.get('revision') == REVISION and manifest.get('board_status') == 'NOT_RUN', 'Wrong Q4d release')
    require(manifest.get('png_profiles') == PNG_PROFILES, 'Wrong PNG comparison settings')
    expected = {'pynq_showcase/' + name + '.py' for name in ('__init__', 'protocol', 'hardware', 'evaluation', 'service', 'launch', 'quality_observer')}
    expected.update({'ui/index.html', 'ui/style.css', 'ui/app.js'})
    expected.update({'q4d_detector.bit', 'q4d_detector.hwh', 'q4d_hardware_manifest.json', 'a0_dma_board_test.py'})
    expected.update({'integration.json', 'pynq_showcase/single_image.py'})
    config = json.loads((root/'integration.json').read_bytes())
    require(config['schema'] == 'c7-targeted-images-web-v1' and config['side'] == 512
            and config['algorithm_name'] == 'C7' and config['threshold'] == 112,
            'Wrong targeted-image contract')
    require(set(config['payload_manifests'])=={'refinement','refinement_single'},'PAYLOAD_SCOPE')
    for folder, binding in config['payload_manifests'].items():
        expected.add(folder+'/manifest.json')
        require(file_info(root/folder/'manifest.json')=={k:binding[k] for k in ('bytes','sha256')},'FROZEN_PAYLOAD_MANIFEST')
        refinement=json.loads((root/folder/'manifest.json').read_bytes())
        if folder=='refinement':
            require(refinement['algorithm']=='three-image-vessel-completion-v1' and refinement['clock_mhz']==50 and
                    refinement['hardware_release']=='OFFLINE_PHYSICAL_GATES_PASS','Wrong three-image release')
        else:
            require(refinement['release_revision']=='RESET_FIXED_R2','Wrong preserved im0324 release')
        expected.update(folder+'/'+name for name in refinement['files'])
        for name, info in refinement['files'].items():
            path=(root/folder/name).resolve()
            require((root/folder).resolve() in path.parents,'Unsafe refinement path')
            require(file_info(path)=={k:info[k] for k in ('bytes','sha256')},'Refinement mismatch: '+folder+'/'+name)
    require(set(config['targets'])=={'im0004','im0291','im0319','im0324'},'TARGET_SCOPE')
    require(len({t['input_word_sha256'] for t in config['targets'].values()})==4,'DUPLICATE_TARGET')
    for key,profile in [('im0004',0),('im0291',1),('im0319',2),('im0324',None)]:
        target=config['targets'][key]
        require(target['image_id']==key and target['profile']==profile,'PROFILE_BINDING')
        require(target['payload']==('refinement_single' if profile is None else 'refinement'),'PROFILE_PAYLOAD')
        require(target['input_word_sha256']==manifest['images'][key]['512']['input_word_sha256'],'TARGET_INPUT_IDENTITY')
    for sides in manifest['images'].values():
        for entry in sides.values():
            expected.add(entry['input'])
            expected.update(spec['path'] for spec in entry['evaluation_only'].values())
    require(set(manifest['artifacts']) == expected, 'Incomplete/unexpected Q4d inventory')
    for name, info in manifest['artifacts'].items():
        require(re.fullmatch(r'[A-Za-z0-9_./-]+', name) is not None and
                not name.startswith('/') and '..' not in Path(name).parts, 'Unsafe manifest path')
        require(file_info(root / name) == info, 'Package mismatch: ' + name)
    hardware = json.loads((root / 'q4d_hardware_manifest.json').read_bytes())
    require(hardware['revision'] == 'q4d_rq71_c7_experimental_r1' and hardware['board_status'] == 'NOT_RUN', 'Wrong Q4d hardware release')
    require(hardware['hardware_clock_hz'] == 100000000 and hardware['observer_identity'] == 0x52513731, 'Wrong Q4d ABI/clock')
    for name in ('q4d_detector.bit', 'q4d_detector.hwh', 'a0_dma_board_test.py', 'pynq_showcase/quality_observer.py'):
        require(file_info(root / name) == hardware['artifacts'][name.replace('pynq_showcase/', 'pynq_q4d/')], 'Paired hardware source changed: ' + name)
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
        if not isinstance(body, dict) or set(body) != {'image_id', 'side', 'threshold', 'mode', 'algorithm', 'client_nonce', 'png_profile'}:
            raise RequestError('Required fields: image_id, side, threshold, mode, algorithm, client_nonce, png_profile')
        if not isinstance(body['png_profile'], str) or body['png_profile'] not in PNG_PROFILES:
            raise RequestError('Choose baseline or fast lossless PNG delivery')
        image_id, side, mode, nonce = (body[key] for key in ('image_id', 'side', 'mode', 'client_nonce'))
        if not isinstance(image_id, str) or image_id not in self.catalog or type(side) is not int or str(side) not in self.catalog[image_id]:
            raise RequestError('Choose an available image and 256/512 resolution')
        if type(body['threshold']) is not int or not 1 <= body['threshold'] <= 255:
            raise RequestError('Choose an integer PL threshold from 1 to 255')
        if not isinstance(mode, str) or mode not in MODES:
            raise RequestError('Choose an existing PL processing mode; algorithm B is not implemented')
        if not isinstance(nonce, str) or re.fullmatch(r'[A-Za-z0-9_-]{8,80}', nonce) is None:
            raise RequestError('Invalid client nonce')
        if body['algorithm'] not in ('A', 'C2', 'C5', 'C7'):
            raise RequestError('Choose algorithm A, C2, C5 or experimental C7')
        if body['algorithm'] == 'C7' and mode not in ('bypass','final'):
            raise RequestError('C7 supports final mask or bypass; use A/C2/C5 to inspect old intermediate stages')
        return {**body, 'mode_code': MODES[mode]}

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
