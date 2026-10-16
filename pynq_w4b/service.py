"""Same-origin HTTP application; one worker owns all real PL operations."""
import asyncio
import csv
import copy
import io
import json
import math
import shutil
import time
import uuid
import zipfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
import tornado.web

from .evaluation import score_completed
from .protocol import Inputs, MODES, PNG_PROFILES, RequestError, REVISION, file_info, require, rgb_from_input, sha, write_json

MAX_RUNS = 309  # Three formal rounds: 3 warmup + 100 measured frames each.


class BusyError(ValueError):
    pass


def encode_png(path, array, profile, detail):
    """Lossless representation only. No resize, quantization or mask editing."""
    start = time.perf_counter_ns()
    picture = Image.fromarray(array)
    constructed = time.perf_counter_ns()
    picture.save(path, format='PNG', **PNG_PROFILES[profile])
    saved = time.perf_counter_ns()
    info = file_info(path)
    hashed = time.perf_counter_ns()
    detail.update(profile=profile, options=dict(PNG_PROFILES[profile]),
                  mode=picture.mode, shape=list(array.shape), dtype=str(array.dtype),
                  raw_timestamps_ns=[start, constructed, saved, hashed],
                  fromarray_ns=constructed-start, save_ns=saved-constructed,
                  file_hash_ns=hashed-saved, bytes=info['bytes'])
    return info


def process_run(root, inputs, hardware, job, directory):
    """Worker only. Image processing is on PL; PS decodes, scores and encodes."""
    require(shutil.disk_usage(directory).free >= 32 * 1024 * 1024, 'SD free space below 32 MiB; stop this session')
    marks = {'worker_start_ns': time.perf_counter_ns()}
    words, entry = inputs.load(job['request'])
    marks['input_ready_ns'] = time.perf_counter_ns()
    output, evidence = hardware.run(words, job['request'])
    marks.update(evidence['raw_timestamps_ns'])
    # Save the actual immutable output before GT evaluation/presentation.
    np.save(directory / 'output_packed.npy', output, allow_pickle=False)
    shutil.copyfile(root / entry['input'], directory / 'input_packed.npy')
    marks['raw_saved_ns'] = time.perf_counter_ns()
    fov = (words >> 24) != 0
    quality = score_completed(root, entry, output, fov, job['request']['mode_code'])
    marks['evaluation_end_ns'] = time.perf_counter_ns()
    rgb = rgb_from_input(words)
    arrays = {'original': rgb}
    if job['request']['mode_code'] != 0:
        enhanced = ((output >> 8) & 255).astype(np.uint8)
        mask = ((output >> 16) & 255).astype(np.uint8)
        overlay = rgb.copy()
        selected = mask != 0
        # Display-only blending of the actual PL mask; no PS segmentation.
        overlay[selected] = ((35 * rgb[selected].astype(np.uint16) + np.array([0, 16575, 0], np.uint16) + 50) // 100).astype(np.uint8)
        arrays.update(enhanced=enhanced, mask=mask, overlay=overlay,
                      response=((output >> 24) & 255).astype(np.uint8))
    marks['arrays_ready_ns'] = time.perf_counter_ns()
    encoding = {kind: {} for kind in arrays}
    images = {kind: encode_png(directory / (kind + '.png'), pixels, job['request']['png_profile'], encoding[kind])
              for kind, pixels in arrays.items()}
    marks['encoding_end_ns'] = time.perf_counter_ns()
    files = {path.name: file_info(path) for path in sorted(directory.iterdir()) if path.is_file()}
    marks['worker_result_ready_ns'] = time.perf_counter_ns()
    timing = {**evidence['timing_ns'],
              'queue_wait_ns': marks['worker_start_ns'] - job['accepted_server_ns'],
              'input_read_ns': marks['input_ready_ns'] - marks['worker_start_ns'],
              'raw_save_ns': marks['raw_saved_ns'] - marks['observer_end_ns'],
              'evaluation_ns': marks['evaluation_end_ns'] - marks['raw_saved_ns'],
              'png_encoding_ns': marks['encoding_end_ns'] - marks['evaluation_end_ns'],
              'array_decode_overlay_ns': marks['arrays_ready_ns'] - marks['evaluation_end_ns'],
              'png_fromarray_ns': sum(p['fromarray_ns'] for p in encoding.values()),
              'png_save_ns': sum(p['save_ns'] for p in encoding.values()),
              'png_file_hash_ns': sum(p['file_hash_ns'] for p in encoding.values()),
              'file_inventory_hash_ns': marks['worker_result_ready_ns'] - marks['encoding_end_ns'],
              'worker_result_ns': marks['worker_result_ready_ns'] - marks['worker_start_ns']}
    record = {**job, 'status': 'COMPLETED', 'evidence': evidence,
              'input': {'sha256': entry['input_word_sha256'], 'file': entry['input_file'],
                        'rgb_sha256': sha(rgb.tobytes()), 'geometry': entry['geometry']},
              'output': {'sha256': evidence['output_sha256'], 'shape': list(output.shape),
                         'dtype': str(output.dtype), 'words': int(output.size), 'file': files['output_packed.npy']},
              'quality': quality, 'timing_ns': timing, 'raw_timestamps_ns': marks,
              'timing_scope': 'Worker result excludes final JSON publication, HTTP/polling and browser; DMA overlaps PL. Inference includes config/allocation/native DMA/read-only snapshot. Core comes from the completed hardware snapshot and includes stream stalls; pure transport remains unavailable. Observer GPIO reads are measured separately after the inference snapshot.',
              'images': {kind: {'url': '/api/runs/' + job['run_id'] + '/images/' + kind, **info}
                         for kind, info in images.items()}, 'files': files,
              'browser_timing': None, 'formal_quality_experiment': False,
              'png_profile': job['request']['png_profile'], 'encoding_details': encoding,
              'encoding_scope': 'PS-only Pillow PNG settings; baseline is unchanged default, fast uses compress_level=1. Decoded pixels must match actual DMA exactly. No result cache. save_ns includes codec/filter/file-write; file hashes are separate. No assumption of speedup.'}
    record['overlay_presentation'] = {'green_rgb': [0, 255, 0], 'alpha_percent': 65, 'rounding': 'integer_half_up',
                                      'browser_slider': 'Presentation only; exported PNG retains fixed 65%'}
    write_json(directory / 'record.json', record)
    return record


class Manager:
    def __init__(self, root, manifest, hardware, executor=None):
        self.root, self.manifest, self.hardware = Path(root), manifest, hardware
        self.inputs = Inputs(self.root, manifest['images'])
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix='real-pl-owner')
        self.session_id = uuid.uuid4().hex
        self.directory = self.root / 'browser_results' / self.session_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.queue, self.jobs, self.nonces, self.loops = deque(), {}, {}, {}
        self.active, self.pump, self.error, self.exporting = None, None, None, False
        self.closed = False
        self.started_ns = time.perf_counter_ns()
        write_json(self.directory / 'capabilities.json', self.capabilities())
        write_json(self.directory / 'environment.json', hardware.environment)
        shutil.copyfile(self.root / 'browser_manifest.json', self.directory / 'browser_manifest.json')
        self.event('SERVICE_READY', {'hardware_state': hardware.state})

    def capabilities(self):
        return {'revision': REVISION, 'session_id': self.session_id,
                'evidence_kind': self.hardware.evidence_kind, 'board_acceptance': 'PENDING_INDEPENDENT_VERIFICATION',
                'bit': self.manifest['artifacts']['q4d_detector.bit'],
                'hwh': self.manifest['artifacts']['q4d_detector.hwh'],
                'clock_hz': 100000000, 'clock_source': 'Paired C7 RQ71 100MHz implementation plus live FCLK0 register readback',
                'dma_address': '0x40400000', 'gpio_address': '0x41200000', 'observer_address': '0x41210000',
                'algorithms': ['A', 'C2', 'C5', 'C7'], 'modes': MODES, 'threshold_range': [1, 255], 'side_choices': [256, 512],
                'png_profiles': PNG_PROFILES, 'profile_scope': 'PS image delivery only; not a PL medical parameter',
                'runtime_threshold_supported': True, 'core_cycle_readback_supported': True,
                'latched_parameter_readback_supported': True, 'algorithm_B_supported': False,
                'max_active': 1, 'max_pending': 1, 'session_run_limit': MAX_RUNS,
                'timing_notice': 'Client and board absolute clocks cannot be subtracted; double-rAF is an approximate paint marker, not physical display or algorithm 60 FPS.'}

    def event(self, kind, detail):
        with (self.directory / 'events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'event': kind, 'server_ns': time.perf_counter_ns(), 'detail': detail},
                                    ensure_ascii=False, allow_nan=False) + '\n')

    def status(self):
        return {'session_id': self.session_id, 'service_state': 'CLOSED' if self.closed else ('FAULT' if self.error else 'READY'),
                'hardware_state': self.hardware.state, 'overlay_downloads': self.hardware.downloads,
                'last_completed_frame_status': self.hardware.last_status,
                'active_run_id': self.active, 'pending': len(self.queue),
                'completed': sum(job['status'] == 'COMPLETED' for job in self.jobs.values()),
                'accepted': len(self.jobs), 'run_limit': MAX_RUNS,
                'retained_buffer_count': len(self.hardware.retained), 'error': self.error,
                'evidence_kind': self.hardware.evidence_kind, 'board_acceptance': 'PENDING_INDEPENDENT_VERIFICATION'}

    def submit(self, body):
        request = self.inputs.request(body)  # Reject unsupported config before touching hardware.
        nonce = request['client_nonce']
        if nonce in self.nonces:
            previous = self.jobs[self.nonces[nonce]]
            if previous['request'] != request:
                raise BusyError('Nonce already belongs to a different request')
            return previous  # Retry never creates an extra PL frame.
        if self.closed or self.error or self.hardware.state == 'FAULT':
            raise BusyError('Service stopped/faulted; preserve kernel, buffers and records')
        if self.exporting:
            raise BusyError('Export snapshot in progress; submit after it completes')
        if len(self.queue) + (self.active is not None) >= 2:
            raise BusyError('One active and one pending request already exist')
        if len(self.jobs) >= MAX_RUNS:
            raise BusyError('W4b session reached 309 runs; export records and finish safely')
        run_id = uuid.uuid4().hex
        config = {key: request[key] for key in ('algorithm', 'image_id', 'side', 'threshold', 'mode', 'mode_code', 'png_profile')}
        job = {'run_id': run_id, 'session_id': self.session_id, 'request': request,
               'config_id': sha(json.dumps(config, sort_keys=True, separators=(',', ':')).encode()),
               'status': 'QUEUED', 'accepted_server_ns': time.perf_counter_ns(),
               'revision': REVISION, 'hardware_identity': {'bit': self.capabilities()['bit'], 'hwh': self.capabilities()['hwh']},
               'evidence_kind': self.hardware.evidence_kind}
        (self.directory / run_id).mkdir()
        self.jobs[run_id], self.nonces[nonce] = job, run_id
        try:
            self.event('RUN_ACCEPTED', {'run_id': run_id, 'request': request})
        except Exception as exc:
            self.error = {'run_id': run_id, 'type': type(exc).__name__, 'message': str(exc),
                          'recovery': 'Accepted-request journal failed before hardware access; stop and preserve records'}
            job.update(status='FAILED', error=self.error)
            raise BusyError('Cannot persist request journal; service stopped before hardware access')
        if self.active is None:
            self.active = run_id  # Reserve the one worker immediately; pending never exceeds one.
            self.pump = asyncio.create_task(self._work())
        else:
            self.queue.append(run_id)
        return job

    async def _work(self):
        while self.active is not None and not self.error:
            run_id = self.active
            job = self.jobs[run_id]
            job['status'], self.active = 'RUNNING', run_id
            try:
                self.event('RUN_STARTED', {'run_id': run_id})
                result = await asyncio.get_running_loop().run_in_executor(
                    self.executor, process_run, self.root, self.inputs, self.hardware, job, self.directory / run_id)
                self.jobs[run_id] = result
                self.event('RUN_COMPLETED', {'run_id': run_id, 'output_sha256': result['output']['sha256']})
            except BaseException as exc:
                last = self.hardware.last_attempt
                attempt = {**last, 'raw_timestamps_ns': dict(last['raw_timestamps_ns'])} if last and last['request'] == job['request'] else None
                self.error = {'run_id': run_id, 'type': type(exc).__name__,
                              'message': str(exc) or 'Worker wait interrupted; native hardware may still be active',
                              'hardware_state': self.hardware.state,
                              'retained_buffer_count': len(self.hardware.retained),
                              'last_native_attempt': attempt,
                              'recovery': 'Stop requests. Preserve this kernel, references and records. No automatic reset, Overlay reload or CPU fallback.'}
                job.update(status='FAILED', error=self.error)
                try:
                    write_json(self.directory / run_id / 'record.json', job)
                    # A cancelled await cannot stop the native worker. Its later
                    # output record must never erase the independent fault marker.
                    write_json(self.directory / run_id / 'failure.json', job)
                    self.event('SERVICE_FAULT', self.error)
                except Exception as persistence_error:
                    # Fault protection must survive even a full/broken SD card.
                    self.error['record_write_error'] = str(persistence_error)
            finally:
                self.active = self.queue.popleft() if self.queue and not self.error else None
        if self.error:
            while self.queue:
                job = self.jobs[self.queue.popleft()]
                job.update(status='CANCELLED', error={'message': 'Previous operation faulted; no hardware access for this request'})
                try:
                    write_json(self.directory / job['run_id'] / 'record.json', job)
                except Exception as persistence_error:
                    job['error']['record_write_error'] = str(persistence_error)

    def get(self, run_id):
        if run_id not in self.jobs:
            raise KeyError('Unknown run')
        return self.jobs[run_id]

    def browser_timing(self, run_id, body):
        job = self.get(run_id)
        if self.exporting:
            raise BusyError('Export snapshot in progress; retry this observation afterwards')
        if job['status'] != 'COMPLETED':
            raise BusyError('Timing requires a completed current run')
        if job.get('browser_timing') is not None:
            raise BusyError('A first-render observation already exists for this run')
        fields = {'client_nonce', 'config_id', 'input_sha256', 'output_sha256', 'request_start_ms',
                  'result_received_ms', 'images_decoded_ms', 'render_done_ms', 'visibility', 'user_agent',
                  'loop_id', 'loop_index', 'loop_start_ms'}
        if not isinstance(body, dict) or set(body) != fields:
            raise RequestError('Invalid browser timing fields')
        expected = {'client_nonce': job['request']['client_nonce'], 'config_id': job['config_id'],
                    'input_sha256': job['input']['sha256'], 'output_sha256': job['output']['sha256']}
        if any(body[key] != value for key, value in expected.items()):
            raise RequestError('Stale or mismatched browser observation')
        times = [body[key] for key in ('request_start_ms', 'result_received_ms', 'images_decoded_ms', 'render_done_ms')]
        if not all(type(n) in (int, float) and math.isfinite(n) and n >= 0 for n in times) or times != sorted(times) or times[-1] - times[0] > 120000:
            raise RequestError('Invalid client monotonic intervals')
        if body['visibility'] not in ('visible', 'hidden') or not isinstance(body['user_agent'], str) or len(body['user_agent']) > 1000:
            raise RequestError('Invalid browser visibility/version')
        fps = None
        if body['loop_id'] is None:
            if body['loop_index'] is not None or body['loop_start_ms'] is not None:
                raise RequestError('Manual observation has no loop counters')
        else:
            import re
            loop_id, index, start = body['loop_id'], body['loop_index'], body['loop_start_ms']
            if not isinstance(loop_id, str) or re.fullmatch(r'[A-Za-z0-9_-]{8,80}', loop_id) is None or type(index) is not int or not 1 <= index <= 100:
                raise RequestError('Invalid bounded display loop')
            if type(start) not in (int, float) or not math.isfinite(start) or start < 0 or start > times[0]:
                raise RequestError('Invalid display loop start')
            previous = self.loops.get(loop_id)
            if previous is None:
                if index != 1 or start != times[0]:
                    raise RequestError('Display loop must begin at its first request')
                previous = {'index': 0, 'start': start, 'render': start, 'all_visible': True, 'config_id': job['config_id']}
            if index != previous['index'] + 1 or start != previous['start'] or times[0] < previous['render'] or job['config_id'] != previous['config_id']:
                raise RequestError('Display loop is nonconsecutive or clock scope changed')
            visible = previous['all_visible'] and body['visibility'] == 'visible'
            duration = times[-1] - start
            if visible and index >= 2 and duration > 0:
                fps = index * 1000 / duration
            self.loops[loop_id] = {'index': index, 'start': start, 'render': times[-1], 'all_visible': visible, 'config_id': job['config_id']}
        observation = {**body, 'run_id': run_id, 'session_id': self.session_id,
                       'request_to_render_ms': times[-1] - times[0],
                       'result_received_to_render_ms': times[-1] - times[1],
                       'browser_actual_fps': fps, 'evidence_kind': self.hardware.evidence_kind,
                       'scope': 'Client monotonic first-render approximation. FPS counts consecutive unique visible PL results including HTTP/poll/decode/render; no cross-clock subtraction or scanout claim.'}
        write_json(self.directory / run_id / 'browser_timing.json', observation)
        job['browser_timing'] = observation
        self.event('BROWSER_FIRST_RENDER', observation)
        return observation

    def _export(self, run_id):
        snapshot = {'status': self.status(), 'run_ids': list(self.jobs), 'export_server_ns': time.perf_counter_ns(),
                    'scope': 'W4b formal browser collection; acceptance requires independent downloaded-array verification'}
        write_json(self.directory / 'session.json', snapshot)
        csv_stream = io.StringIO(newline='')
        columns = ['run_id', 'image_id', 'side', 'mode', 'threshold', 'algorithm', 'dma_transaction_ns', 'inference_ns',
                   'pl_core_frame_ns', 'pure_dma_transport_ns', 'vessel_area_fraction', 'dice_AH', 'iou_AH',
                   'dice_VK', 'iou_VK', 'browser_request_to_render_ms', 'browser_actual_fps', 'png_profile',
                   'array_decode_overlay_ns', 'png_fromarray_ns', 'png_save_ns', 'png_file_hash_ns', 'file_inventory_hash_ns']
        writer = csv.DictWriter(csv_stream, fieldnames=columns)
        writer.writeheader()
        selected = copy.deepcopy([self.get(run_id)] if run_id else list(self.jobs.values()))
        for job in selected:
            if job['status'] != 'COMPLETED':
                continue
            row = {'run_id': job['run_id'], **{key: job['request'][key] for key in ('image_id', 'side', 'mode', 'threshold', 'algorithm')},
                   **{key: job['timing_ns'][key] for key in columns[6:10]},
                   'vessel_area_fraction': job['quality']['vessel_area_fraction']}
            for label in ('AH', 'VK'):
                for metric in ('dice', 'iou'):
                    row[metric + '_' + label] = job['quality']['annotations'].get(label, {}).get(metric)
            observed = job.get('browser_timing') or {}
            row['browser_request_to_render_ms'], row['browser_actual_fps'] = observed.get('request_to_render_ms'), observed.get('browser_actual_fps')
            row['png_profile'] = job['request']['png_profile']
            row.update({k: job['timing_ns'][k] for k in columns[-5:]})
            writer.writerow(row)
        exports = self.directory / 'exports'
        exports.mkdir(exist_ok=True)
        label = '' if self.hardware.evidence_kind == 'PYNQ_PL_DMA' else 'HOST_TEST_'
        path = exports / (label + (('run_' + run_id) if run_id else 'browser_session_' + self.session_id))
        path = path.with_suffix('.zip')
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('measurements.csv', csv_stream.getvalue().encode('utf-8-sig'))
            for name in ('capabilities.json', 'environment.json', 'browser_manifest.json', 'session.json', 'events.jsonl'):
                bundle.write(self.directory / name, name)
            for position, job in enumerate(selected, 1):
                if job['status'] in ('COMPLETED', 'FAILED', 'CANCELLED'):
                    for source in sorted((self.directory / job['run_id']).iterdir()):
                        if source.is_file() and not source.name.endswith('.tmp'):
                            bundle.write(source, job['run_id'] + '/' + source.name)
                if position % 20 == 0 or position == len(selected):
                    print('W4B_EXPORT_PROGRESS: %d/%d' % (position, len(selected)), flush=True)
        return path

    async def export(self, run_id=None):
        if run_id and self.get(run_id)['status'] not in ('COMPLETED', 'FAILED', 'CANCELLED'):
            raise BusyError('Wait for this run to finish before exporting')
        # Serialize snapshots with timing updates and native work; no half-written run.
        if self.active or self.queue or self.exporting:
            raise BusyError('Wait for the current native operation/export to complete')
        self.exporting = True
        try:
            return await asyncio.get_running_loop().run_in_executor(self.executor, self._export, run_id)
        finally:
            self.exporting = False

    def finish(self):
        if self.active or self.queue or self.exporting or self.error or self.hardware.retained or self.hardware.state != 'IDLE':
            raise BusyError('Cannot close with active/pending/faulted hardware or retained buffers')
        self.closed = True
        self.event('SERVICE_FINISHED_IDLE', self.status())


def formal_require(value, message):
    if not value:
        raise RequestError(message)


def formal_step(position):
    formal_require(type(position) is int and 0 <= position < 309, 'Formal suite is exactly 309 new PL frames')
    round_index, within = divmod(position, 103)
    return round_index + 1, ('w' if within < 3 else 'm'), (within + 1 if within < 3 else within - 2)


class FormalManager(Manager):
    """Use the proven processor, with a frozen single-tab performance schedule."""
    def __init__(self, *args, **kwargs):
        self.formal_id = None
        super().__init__(*args, **kwargs)

    def submit(self, body):
        request = self.inputs.request(body)
        fixed = dict(image_id='im0001', side=512, algorithm='C7', threshold=112, mode='final', png_profile='fast')
        formal_require(all(request[k] == v for k, v in fixed.items()), 'W4b requires fixed im0001/512/C7/T112/final/fast')
        import re
        match = re.fullmatch(r'w4b_([a-f0-9]{32})_r([123])_([wm])(\d{1,3})', request['client_nonce'])
        formal_require(match is not None, 'Use the formal W4b browser button')
        suite, repeat, phase, index = match.groups()
        formal_require(self.formal_id is None or suite == self.formal_id, 'Different browser instance; preserve current experiment')
        if request['client_nonce'] in self.nonces:
            return super().submit(body)  # Existing nonce is idempotent, never a new PL frame.
        formal_require((int(repeat), phase, int(index)) == formal_step(len(self.jobs)), 'Out-of-order formal request')
        if self.jobs:
            previous = next(reversed(self.jobs.values()))
            formal_require(previous['status'] == 'COMPLETED' and previous.get('browser_timing') is not None and
                    previous['browser_timing']['visibility'] == 'visible', 'Previous frame has no valid foreground render')
        job = super().submit(body)
        self.formal_id = suite
        return job

    def browser_timing(self, run_id, body):
        formal_require(isinstance(body, dict), 'Browser timing must be a JSON object')
        job = self.get(run_id)
        parts = job['request']['client_nonce'].split('_')
        repeat, phase_index = parts[-2], parts[-1]
        formal_require(body.get('visibility') == 'visible', 'Foreground display required; stop and preserve experiment')
        if phase_index.startswith('w'):
            formal_require(body.get('loop_id') is None, 'Warmup must not enter measured loop')
        else:
            formal_require(body.get('loop_id') == self.formal_id + '_' + repeat and
                    body.get('loop_index') == int(phase_index[1:]), 'Formal loop identity/index mismatch')
        return super().browser_timing(run_id, body)

    def formal_summary(self):
        require(len(self.jobs) == 309 and not self.active and not self.queue and not self.error and
                self.hardware.state == 'IDLE' and not self.hardware.retained, 'Formal suite incomplete/faulted')
        jobs = list(self.jobs.values())
        groups = []
        for repeat in range(1, 4):
            all_frames = jobs[(repeat-1)*103:repeat*103]
            observations = [job.get('browser_timing') for job in all_frames]
            require(all(o and o['visibility'] == 'visible' for o in observations), 'Missing foreground observations')
            require(all(o['loop_id'] is None for o in observations[:3]), 'Warmup entered measurement')
            timed = observations[3:]
            require([o['loop_index'] for o in timed] == list(range(1,101)) and
                    all(o['loop_id'] == self.formal_id + '_r%d' % repeat for o in timed), 'Measured loop differs')
            latency = [o['request_to_render_ms'] for o in timed]
            elapsed = timed[-1]['render_done_ms'] - timed[0]['request_start_ms']
            require(elapsed > 0 and timed[-1]['browser_actual_fps'] == 100000 / elapsed, 'Display FPS arithmetic differs')
            groups.append(dict(repeat=repeat, warmup=3, n=100, loop_id=timed[0]['loop_id'],
                mean_ms=float(np.mean(latency)), median_ms=float(np.median(latency)),
                p95_ms=float(np.percentile(latency,95)), elapsed_ms=elapsed, actual_fps=100000/elapsed))
        result = dict(status='COLLECTED_PENDING_DOWNLOAD_AUDIT', suite_id=self.formal_id, groups=groups,
            scope='Client same-clock full request/poll/download/decode/double-rAF; foreground required; no scanout claim')
        write_json(self.directory / 'w4b_summary.json', result)
        return result


class API(tornado.web.RequestHandler):
    def initialize(self, manager):
        self.manager = manager

    def set_default_headers(self):
        self.set_header('Cache-Control', 'no-store')
        self.set_header('X-Content-Type-Options', 'nosniff')

    def respond(self, value, status=200):
        self.set_status(status)
        self.set_header('Content-Type', 'application/json; charset=utf-8')
        self.finish(json.dumps(value, ensure_ascii=False, allow_nan=False))

    def body(self):
        origin = self.request.headers.get('Origin')
        if origin and origin not in ('http://' + self.request.host, 'https://' + self.request.host):
            raise RequestError('Use this same-origin browser application')
        if self.request.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
            raise RequestError('Send an application/json request')
        if len(self.request.body) > 8192:
            raise RequestError('JSON request too large')
        try:
            return json.loads(self.request.body, parse_constant=lambda n: (_ for _ in ()).throw(ValueError(n)))
        except (ValueError, UnicodeError):
            raise RequestError('Expected finite JSON values')

    def reject(self, exc):
        self.respond({'error': type(exc).__name__, 'message': str(exc)}, 409 if isinstance(exc, BusyError) else 422)

    def write_error(self, status_code, **kwargs):
        self.respond({'error': 'ApplicationError', 'message': 'Application exception; preserve board Notebook and records'}, status_code)


class Capabilities(API):
    def get(self):
        self.respond(self.manager.capabilities())


class Images(API):
    def get(self):
        public = self.manager.inputs.public_images()
        for image in public:
            image['variants'] = {side: {key: entry[key] for key in ('input_word_sha256', 'input_file', 'geometry')}
                                 for side, entry in self.manager.inputs.catalog[image['image_id']].items()}
            image['annotation_notice'] = 'AH/VK are evaluation-only and never passed to the hardware'
        self.respond({'images': public})


class Status(API):
    def get(self):
        self.respond(self.manager.status())


class Runs(API):
    def post(self):
        try:
            self.respond(self.manager.submit(self.body()), 202)
        except (RequestError, BusyError) as exc:
            self.reject(exc)


class Run(API):
    def get(self, run_id):
        try:
            self.respond(self.manager.get(run_id))
        except KeyError:
            self.respond({'error': 'Unknown run'}, 404)


class Timing(API):
    def post(self, run_id):
        try:
            self.respond(self.manager.browser_timing(run_id, self.body()))
        except KeyError:
            self.respond({'error': 'Unknown run'}, 404)
        except (RequestError, BusyError) as exc:
            self.reject(exc)


class ResultImage(API):
    def get(self, run_id, kind):
        try:
            job = self.manager.get(run_id)
            if job['status'] != 'COMPLETED' or kind not in job['images']:
                raise KeyError()
            self.set_header('Content-Type', 'image/png')
            self.set_header('X-Run-Id', run_id)
            self.set_header('X-Output-SHA256', job['output']['sha256'])
            self.finish((self.manager.directory / run_id / (kind + '.png')).read_bytes())
        except KeyError:
            self.respond({'error': 'Current completed image unavailable'}, 404)


class Export(API):
    async def get(self, run_id=None):
        try:
            path = await self.manager.export(run_id)
            self.set_header('Content-Type', 'application/zip')
            self.set_header('Content-Disposition', 'attachment; filename="' + path.name + '"')
            # The Q4d session has an explicit run limit; stream without holding its ZIP in RAM.
            with path.open('rb') as stream:
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    self.write(chunk)
                    await self.flush()
            self.finish()
        except KeyError:
            self.respond({'error': 'Unknown run'}, 404)
        except (RequestError, BusyError) as exc:
            self.reject(exc)


class OfflineStatic(tornado.web.StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header('Cache-Control', 'no-store')
        self.set_header('X-Content-Type-Options', 'nosniff')


def application(manager):
    args = {'manager': manager}
    return tornado.web.Application([
        (r'/api/capabilities', Capabilities, args), (r'/api/images', Images, args),
        (r'/api/status', Status, args), (r'/api/runs', Runs, args),
        (r'/api/runs/([a-f0-9]{32})', Run, args),
        (r'/api/runs/([a-f0-9]{32})/browser-timing', Timing, args),
        (r'/api/runs/([a-f0-9]{32})/images/(original|enhanced|mask|overlay|response)', ResultImage, args),
        (r'/api/runs/([a-f0-9]{32})/export', Export, args),
        (r'/api/session/export', Export, args),
        (r'/(.*)', OfflineStatic, {'path': str(manager.root / 'ui'), 'default_filename': 'index.html'})
    ], debug=False, autoreload=False, xsrf_cookies=False)
