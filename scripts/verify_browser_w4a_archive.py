"""Offline full-word/PNG/score/timing verification of downloaded W4a evidence.

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
from prepare_q2_quality_vectors import expected_words
from pynq_w4a.quality_observer import QualityObserver, control_word
CANDIDATE = json.loads((ROOT / "results/q1_quality_2026-10-14/selected_candidate.json").read_bytes())["candidate"]
from a1_point_board_test import notebook_code_hash
from pynq_w4a.protocol import Inputs, MODES, PNG_PROFILES, REVISION, file_info, require, rgb_from_input, sha, validate_package, write_json


def check_run(archive, record, package, manifest):
    run_id, request = record['run_id'], record['request']
    require(record['status'] == 'COMPLETED' and record['revision'] == REVISION, 'Noncompleted/wrong release run')
    config = Inputs(package, manifest['images']).request({key: request[key] for key in ('image_id', 'side', 'mode', 'threshold', 'algorithm', 'client_nonce', 'png_profile')})
    require(config == request, 'Recorded request differs from validated request')
    identity = {key: request[key] for key in ('algorithm', 'image_id', 'side', 'threshold', 'mode', 'mode_code', 'png_profile')}
    require(sha(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()) == record['config_id'], 'Config identity mismatch')
    require(record['hardware_identity'] == {key: manifest['artifacts']['w2_quality.' + ('bit' if key == 'bit' else 'hwh')]
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
    require(np.array_equal(output, golden), 'Downloaded PL output differs from independent A/C2 full-word reference')
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


def verify(archive_path, notebook_path, package, *, allow_incomplete_display=False):
    package = Path(package)
    manifest = validate_package(package)
    executed = json.loads(Path(notebook_path).read_bytes())
    release = json.loads((ROOT / 'notebooks/browser_w4a_start.ipynb').read_bytes())
    # An empty, unexecuted tail is Jupyter UI data, not a changed executable step.
    original_count = sum(cell['cell_type'] == 'code' for cell in release['cells'])
    code = [cell for cell in executed['cells'] if cell['cell_type'] == 'code']
    if len(code) == original_count + 1 and not ''.join(code[-1]['source']).strip() and code[-1].get('execution_count') is None:
        executed = {**executed, 'cells': executed['cells'][:-1]}
        code = code[:-1]
    require(len(code) == original_count and notebook_code_hash(executed) == notebook_code_hash(release), 'Executed Notebook code differs')
    require(all(type(cell.get('execution_count')) is int and not any(output.get('output_type') == 'error' for output in cell.get('outputs', []))
                for cell in code), 'Startup/finish steps did not all complete cleanly')
    records = []
    observations = []
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and all(not Path(name).is_absolute() and '..' not in Path(name).parts and '\\' not in name and ':' not in name for name in names), 'Unsafe/duplicate evidence members')
        require(sum(item.file_size for item in archive.infolist()) <= 1024 ** 3, 'W4a evidence exceeds bounded session size')
        caps = json.loads(archive.read('capabilities.json'))
        require(caps['evidence_kind'] == 'PYNQ_PL_DMA', 'HOST TEST preview is not board evidence')
        require(caps['revision'] == REVISION and caps['threshold_range'] == [1, 255] and caps['algorithms'] == ['A', 'C2'] and caps['core_cycle_readback_supported'] and caps['latched_parameter_readback_supported'] and caps['modes'] == MODES, 'Wrong measured capabilities')
        require(caps['png_profiles'] == PNG_PROFILES, 'Wrong delivery options')
        require(archive.read('browser_manifest.json') == (package / 'browser_manifest.json').read_bytes(), 'Execution package differs')
        environment = json.loads(archive.read('environment.json'))
        require(environment['pynq'] == '3.0.1' and environment['machine'] in ('armv7l', 'armv7'), 'Wrong recorded real board runtime')
        require(environment['runtime_fclk0_mhz_register_readback'] == 100.0 and environment['drivers'] == {'dma': 'pynq.lib.dma.DMA', 'control': 'pynq.lib.axigpio.AxiGPIO', 'observer': 'pynq.lib.axigpio.AxiGPIO'}, 'Wrong clock/drivers')
        session = json.loads(archive.read('session.json'))
        require(session['status']['session_id'] == caps['session_id'] and session['status']['overlay_downloads'] == 1 and
                session['status']['service_state'] == 'READY' and session['status']['hardware_state'] == 'IDLE' and
                session['status']['active_run_id'] is None and session['status']['pending'] == 0 and not session['status']['error'], 'Export not from clean idle single-load session')
        require(session['status']['retained_buffer_count'] == 0, 'Idle session retains native buffers')
        lifecycle = notebook_outputs(code, session, environment)
        native_records = [json.loads(archive.read(run_id + '/record.json')) for run_id in session['run_ids']]
        native_records.sort(key=lambda record: record['accepted_server_ns'])
        previous_status, nonces = 0, set()
        loops = {}
        for record in native_records:
            require(record['session_id'] == caps['session_id'] and record['evidence_kind'] == record['evidence']['evidence_kind'] == 'PYNQ_PL_DMA', 'Mixed/unreal execution provenance')
            require(record['request']['client_nonce'] not in nonces, 'Duplicate request nonce counted twice')
            nonces.add(record['request']['client_nonce'])
            checked = check_run(archive, record, package, manifest)
            require(checked['frame_status_before'] == previous_status, 'Unexplained PL frames or reset between browser requests')
            previous_status = checked['frame_status_after']
            require(checked['hardware']['sequence'] == len(records) + 1, 'Observer sequence discontinuity')
            records.append(checked)
            timing_name = record['run_id'] + '/browser_timing.json'
            if timing_name not in names:
                continue  # Selection can change in flight; such a frame is not a displayed-FPS sample.
            observed = json.loads(archive.read(timing_name))
            require(observed['run_id'] == record['run_id'] and observed['session_id'] == caps['session_id'] and
                    observed['client_nonce'] == record['request']['client_nonce'] and observed['config_id'] == record['config_id'] and
                    observed['input_sha256'] == record['input']['sha256'] and observed['output_sha256'] == record['output']['sha256'], 'Stale browser frame observation')
            require(observed['visibility'] in ('visible', 'hidden') and observed['evidence_kind'] == 'PYNQ_PL_DMA',
                    'Invalid browser visibility/provenance')
            times = [observed[key] for key in ('request_start_ms', 'result_received_ms', 'images_decoded_ms', 'render_done_ms')]
            require(all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in times) and times == sorted(times), 'Invalid client times')
            require(observed['request_to_render_ms'] == times[-1] - times[0] and observed['result_received_to_render_ms'] == times[-1] - times[1], 'Browser interval arithmetic differs')
            if observed['loop_id'] is None:
                require(observed['browser_actual_fps'] is None, 'Manual click represented as FPS')
            else:
                loop_id, index, start = observed['loop_id'], observed['loop_index'], observed['loop_start_ms']
                previous = loops.get(loop_id, {'index': 0, 'start': times[0], 'render': times[0], 'visible': True, 'config_id': record['config_id']})
                require(index == previous['index'] + 1 and start == previous['start'] and times[0] >= previous['render'] and record['config_id'] == previous['config_id'], 'Nonconsecutive display loop')
                visible = previous['visible'] and observed['visibility'] == 'visible'
                fps = index * 1000 / (times[-1] - start) if index >= 2 and visible and times[-1] > start else None
                require(observed['browser_actual_fps'] == fps, 'Client FPS not unique completed frames per loop duration')
                hidden = previous.get('hidden_indices', []) + ([index] if observed['visibility'] == 'hidden' else [])
                loops[loop_id] = {'index': index, 'start': start, 'render': times[-1], 'visible': visible,
                                 'hidden_indices': hidden, 'verified_fps': fps, 'config_id': record['config_id']}
            observations.append(observed)
        require(session['status']['completed'] == session['status']['accepted'] == len(records) == len(session['run_ids']) and
                session['status']['last_completed_frame_status'] == previous_status, 'Completed/exported/native run count mismatch')
        coverage = {'image_ids': sorted({record['request']['image_id'] for record in records}),
                    'modes': sorted({record['request']['mode'] for record in records}),
                    'sides': sorted({record['request']['side'] for record in records})}
        rows = list(csv.DictReader(io.StringIO(archive.read('measurements.csv').decode('utf-8-sig'))))
        require(len(rows) == len(records), 'CSV count mismatch')
        by_id = {row['run_id']: row for row in rows}
        require(len(by_id) == len(records) and set(by_id) == {record['run_id'] for record in records}, 'Duplicate/missing CSV run IDs')
        observed_by_id = {observed['run_id']: observed for observed in observations}
        for record in records:
            row = by_id[record['run_id']]
            for name in ('dma_transaction_ns', 'inference_ns'):
                require(int(row[name]) == record['timing_ns'][name], 'CSV latency mismatch')
            require(int(row['pl_core_frame_ns']) == record['timing_ns']['pl_core_frame_ns'] and row['pure_dma_transport_ns'] == '', 'CSV invented core/pure transport time')
            require(all(row[key] == str(record['request'][key]) for key in ('image_id', 'side', 'mode', 'threshold', 'algorithm')),
                    'CSV request identity mismatch')
            require(row['png_profile'] == record['request']['png_profile'] and all(int(row[k]) == record['timing_ns'][k] for k in
                    ('array_decode_overlay_ns','png_fromarray_ns','png_save_ns','png_file_hash_ns','file_inventory_hash_ns')), 'CSV PNG profile/timing differs')
            expected_csv = {'vessel_area_fraction': record['quality']['vessel_area_fraction']}
            for label in ('AH', 'VK'):
                for metric in ('dice', 'iou'):
                    expected_csv[metric + '_' + label] = record['quality']['annotations'].get(label, {}).get(metric)
            observation = observed_by_id.get(record['run_id'], {})
            expected_csv.update(browser_request_to_render_ms=observation.get('request_to_render_ms'),
                                browser_actual_fps=observation.get('browser_actual_fps'))
            require(all(row[key] == '' if value is None else float(row[key]) == value for key, value in expected_csv.items()),
                    'CSV quality/browser observation mismatch')
        display_complete = any(loop['index'] >= 20 and loop['visible'] for loop in loops.values())
        if not allow_incomplete_display:
            require(display_complete, 'Visible 20-frame browser loop missing')
    needed = [('A','baseline'),('A','fast'),('C2','baseline'),('C2','fast')]
    cursor=0
    for r in records:
        q=r['request']
        if cursor < len(needed) and (q['algorithm'],q['png_profile']) == needed[cursor] and (q['image_id'],q['side'],q['threshold'],q['mode']) == ('im0001',512,28,'final'):
            cursor += 1
    require(cursor == len(needed), 'W4a four A/C2/profile gates missing')
    by_run = {r['run_id']: r for r in records}
    qualified = {}
    for loop_id, loop in loops.items():
        sample=[o for o in observations if o['loop_id']==loop_id]
        if len(sample)!=20 or not loop['visible']: continue
        group=[by_run[o['run_id']] for o in sample]
        first=records.index(group[0]); warm=records[first-3:first] if first>=3 else []
        q=group[0]['request']; profile=q['png_profile']
        require((q['image_id'],q['side'],q['algorithm'],q['threshold'],q['mode']) == ('im0001',512,'C2',28,'final'), 'Wrong profile comparison input')
        require(len(warm)==3 and all(all(r['request'][k]==q[k] for k in ('image_id','side','algorithm','threshold','mode','png_profile')) for r in warm), 'Three preceding native warmups missing')
        require([r['run_id'] for r in records[first:first+20]] == [r['run_id'] for r in group], 'Profile loop interrupted by other native frames')
        warm_ids={r['run_id'] for r in warm}
        require(sum(o['run_id'] in warm_ids and o['loop_id'] is None for o in observations)==3, 'Warmups missing independent browser observations')
        require(profile not in qualified, 'Multiple profile loops: report explicitly before comparison')
        qualified[profile]={'loop_id':loop_id,'warmup_ids':[r['run_id'] for r in warm], 'measured_ids':[r['run_id'] for r in group], 'output_sha256':group[0]['output_sha256']}
    if not allow_incomplete_display: require(set(qualified)=={'baseline','fast'}, 'Both complete foreground PNG groups required')
    if set(qualified)=={'baseline','fast'}:
        require(qualified['baseline']['output_sha256']==qualified['fast']['output_sha256'], 'Profile groups changed PL output')
    display_complete=set(qualified)=={'baseline','fast'}
    return {'status': ('W4a_DOWNLOADED_ARRAYS_AND_OBSERVATIONS_VERIFIED_NOT_FINAL_ACCEPTANCE' if display_complete else
                       'W4a_NUMERIC_AND_FUNCTIONAL_EVIDENCE_VERIFIED_DISPLAY_FPS_PENDING'),
            'session_id': caps['session_id'], 'coverage': coverage,
            'archive': file_info(archive_path), 'notebook': file_info(notebook_path),
            'verified_runs': len(records), 'matched_words': sum(record['matched_words'] for record in records),
            'matched_png_images': sum(record['matched_png_images'] for record in records),
            'matched_png_values': sum(record['matched_png_values'] for record in records),
            'browser_observations': len(observations), 'runs': records, 'observations': observations,
            'lifecycle': lifecycle, 'display_loops': loops, 'visible_20_frame_loop_verified': display_complete,
            'timing_summary': timing_summary(records, observations, loops), 'profile_groups': qualified,
            'numeric_and_functional_evidence_verified': True, 'final_acceptance_pass': False,
            'pl_core_measured_per_run': True, 'pure_dma_transport_ns': None,
            'formal_20_image_quality_pass': False, 'adjustable_threshold_pass': True, 'full_performance_pass': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('notebook', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--package', type=Path, default=ROOT / 'build/deploy/browser_w4a_png_r1')
    parser.add_argument('--allow-incomplete-display', action='store_true',
                        help='Offline partial audit only; do not certify missing comparison groups')
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=False)
    try:
        report = verify(args.archive, args.notebook, args.package,
                        allow_incomplete_display=args.allow_incomplete_display)
    except Exception as exc:
        write_json(args.destination / 'failed_verification.json', {'status': 'FAILED_VERIFICATION', 'error': type(exc).__name__ + ': ' + str(exc)})
        raise
    write_json(args.destination / 'verification.json', report)
    print(report['status'] + ': ' + str(report['verified_runs']) + ' runs / ' + str(report['matched_words']) + ' words')
