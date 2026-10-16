"""Offline full-word/PNG/score/timing verification of downloaded W4b evidence.

CPU M0 is used here as an independent comparator, never in the deployed service.
"""
import argparse
import ast
import csv
import io
import json
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_q4d_detector_vectors import expected_words
from pynq_w4b.quality_observer import QualityObserver, control_word
CANDIDATE = json.loads((ROOT / "results/q1_quality_2026-10-14/selected_candidate.json").read_bytes())["candidate"]
from a1_point_board_test import notebook_code_hash
from pynq_w4b.protocol import Inputs, MODES, PNG_PROFILES, REVISION, file_info, require, rgb_from_input, sha, validate_package, write_json


def check_run(archive, record, package, manifest):
    run_id, request = record['run_id'], record['request']
    require(record['status'] == 'COMPLETED' and record['revision'] == REVISION, 'Noncompleted/wrong release run')
    config = Inputs(package, manifest['images']).request({key: request[key] for key in ('image_id', 'side', 'mode', 'threshold', 'algorithm', 'client_nonce', 'png_profile')})
    require(config == request, 'Recorded request differs from validated request')
    identity = {key: request[key] for key in ('algorithm', 'image_id', 'side', 'threshold', 'mode', 'mode_code', 'png_profile')}
    require(sha(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()) == record['config_id'], 'Config identity mismatch')
    require(record['hardware_identity'] == {key: manifest['artifacts']['q4d_detector.' + ('bit' if key == 'bit' else 'hwh')]
                                          for key in ('bit', 'hwh')}, 'Hardware pair mismatch')
    prefix = run_id + '/'
    for name, info in record['files'].items():
        data = archive.read(prefix + name)
        require({'bytes': len(data), 'sha256': sha(data)} == info, 'Exported file hash mismatch: ' + name)
    source = np.load(io.BytesIO(archive.read(prefix + 'input_packed.npy')), allow_pickle=False)
    output = np.load(io.BytesIO(archive.read(prefix + 'output_packed.npy')), allow_pickle=False)
    prepared, entry = Inputs(package, manifest['images']).load(config)
    require(np.array_equal(source, prepared) and source.dtype == output.dtype == np.uint32 and source.shape == output.shape,
            'Input shape/type/immutable geometry mismatch')
    require(sha(source.tobytes()) == record['input']['sha256'] == entry['input_word_sha256'], 'Input hash mismatch')
    require(sha(output.tobytes()) == record['output']['sha256'] == record['evidence']['output_sha256'], 'Output hash mismatch')
    golden = expected_words(source, request['mode_code'], request['algorithm'], request['threshold'], CANDIDATE)
    require(np.array_equal(output, golden), 'Downloaded PL output differs from independent A/C2/C5/C7 full-word reference')
    rgb = rgb_from_input(source)
    decoded = {'original': rgb}
    if request['mode_code']:
        mask = ((output >> 16) & 255).astype(np.uint8)
        overlay = rgb.copy()
        overlay[mask != 0] = ((35 * rgb[mask != 0].astype(np.uint16) + np.array([0, 16575, 0], np.uint16) + 50) // 100).astype(np.uint8)
        decoded.update(enhanced=((output >> 8) & 255).astype(np.uint8), mask=mask, overlay=overlay,
                       response=((output >> 24) & 255).astype(np.uint8))
    require(set(decoded) == set(record['images']), 'Wrong image panels for current PL mode')
    for name, pixels in decoded.items():
        png = archive.read(prefix + name + '.png')
        require(sha(png) == record['images'][name]['sha256'], 'Image hash mismatch')
        require(np.array_equal(np.array(Image.open(io.BytesIO(png))), pixels), 'PNG pixels differ from current raw DMA output')
    require(set(record['files']) == {'input_packed.npy', 'output_packed.npy'} | {name + '.png' for name in decoded},
            'Incomplete raw/image file inventory')
    require(record['png_profile'] == request['png_profile'] and set(record['encoding_details']) == set(decoded), 'Wrong encoding profile/inventory')
    previous = record['raw_timestamps_ns']['arrays_ready_ns']
    for kind, pixels in decoded.items():
        detail = record['encoding_details'][kind]
        points = detail['raw_timestamps_ns']
        require(len(points) == 4 and all(type(t) is int for t in points) and points == sorted(points) and
                previous <= points[0] <= points[-1] <= record['raw_timestamps_ns']['encoding_end_ns'], 'Invalid PNG timing order')
        require(detail['options'] == PNG_PROFILES[request['png_profile']] and detail['profile'] == request['png_profile'] and
                detail['shape'] == list(pixels.shape) and detail['dtype'] == 'uint8' and
                detail['mode'] == ('RGB' if pixels.ndim == 3 else 'L') and detail['bytes'] == record['files'][kind+'.png']['bytes'], 'PNG format/options/size differ')
        for key, start, end in [('fromarray_ns',0,1),('save_ns',1,2),('file_hash_ns',2,3)]:
            require(detail[key] == points[end]-points[start], 'PNG timing arithmetic differs')
        previous = points[-1]
    for key, item in [('png_fromarray_ns','fromarray_ns'),('png_save_ns','save_ns'),('png_file_hash_ns','file_hash_ns')]:
        require(record['timing_ns'][key] == sum(d[item] for d in record['encoding_details'].values()), 'PNG totals differ')
    require(record['input']['file'] == record['files']['input_packed.npy'] and
            record['output']['file'] == record['files']['output_packed.npy'], 'Raw file identities differ')
    fov = (source >> 24) != 0
    quality = record['quality']
    if request['mode_code'] == 0:
        require(quality['vessel_area_fraction'] is None and not quality['annotations'], 'Bypass has stale quality')
    else:
        prediction = ((output >> 16) & 255) != 0
        denominator, numerator = int(fov.sum()), int((prediction & fov).sum())
        require(quality['vessel_pixels'] == numerator and quality['fov_pixels'] == denominator and
                quality['vessel_area_fraction'] == (numerator / denominator if denominator else None), 'Area not based on actual PL mask and FOV')
        for label, spec in entry['evaluation_only'].items():
            truth = np.load(package / spec['path'], allow_pickle=False)
            counts = {'tp': int((prediction & truth & fov).sum()), 'fp': int((prediction & ~truth & fov).sum()),
                      'fn': int((~prediction & truth & fov).sum()), 'tn': int((~prediction & ~truth & fov).sum())}
            reported = quality['annotations'][label]
            require(all(reported[key] == value for key, value in counts.items()), 'Confusion matrix differs')
            tp, fp, fn = counts['tp'], counts['fp'], counts['fn']
            require(reported['dice'] == (2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.0) and
                    reported['iou'] == (tp / (tp + fp + fn) if tp + fp + fn else 1.0), 'Dice/IoU formula mismatch')
    evidence, timing, stamps = record['evidence'], record['timing_ns'], record['raw_timestamps_ns']
    observed = evidence['hardware_latched_parameter_readback']
    control = control_word(side=request['side'], stage=request['mode_code'], algorithm=request['algorithm'], threshold=request['threshold'], tag=observed['sequence'] & 0xffff)
    reader = object.__new__(QualityObserver)
    reader.clock_hz = 100000000
    reader.read_word = lambda page: observed['raw_pages'][str(page)]
    replay = reader.completed(expected_control=control, previous_sequence=(observed['sequence']-1)&0xffffffff, expected_words=source.size)
    require(replay == observed, 'Raw hardware observer arithmetic/control differs')
    require(evidence['requested_control_word'] == control, 'GPIO control differs from request')
    require(evidence['applied_parameters'] == dict(algorithm=request['algorithm'], threshold=request['threshold'], side=request['side'], mode_code=request['mode_code'], task_tag=observed['task_tag']), 'Applied parameters differ')
    require(timing['pl_core_frame_ns'] == observed['pl_core_frame_ns'] <= timing['dma_transaction_ns'] and timing['pl_core_cycles'] == observed['pl_core_cycles'] and timing['pure_dma_transport_ns'] is None, 'Invalid hardware timing')
    for key in ('tx', 'rx'):
        buf = evidence['buffers'][key]
        require(buf['nbytes'] == source.size * 4 and buf['dtype'] == 'uint32' and buf['shape'] == [source.size] and buf['strides'] == [4], 'Wrong buffer shape/type')
        require(buf['physical_address'] % 8 == 0 and 0x100000 <= buf['physical_address'] <= 0x20000000 - source.size * 4, 'Invalid DDR buffer')
    require(abs(evidence['buffers']['tx']['physical_address'] - evidence['buffers']['rx']['physical_address']) >= source.size * 4, 'DDR overlap')
    before, after = evidence['frame_status_before'], evidence['frame_status_after']
    count = ((before & 0x3fff) + 1) & 0x3fff
    require(before >> 28 == 0 and before & 0x3fff == (before >> 14) & 0x3fff and after == count | count << 14,
            'PL counters/error/wrap mismatch')
    require(evidence['frame_count'] == count and evidence['frame_counter_wrapped'] == (count == 0), 'Frame count mismatch')
    require(evidence['send_bytes'] == evidence['recv_bytes'] == request['side'] ** 2 * 4,
            'Actual DMA byte lengths mismatch')
    require(set(evidence['dma_status']) == {'mm2s', 's2mm'} and
            all(value & 2 and not value & 0x771 for value in evidence['dma_status'].values()), 'DMA status mismatch')
    order = ['worker_start_ns', 'input_ready_ns', 'config_start_ns', 'config_end_ns', 'dma_start_ns', 'dma_end_ns',
             'snapshot_start_ns', 'snapshot_end_ns', 'observer_end_ns', 'raw_saved_ns', 'evaluation_end_ns', 'arrays_ready_ns', 'encoding_end_ns', 'worker_result_ready_ns']
    values = [stamps[key] for key in order]
    require(all(type(value) is int and value >= 0 for value in values) and values == sorted(values), 'Invalid server monotonic boundaries')
    intervals = {'array_decode_overlay_ns': ('evaluation_end_ns', 'arrays_ready_ns'), 'file_inventory_hash_ns': ('encoding_end_ns', 'worker_result_ready_ns'), 'observer_readback_ns': ('snapshot_end_ns', 'observer_end_ns'), 'config_ns': ('config_start_ns', 'config_end_ns'), 'dma_transaction_ns': ('dma_start_ns', 'dma_end_ns'),
                 'cpu_snapshot_ns': ('snapshot_start_ns', 'snapshot_end_ns'), 'inference_ns': ('config_start_ns', 'snapshot_end_ns'),
                 'input_read_ns': ('worker_start_ns', 'input_ready_ns'), 'raw_save_ns': ('observer_end_ns', 'raw_saved_ns'),
                 'evaluation_ns': ('raw_saved_ns', 'evaluation_end_ns'), 'png_encoding_ns': ('evaluation_end_ns', 'encoding_end_ns'),
                 'worker_result_ns': ('worker_start_ns', 'worker_result_ready_ns')}
    require(all(timing[name] == stamps[end] - stamps[start] for name, (start, end) in intervals.items()), 'Server timing interval differs')
    require(timing['queue_wait_ns'] == stamps['worker_start_ns'] - record['accepted_server_ns'] >= 0, 'Queue wait mismatch')
    return {'run_id': run_id, 'request': request, 'matched_words': int(output.size),
            'matched_png_images': len(decoded), 'matched_png_values': sum(int(pixels.size) for pixels in decoded.values()),
            'input_sha256': record['input']['sha256'], 'output_sha256': record['output']['sha256'],
            'timing_ns': timing, 'hardware': observed,
            'frame_status_before': before, 'frame_status_after': after, 'quality': quality}


def notebook_outputs(code, session, environment):
    streams = [''.join(''.join(output.get('text', [])) for output in cell.get('outputs', [])
                       if output.get('output_type') == 'stream') for cell in code]
    markers = {0: 'PACKAGE_BYTES_PASS:', 1: 'BROWSER_PRECHECK_PASS:', 2: 'BROWSER_SERVICE_READY:',
               4: 'BROWSER_RECORDS_READY:', 5: 'BROWSER_SERVICE_CLOSED_IDLE:'}
    require(all(marker in streams[index] for index, marker in markers.items()), 'Notebook lifecycle marker missing')
    runtime = [line.removeprefix('Runtime: ') for line in streams[1].splitlines() if line.startswith('Runtime: ')]
    require(len(runtime) == 1 and all(environment.get(k) == v for k,v in ast.literal_eval(runtime[0]).items()), 'Notebook/archive runtime differs')
    printed = []
    for index in (2, 3):
        lines = [line for line in streams[index].splitlines() if line.startswith("{'session_id':")]
        require(len(lines) == 1, 'Notebook lifecycle status missing')
        printed.append(ast.literal_eval(lines[0]))
    initial, final = printed
    require(initial['session_id'] == final['session_id'] == session['status']['session_id'] and
            initial['overlay_downloads'] == 1 and initial['completed'] == initial['accepted'] == 0 and
            initial['last_completed_frame_status'] == 0 and initial['hardware_state'] == 'IDLE' and
            initial['active_run_id'] is None and initial['pending'] == initial['retained_buffer_count'] == 0 and
            not initial['error'] and initial['evidence_kind'] == 'PYNQ_PL_DMA' and initial['service_state'] == 'READY',
            'Notebook initial native status differs')
    require(final == session['status'], 'Notebook/export final session status differs')
    return {'execution_counts': [cell['execution_count'] for cell in code],
            'markers': list(markers.values()), 'initial_status': initial, 'export_status': final,
            'clean_close_printed': True}


def latency_statistics(values):
    samples = np.asarray(values, dtype=np.float64)
    require(samples.size > 0 and bool(np.isfinite(samples).all()), 'Invalid latency statistics')
    return {'n': int(samples.size), 'mean': float(samples.mean()), 'median': float(np.median(samples)),
            'p95': float(np.percentile(samples, 95)), 'minimum': float(samples.min()), 'maximum': float(samples.max()),
            'percentile_method': 'linear'}


def timing_summary(records, observations, loops):
    by_id = {record['run_id']: record for record in records}
    fields = ('pl_core_frame_ns', 'observer_readback_ns', 'dma_transaction_ns', 'inference_ns', 'cpu_snapshot_ns', 'input_read_ns', 'raw_save_ns',
              'evaluation_ns', 'png_encoding_ns', 'worker_result_ns', 'queue_wait_ns', 'array_decode_overlay_ns', 'png_fromarray_ns', 'png_save_ns', 'png_file_hash_ns', 'file_inventory_hash_ns')
    result = {}
    for loop_id, loop in loops.items():
        clients = [observed for observed in observations if observed['loop_id'] == loop_id]
        native = [by_id[observed['run_id']] for observed in clients]
        visible = [observed for observed in clients if observed['visibility'] == 'visible']
        result[loop_id] = {
            'png_profile': native[0]['request']['png_profile'], 'native_runs': len(native), 'hidden_indices': loop['hidden_indices'],
            'warmup_frames': 3, 'scope': 'W4a PNG profile comparison: 3 warmup plus 20 measured; not formal 100-frame three-configuration performance',
            'server_latency_ms': {field.removesuffix('_ns') + '_ms': latency_statistics([record['timing_ns'][field] / 1e6 for record in native])
                                  for field in fields},
            'mean_png_fraction_of_worker_time': float(np.mean([record['timing_ns']['png_encoding_ns'] / record['timing_ns']['worker_result_ns'] for record in native])),
            'visible_request_latency_ms': latency_statistics([observed['request_to_render_ms'] for observed in visible]) if visible else None,
            'visible_result_to_render_ms': latency_statistics([observed['result_received_to_render_ms'] for observed in visible]) if visible else None,
            'entire_loop_duration_ms': loop['render'] - loop['start'],
            'browser_actual_fps': loop['verified_fps'],
            'display_fps_valid': loop['index'] >= 20 and loop['visible'],
            'pl_core_measured_per_run': True, 'pure_dma_transport_ns': None,
            'browser_time_scope': 'Client monotonic double-rAF approximation; hidden requests excluded from latency statistics, any hidden interval invalidates entire-loop visible FPS'}
    return result
