"""Frozen W4c data protocol; no hardware access."""
import hashlib
import json
from pathlib import Path
import numpy as np

REVISION = 'c7_w4_dma_r1'
PROTOCOL = dict(sizes=[256, 512], repeats=3, warmup=3, samples=100,
                smoke_words=17, total=619, pattern='index-xor-sequence-v1',
                polling='original_A0_r2_1ms', clock_hz=100000000)
HARDWARE = {'a0_dma.bit': 'c27921b683d4c2ec2e1a9d01b34b8d128f6557624d887abce43649767d1fd5af',
            'a0_dma.hwh': 'fa3f7ff7c7d543ca157fcb78d0f2b6af938ce550a49228b23ef4d0eb784f7fde'}
HELPER_SHA = '26d3dda2d0d4f42cccf72927fa339f705b27ca7d35cb2a4e79f2b0fd053cc3d7'


def require(value, message):
    if not value:
        raise ValueError(message)


def info(path):
    b = Path(path).read_bytes()
    return dict(bytes=len(b), sha256=hashlib.sha256(b).hexdigest())


def write_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    tmp.replace(path)


def pattern(words, sequence):
    return np.arange(words, dtype=np.uint32) ^ np.uint32((sequence * 0x9e3779b9) & 0xffffffff)


def word_sha(words):
    return hashlib.sha256(np.asarray(words, dtype='<u4').tobytes()).hexdigest()


def validate(root):
    root = Path(root)
    m = json.loads((root/'w4c_manifest.json').read_bytes())
    require(m['revision'] == REVISION and m['protocol'] == PROTOCOL, 'Wrong W4c protocol')
    require(m['board_status'] == 'BOARD_NOT_RUN', 'Unexpected release status')
    for name, meta in m['artifacts'].items():
        p = Path(name)
        require(not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name, 'Unsafe path')
        require(info(root/p) == meta, 'Package mismatch: '+name)
    for name, sha in HARDWARE.items():
        require(info(root/name)['sha256'] == sha, 'Not trusted A0 r2')
    require(info(root/'a0_dma_board_test.py')['sha256'] == HELPER_SHA, 'Original helper changed')
    return m


def summarize(rows):
    require(len(rows) == 619, 'Incomplete collection')
    require([r['sequence'] for r in rows] == list(range(1, 620)), 'Sequence gap')
    groups = []
    for side in (256, 512):
        for repeat in (1, 2, 3):
            group = [r for r in rows if r['side'] == side and r['repeat'] == repeat]
            require([r['index'] for r in group] == list(range(103)), 'Missing group samples')
            require([r['warmup'] for r in group] == [True]*3+[False]*100, 'Warmup changed')
            metrics = {}
            for key in ('transaction_ns', 'submit_to_observed_idle_ns', 'wait_invalidate_ns', 'snapshot_ns'):
                values = [r[key] for r in group[3:]]
                require(all(type(v) is int and v > 0 for v in values), 'Invalid timestamps')
                metrics[key] = dict(n=100, median_ns=float(np.median(values)), mean_ns=float(np.mean(values)),
                                    p95_ns=float(np.percentile(values, 95)), min_ns=min(values), max_ns=max(values))
            groups.append(dict(side=side, repeat=repeat, metrics=metrics,
                aggregate_payload_MiB_s=2*side*side*4/(1024**2)/(metrics['transaction_ns']['mean_ns']/1e9)))
    return dict(status='COLLECTED_PENDING_INDEPENDENT_AUDIT', groups=groups,
        scope='Separate A0 r2: DDR -> MM2S -> AXIS FIFO -> S2MM -> DDR, no C7 core.',
        timing='Host perf_counter_ns: before recv.transfer through both official waits. Includes TX flush, driver, 1ms polling quantization, RX invalidate. Snapshot separately.',
        exclusions='Not on-chip bus cycles, not C7 DMA minus core, not browser FPS or resident system throughput. Allocation/input/poison/RX flush and evidence writes outside transaction.',
        board_acceptance='PENDING_INDEPENDENT_AUDIT')
