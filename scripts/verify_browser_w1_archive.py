"""Offline full-word/PNG/score/timing verification of downloaded W1 evidence.

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
from prepare_a4_vectors import expected_words
from a1_point_board_test import notebook_code_hash
from pynq_app.protocol import Inputs, MODES, REVISION, file_info, require, rgb_from_input, sha, validate_package, write_json


def check_run(archive, record, package, manifest):
    run_id, request = record['run_id'], record['request']
    require(record['status'] == 'COMPLETED' and record['revision'] == REVISION, 'Noncompleted/wrong release run')
    config = Inputs(package, manifest['images']).request({key: request[key] for key in ('image_id', 'side', 'mode', 'threshold', 'client_nonce')})
    require(config == request, 'Recorded request differs from validated request')
    identity = {key: request[key] for key in ('algorithm', 'image_id', 'side', 'threshold', 'mode', 'mode_code')}
    require(sha(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()) == record['config_id'], 'Config identity mismatch')
    require(record['hardware_identity'] == {key: manifest['artifacts']['a4_segmentation.' + ('bit' if key == 'bit' else 'hwh')]
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
    golden = expected_words(source, request['mode_code'])
    require(np.array_equal(output, golden), 'Downloaded PL output differs from independent frozen M0 full-word reference')
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
    require(evidence['requested_control_word'] == request['mode_code'] | (4 if request['side'] == 256 else 0), 'GPIO control not requested config')
    require(evidence['hardware_latched_parameter_readback'] is None and timing['pl_core_frame_ns'] is None and
            timing['pl_core_cycles'] is None and timing['pure_dma_transport_ns'] is None, 'Unavailable hardware timing falsely populated')
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
             'snapshot_start_ns', 'snapshot_end_ns', 'raw_saved_ns', 'evaluation_end_ns', 'encoding_end_ns', 'worker_result_ready_ns']
    values = [stamps[key] for key in order]
    require(all(type(value) is int and value >= 0 for value in values) and values == sorted(values), 'Invalid server monotonic boundaries')
    intervals = {'config_ns': ('config_start_ns', 'config_end_ns'), 'dma_transaction_ns': ('dma_start_ns', 'dma_end_ns'),
                 'cpu_snapshot_ns': ('snapshot_start_ns', 'snapshot_end_ns'), 'inference_ns': ('config_start_ns', 'snapshot_end_ns'),
                 'input_read_ns': ('worker_start_ns', 'input_ready_ns'), 'raw_save_ns': ('snapshot_end_ns', 'raw_saved_ns'),
                 'evaluation_ns': ('raw_saved_ns', 'evaluation_end_ns'), 'png_encoding_ns': ('evaluation_end_ns', 'encoding_end_ns'),
                 'worker_result_ns': ('worker_start_ns', 'worker_result_ready_ns')}
    require(all(timing[name] == stamps[end] - stamps[start] for name, (start, end) in intervals.items()), 'Server timing interval differs')
    require(timing['queue_wait_ns'] == stamps['worker_start_ns'] - record['accepted_server_ns'] >= 0, 'Queue wait mismatch')
    return {'run_id': run_id, 'request': request, 'matched_words': int(output.size),
            'matched_png_images': len(decoded), 'matched_png_values': sum(int(pixels.size) for pixels in decoded.values()),
            'input_sha256': record['input']['sha256'], 'output_sha256': record['output']['sha256'],
            'timing_ns': timing,
            'frame_status_before': before, 'frame_status_after': after, 'quality': quality}


def notebook_outputs(code, session, environment):
    streams = [''.join(''.join(output.get('text', [])) for output in cell.get('outputs', [])
                       if output.get('output_type') == 'stream') for cell in code]
    markers = {0: 'PACKAGE_BYTES_PASS:', 1: 'BROWSER_PRECHECK_PASS:', 2: 'BROWSER_SERVICE_READY:',
               4: 'BROWSER_RECORDS_READY:', 5: 'BROWSER_SERVICE_CLOSED_IDLE:'}
    require(all(marker in streams[index] for index, marker in markers.items()), 'Notebook lifecycle marker missing')
    runtime = [line.removeprefix('Runtime: ') for line in streams[1].splitlines() if line.startswith('Runtime: ')]
    require(len(runtime) == 1 and ast.literal_eval(runtime[0]) == environment, 'Notebook/archive runtime differs')
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
    fields = ('dma_transaction_ns', 'inference_ns', 'cpu_snapshot_ns', 'input_read_ns', 'raw_save_ns',
              'evaluation_ns', 'png_encoding_ns', 'worker_result_ns', 'queue_wait_ns')
    result = {}
    for loop_id, loop in loops.items():
        clients = [observed for observed in observations if observed['loop_id'] == loop_id]
        native = [by_id[observed['run_id']] for observed in clients]
        visible = [observed for observed in clients if observed['visibility'] == 'visible']
        result[loop_id] = {
            'native_runs': len(native), 'hidden_indices': loop['hidden_indices'],
            'warmup_frames': 0, 'scope': 'W1 recorded diagnostic loop; not formal 3-warmup/100-frame performance',
            'server_latency_ms': {field.removesuffix('_ns') + '_ms': latency_statistics([record['timing_ns'][field] / 1e6 for record in native])
                                  for field in fields},
            'mean_png_fraction_of_worker_time': float(np.mean([record['timing_ns']['png_encoding_ns'] / record['timing_ns']['worker_result_ns'] for record in native])),
            'visible_request_latency_ms': latency_statistics([observed['request_to_render_ms'] for observed in visible]) if visible else None,
            'visible_result_to_render_ms': latency_statistics([observed['result_received_to_render_ms'] for observed in visible]) if visible else None,
            'entire_loop_duration_ms': loop['render'] - loop['start'],
            'browser_actual_fps': loop['verified_fps'],
            'display_fps_valid': loop['index'] >= 20 and loop['visible'],
            'pl_core_frame_ns': None, 'pure_dma_transport_ns': None,
            'browser_time_scope': 'Client monotonic double-rAF approximation; hidden requests excluded from latency statistics, any hidden interval invalidates entire-loop visible FPS'}
    return result


def verify(archive_path, notebook_path, package, *, allow_incomplete_display=False, prior_bringup=None):
    package = Path(package)
    manifest = validate_package(package)
    executed = json.loads(Path(notebook_path).read_bytes())
    release = json.loads((ROOT / 'notebooks/browser_start.ipynb').read_bytes())
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
        require(sum(item.file_size for item in archive.infolist()) <= 1024 ** 3, 'W1 evidence exceeds bounded session size')
        caps = json.loads(archive.read('capabilities.json'))
        require(caps['evidence_kind'] == 'PYNQ_PL_DMA', 'HOST TEST preview is not board evidence')
        require(caps['revision'] == REVISION and caps['threshold_choices'] == [28] and caps['modes'] == MODES, 'Wrong measured capabilities')
        require(archive.read('browser_manifest.json') == (package / 'browser_manifest.json').read_bytes(), 'Execution package differs')
        environment = json.loads(archive.read('environment.json'))
        require(environment['pynq'] == '3.0.1' and environment['machine'] in ('armv7l', 'armv7'), 'Wrong recorded real board runtime')
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
                previous = loops.get(loop_id, {'index': 0, 'start': times[0], 'render': times[0], 'visible': True})
                require(index == previous['index'] + 1 and start == previous['start'] and times[0] >= previous['render'], 'Nonconsecutive display loop')
                visible = previous['visible'] and observed['visibility'] == 'visible'
                fps = index * 1000 / (times[-1] - start) if index >= 2 and visible and times[-1] > start else None
                require(observed['browser_actual_fps'] == fps, 'Client FPS not unique completed frames per loop duration')
                hidden = previous.get('hidden_indices', []) + ([index] if observed['visibility'] == 'hidden' else [])
                loops[loop_id] = {'index': index, 'start': start, 'render': times[-1], 'visible': visible,
                                 'hidden_indices': hidden, 'verified_fps': fps}
            observations.append(observed)
        require(session['status']['completed'] == session['status']['accepted'] == len(records) == len(session['run_ids']) and
                session['status']['last_completed_frame_status'] == previous_status, 'Completed/exported/native run count mismatch')
        coverage = {'image_ids': sorted({record['request']['image_id'] for record in records}),
                    'modes': sorted({record['request']['mode'] for record in records}),
                    'sides': sorted({record['request']['side'] for record in records})}
        prior = None
        if prior_bringup is None:
            require(len(coverage['image_ids']) >= 2 and len(coverage['modes']) >= 2 and coverage['sides'] == [256, 512],
                    'W1 two-image/two-mode/two-size coverage missing')
        else:
            # Reverify the preserved bring-up itself; a handwritten PASS JSON cannot supply coverage.
            previous_report = verify(*prior_bringup, package, allow_incomplete_display=True)
            require(previous_report['session_id'] != caps['session_id'] and
                    previous_report['archive']['sha256'] != file_info(archive_path)['sha256'], 'Supplement repeats prior session')
            prior = {key: previous_report[key] for key in ('session_id', 'archive', 'notebook', 'verified_runs', 'matched_words', 'coverage')}
        rows = list(csv.DictReader(io.StringIO(archive.read('measurements.csv').decode('utf-8-sig'))))
        require(len(rows) == len(records), 'CSV count mismatch')
        by_id = {row['run_id']: row for row in rows}
        require(len(by_id) == len(records) and set(by_id) == {record['run_id'] for record in records}, 'Duplicate/missing CSV run IDs')
        observed_by_id = {observed['run_id']: observed for observed in observations}
        for record in records:
            row = by_id[record['run_id']]
            for name in ('dma_transaction_ns', 'inference_ns'):
                require(int(row[name]) == record['timing_ns'][name], 'CSV latency mismatch')
            require(row['pl_core_frame_ns'] == row['pure_dma_transport_ns'] == '', 'CSV invented core/pure transport time')
            require(all(row[key] == str(record['request'][key]) for key in ('image_id', 'side', 'mode', 'threshold')),
                    'CSV request identity mismatch')
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
    return {'status': ('W1_DOWNLOADED_ARRAYS_AND_OBSERVATIONS_VERIFIED_NOT_FINAL_ACCEPTANCE' if display_complete else
                       'W1_NUMERIC_AND_FUNCTIONAL_EVIDENCE_VERIFIED_DISPLAY_FPS_PENDING'),
            'session_id': caps['session_id'], 'coverage': coverage, 'prior_bringup_reverified': prior,
            'archive': file_info(archive_path), 'notebook': file_info(notebook_path),
            'verified_runs': len(records), 'matched_words': sum(record['matched_words'] for record in records),
            'matched_png_images': sum(record['matched_png_images'] for record in records),
            'matched_png_values': sum(record['matched_png_values'] for record in records),
            'browser_observations': len(observations), 'runs': records, 'observations': observations,
            'lifecycle': lifecycle, 'display_loops': loops, 'visible_20_frame_loop_verified': display_complete,
            'timing_summary': timing_summary(records, observations, loops),
            'numeric_and_functional_evidence_verified': True, 'final_acceptance_pass': False,
            'pl_core_frame_ns': None, 'pure_dma_transport_ns': None,
            'formal_20_image_quality_pass': False, 'adjustable_threshold_pass': False, 'full_performance_pass': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('notebook', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--package', type=Path, default=ROOT / 'build/deploy/browser_a4_w1_r1')
    parser.add_argument('--allow-incomplete-display', action='store_true',
                        help='Offline partial audit only: keep missing visible-loop FPS explicitly PENDING, never PASS')
    parser.add_argument('--prior-archive', type=Path, help='Preserved original bring-up archive for a display-only supplement')
    parser.add_argument('--prior-notebook', type=Path, help='Executed original bring-up Notebook; reverifies its coverage')
    args = parser.parse_args()
    if bool(args.prior_archive) != bool(args.prior_notebook):
        parser.error('--prior-archive and --prior-notebook must be supplied together')
    args.destination.mkdir(parents=True, exist_ok=False)
    try:
        report = verify(args.archive, args.notebook, args.package,
                        allow_incomplete_display=args.allow_incomplete_display,
                        prior_bringup=(args.prior_archive, args.prior_notebook) if args.prior_archive else None)
    except Exception as exc:
        write_json(args.destination / 'failed_verification.json', {'status': 'FAILED_VERIFICATION', 'error': type(exc).__name__ + ': ' + str(exc)})
        raise
    write_json(args.destination / 'verification.json', report)
    print(report['status'] + ': ' + str(report['verified_runs']) + ' runs / ' + str(report['matched_words']) + ' words')
