"""Data-only validation/statistics shared with the independent download audit."""
import hashlib
import json
from pathlib import Path
import numpy as np

REVISION = 'c7_w4_processing_r1'
REPEATS, WARMUP, SAMPLES = 3, 3, 100
BASELINE_MANIFEST_SHA = '20719cd3376fa4b1a6ee3464a2f10f20b5f4f1b941b2a63e79dde4da19eff8df'


def require(value, message):
    if not value:
        raise ValueError(message)


def info(path):
    data = Path(path).read_bytes()
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def word_sha(words):
    return hashlib.sha256(words.astype('<u4', copy=False).tobytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def validate(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'w4_manifest.json').read_bytes())
    require(manifest['revision'] == REVISION and manifest['board_status'] == 'BOARD_NOT_RUN', 'Wrong W4 package')
    require(info(root / 'c7_baseline/q4d_manifest.json')['sha256'] == BASELINE_MANIFEST_SHA, 'Wrong trusted C7 release')
    for name, value in manifest['artifacts'].items():
        p = Path(name)
        require(not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name, 'Unsafe package path')
        require(info(root / p) == value, 'Package mismatch: ' + name)
    require(manifest['protocol'] == dict(sizes=[256, 512], repeats=3, warmup=3, samples=100,
        image_id='im0001', algorithm='C7', mode_code=3, threshold=112), 'Performance protocol changed')
    return manifest


def group_order(repeat):
    return ('CPU', 'PL') if repeat % 2 else ('PL', 'CPU')


def stats(values):
    require(len(values) == SAMPLES and all(type(x) is int and x > 0 for x in values), 'Need exactly 100 positive measured samples')
    return dict(n=len(values), mean_ns=float(np.mean(values)), median_ns=float(np.median(values)),
                p95_ns=float(np.percentile(values, 95)), min_ns=min(values), max_ns=max(values))


def summarize(rows, group_records):
    require(len(rows) == 2 * 2 * REPEATS * (WARMUP + SAMPLES), 'Incomplete suite')
    groups = []
    for side in (256, 512):
        for repeat in range(1, REPEATS + 1):
            for kind in group_order(repeat):
                r = [x for x in rows if (x['side'], x['repeat'], x['kind']) == (side, repeat, kind)]
                require([x['index'] for x in r] == list(range(WARMUP + SAMPLES)), 'Duplicate/missing samples')
                require([x['warmup'] for x in r] == [True]*WARMUP + [False]*SAMPLES, 'Warmup classification changed')
                timed = r[WARMUP:]
                metrics = {'call': stats([x['call_end_ns'] - x['call_start_ns'] for x in timed])}
                if kind == 'CPU':
                    metrics['cpu_process'] = stats([x['process_end_ns'] - x['process_start_ns'] for x in timed])
                else:
                    for key in ('pl_core_frame_ns', 'dma_transaction_ns', 'inference_ns', 'cpu_snapshot_ns'):
                        metrics[key] = stats([x['hardware']['timing_ns'][key] for x in timed])
                matches = [g for g in group_records if (g['side'], g['repeat'], g['kind']) == (side, repeat, kind)]
                require(len(matches) == 1, 'Missing/duplicate loop bounds')
                g = matches[0]
                require(g['measured_start_ns'] <= timed[0]['iteration_start_ns'] and
                        g['measured_end_ns'] >= timed[-1]['data_saved_ns'], 'Invalid loop enclosure')
                elapsed = g['measured_end_ns'] - g['measured_start_ns']
                groups.append(dict(side=side, repeat=repeat, kind=kind, metrics=metrics,
                    evidence_loop_ns=elapsed, evidence_loop_fps=SAMPLES*1e9/elapsed))
    return dict(status='COLLECTED_PENDING_INDEPENDENT_DOWNLOAD_AUDIT', groups=groups,
        scope='Fixed im0001, cached ready input, C7 final T112. CPU vs PL call; PL inference/core/DMA separately.',
        exclusions='File decode/preprocess, browser/network/PNG, pure DMA, power and long-run stability not measured here.',
        fps_scope='Evidence loop includes output validation, raw NPY writes and journal fsync; not browser FPS.',
        cpu_scope='One PS process, OpenCV threads=1; NumPy/OpenCV frozen same-output reference, not optimal hand-written ARM code.',
        pending=['W4 browser 3x(3+100)', 'independent pure-DMA loopback', 'paired power estimate', 'W5 stability', 'quality improvements'])
