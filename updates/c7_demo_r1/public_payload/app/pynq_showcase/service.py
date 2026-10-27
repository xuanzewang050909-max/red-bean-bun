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
from .single_image import select_target

MAX_RUNS = 100  # Storage bound; any positive completed count may be closed/exported.


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
    pipeline_start = time.perf_counter_ns()
    target = select_target(words, job['request'], hardware.config)
    staged_target = target is not None
    parent_binding = job.get('c7_parent')
    if parent_binding:
        parent_dir = directory.parent / parent_binding['run_id']
        require(file_info(parent_dir/'record.json') == parent_binding['record_file'], 'C7_PARENT_RECORD_CHANGED')
        parent = json.loads((parent_dir/'record.json').read_bytes())
        require(parent['status']=='COMPLETED' and parent.get('presentation_stage')=='C7_ORIGINAL'
                and parent['session_id']==job['session_id'], 'C7_PARENT_NOT_COMPLETED_OR_SAME_SESSION')
        require(staged_target and parent['input']['sha256']==sha(words.tobytes()), 'C7_PARENT_INPUT_CHANGED')
        for field in ('image_id','side','algorithm','mode','mode_code','threshold','png_profile'):
            require(parent['request'][field]==job['request'][field], 'C7_PARENT_CONFIG_CHANGED:'+field)
        require(file_info(parent_dir/'output_packed.npy')==parent['output']['file'], 'C7_PARENT_ARRAY_CHANGED')
        output=np.load(parent_dir/'output_packed.npy',allow_pickle=False)
        require(output.dtype==np.uint32 and output.shape==words.shape and sha(output.tobytes())==parent['output']['sha256'], 'C7_PARENT_WORDS_CHANGED')
        evidence=copy.deepcopy(parent['evidence'])
        evidence['counter_scope']='Original C7 parent run; reused persisted output, no new C7 transfer in this refinement request'
        marks['observer_end_ns']=time.perf_counter_ns()
        shutil.copyfile(parent_dir/'record.json',directory/'c7_parent_record.json')
    else:
        output, evidence = hardware.run(words, job['request'])
        marks.update(evidence['raw_timestamps_ns'])
    # Save the actual immutable output before GT evaluation/presentation.
    np.save(directory / 'output_packed.npy', output, allow_pickle=False)
    shutil.copyfile(root / entry['input'], directory / 'input_packed.npy')
    marks['raw_saved_ns'] = time.perf_counter_ns()
    # All four targeted default requests end at C7. Only an explicit bound
    # follow-up runs their unchanged refinement (including im0324's single core).
    refinement = None if staged_target and not parent_binding else hardware.refine(words, output, job['request'], directory)
    marks['pipeline_complete_ns'] = time.perf_counter_ns()
    fov = (words >> 24) != 0
    if refinement is None and not staged_target:
        quality = score_completed(root, entry, output, fov, job['request']['mode_code'])
    else:
        # Targeted completion does not reopen the old AH/VK quality campaign.
        count = int(np.count_nonzero((refinement['mask'] if refinement is not None else ((output>>16)&255)!=0) & fov))
        quality = dict(source='PS_COUNTS_OF_CURRENT_REAL_PL_FINAL_MASK', vessel_pixels=count,
                       fov_pixels=int(fov.sum()), vessel_area_fraction=count/int(fov.sum()),
                       annotations={}, quality_reason='原C7/专项补标对比；未进行独立GT精度评价')
    marks['evaluation_end_ns'] = time.perf_counter_ns()
    rgb = rgb_from_input(words)
    arrays = {'original': rgb}
    if job['request']['mode_code'] != 0:
        enhanced = ((output >> 8) & 255).astype(np.uint8)
        mask = ((output >> 16) & 255).astype(np.uint8)
        if refinement is not None:
            mask = refinement['mask'].astype(np.uint8)*255
        overlay = rgb.copy()
        selected = mask != 0
        # Display-only blending of the actual PL mask; no PS segmentation.
        overlay[selected] = ((35 * rgb[selected].astype(np.uint16) + np.array([0, 16575, 0], np.uint16) + 50) // 100).astype(np.uint8)
        arrays.update(enhanced=enhanced, mask=mask, overlay=overlay,
                      response=((output >> 24) & 255).astype(np.uint8))
        if refinement is not None:
            before = rgb.copy()
            old = ((output >> 16) & 255) != 0
            before[old] = ((35*rgb[old].astype(np.uint16)+np.array([0,16575,0],np.uint16)+50)//100).astype(np.uint8)
            added = rgb.copy()
            added[old] = [0,255,0]
            added[refinement['added']] = [0,255,255]
            arrays.update(before=before, added=added)
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
              'encoding_scope': 'PS-only Pillow PNG settings; baseline is unchanged default, fast uses compress_level=1. Decoded pixels match actual PL arrays. Explicit refinement reuses its SHA-bound current-session C7 parent. save_ns includes codec/filter/file-write; file hashes are separate. No assumption of speedup.'}
    record['overlay_presentation'] = {'green_rgb': [0, 255, 0], 'alpha_percent': 65, 'rounding': 'integer_half_up',
                                      'browser_slider': 'Presentation only; exported PNG retains fixed 65%'}
    record['refinement'] = refinement['record'] if refinement is not None else {'applied': False}
    record['presentation_stage'] = ('TARGETED_REFINEMENT' if parent_binding else 'C7_ORIGINAL' if staged_target else 'LEGACY_PIPELINE')
    record['refinement_available'] = bool(staged_target and not parent_binding)
    record['timing_ns']['c7_inference_ns'] = record['timing_ns']['inference_ns']
    record['timing_ns']['inference_ns'] = marks['pipeline_complete_ns']-pipeline_start
    record['timing_scope'] += ' Inference includes overlay switching when needed and raw-file persistence.'
    if refinement is not None:
        # Preserve the original C7 32-bit stream separately. Its Q7 still describes
        # C7 alone and must not be falsely re-labelled as the refined scoring head.
        record['c7_output'] = record['output']
        record['output'] = dict(sha256=refinement['record']['final_mask_sha256'],
                                shape=list(words.shape), dtype='bool', pixels=words.size,
                                file=files['final_mask.npy'], source='CURRENT_REAL_PL_REFINEMENT_MASK')
        record['timing_ns']['refinement_operations_wall_ns'] = refinement['record']['operations_wall_ns']
        record['timing_ns']['refinement_total_ns'] = refinement['record']['total_ns']
        record['timing_ns']['evaluation_ns'] = marks['evaluation_end_ns']-marks['pipeline_complete_ns']
        record['timing_scope'] += (' Target input: inference_ns encloses both overlays, raw save and exact checks. '
                                    'Core/DMA counters remain C7-only; refinement operations use host monotonic '
                                    'time including polling/journaling. Stages must not be summed twice.')
    if parent_binding:
        # Parent hardware counters remain in evidence; current-request counters
        # must not report that old C7 transaction as newly executed work.
        record['timing_ns'].update(c7_inference_ns=0,pl_core_frame_ns=0,dma_transaction_ns=0,
                                  c7_overlay_restore_ns=0,queue_wait_ns=marks['worker_start_ns']-job['accepted_server_ns'])
        record['timing_scope']='Current request reuses the SHA-bound completed original C7 arrays. No C7 inference/DMA performed here. Parent counters are historical evidence; current inference includes refinement overlay load, PL work, persistence and checks. Browser measurements exclude user waiting between steps.'
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
        self.refinement_children = {}
        self.record_seals = {}
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
                'targeted_image_optimization': {'image_ids': ['im0004','im0291','im0319','im0324'], 'side': 512, 'threshold': 112,
                    'mode': 'final', 'algorithm': 'C7', 'annotation': '此图已专项优化',
                    'dispatch': 'Exact input bytes, never GT or image name', 'refinement_clock_hz': 50000000},
                'staged_refinement': {'image_ids':['im0004','im0291','im0319','im0324'], 'default':'C7_ORIGINAL',
                    'action':'EXPLICIT_PARENT_BOUND_REFINEMENT', 'display_switch':'NO_HARDWARE'},
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
        return self._enqueue(request)

    def submit_refinement(self, parent_id, body):
        if not isinstance(body,dict) or set(body)!={'client_nonce'}:
            raise RequestError('Refinement accepts only client_nonce; parameters belong to the original run')
        parent=self.get(parent_id)
        if parent['status']!='COMPLETED' or not parent.get('refinement_available'):
            raise BusyError('Run original C7 for an eligible image first')
        request=self.inputs.request({k:(body['client_nonce'] if k=='client_nonce' else v)
                                     for k,v in parent['request'].items() if k!='mode_code'})
        existing=self.refinement_children.get(parent_id)
        if existing:
            child=self.jobs[existing]
            if child['request']['client_nonce']==request['client_nonce']:return child
            raise BusyError('This original already has a refinement request; do not run it again')
        if request['client_nonce'] in self.nonces:raise BusyError('Nonce belongs to another task')
        # An explicit follow-up is accepted only while the completed service is idle.
        if self.active or self.queue:raise BusyError('Wait for the current request before refinement')
        if file_info(self.directory/parent_id/'record.json')!=self.record_seals[parent_id]:
            raise BusyError('Original C7 record changed; preserve files, do not refine')
        binding=dict(run_id=parent_id,record_file=self.record_seals[parent_id],
                     input_sha256=parent['input']['sha256'],output_sha256=parent['output']['sha256'])
        child=self._enqueue(request,binding)
        self.refinement_children[parent_id]=child['run_id']
        return child

    def _enqueue(self, request, parent_binding=None):
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
            raise BusyError('Demo reached 100 runs; export and finish safely')
        if shutil.disk_usage(self.root).free < 512 * 1024**2:
            raise BusyError('Need 512 MiB free before a new frame; preserve/export existing records')
        run_id = uuid.uuid4().hex
        config = {key: request[key] for key in ('algorithm', 'image_id', 'side', 'threshold', 'mode', 'mode_code', 'png_profile')}
        config['c7_parent_run_id']=parent_binding['run_id'] if parent_binding else None
        job = {'run_id': run_id, 'session_id': self.session_id, 'request': request,
               'config_id': sha(json.dumps(config, sort_keys=True, separators=(',', ':')).encode()),
               'status': 'QUEUED', 'accepted_server_ns': time.perf_counter_ns(),
               'revision': REVISION, 'hardware_identity': {'bit': self.capabilities()['bit'], 'hwh': self.capabilities()['hwh']},
               'evidence_kind': self.hardware.evidence_kind}
        if parent_binding:job['c7_parent']=parent_binding
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
                self.record_seals[run_id]=file_info(self.directory/run_id/'record.json')
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
                  'loop_id', 'loop_index', 'loop_start_ms', 'page_id'}
        if not isinstance(body, dict) or set(body) != fields:
            raise RequestError('Invalid browser timing fields')
        expected = {'client_nonce': job['request']['client_nonce'], 'config_id': job['config_id'],
                    'input_sha256': job['input']['sha256'], 'output_sha256': job['output']['sha256']}
        if any(body[key] != value for key, value in expected.items()):
            raise RequestError('Stale or mismatched browser observation')
        times = [body[key] for key in ('request_start_ms', 'result_received_ms', 'images_decoded_ms', 'render_done_ms')]
        if not all(type(n) in (int, float) and math.isfinite(n) and n >= 0 for n in times) or times != sorted(times) or times[-1] - times[0] > 360000:
            raise RequestError('Invalid client monotonic intervals')
        if body['visibility'] not in ('visible', 'hidden') or not isinstance(body['user_agent'], str) or len(body['user_agent']) > 1000:
            raise RequestError('Invalid browser visibility/version')
        if not isinstance(body['page_id'], str) or __import__('re').fullmatch(r'[a-f0-9]{32}', body['page_id']) is None:
            raise RequestError('Invalid W5b page identity')
        if body['visibility'] != 'visible' or any(body[k] is not None for k in ('loop_id', 'loop_index', 'loop_start_ms')):
            raise RequestError('W5b needs a visible single-frame observation; preserve interrupted session')
        fps = None
        if body['loop_id'] is None:
            if body['loop_index'] is not None or body['loop_start_ms'] is not None:
                raise RequestError('Manual observation has no loop counters')
        else:
            import re
            loop_id, index, start = body['loop_id'], body['loop_index'], body['loop_start_ms']
            if not isinstance(loop_id, str) or re.fullmatch(r'[A-Za-z0-9_-]{8,80}', loop_id) is None or type(index) is not int or not 1 <= index <= 30:
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
                    'scope': 'Q4d bring-up only; board acceptance requires independent downloaded-array verification'}
        write_json(self.directory / 'session.json', snapshot)
        csv_stream = io.StringIO(newline='')
        columns = ['run_id', 'image_id', 'side', 'mode', 'threshold', 'algorithm', 'dma_transaction_ns', 'inference_ns',
                   'pl_core_frame_ns', 'pure_dma_transport_ns', 'vessel_area_fraction', 'dice_AH', 'iou_AH',
                   'dice_VK', 'iou_VK', 'browser_request_to_render_ms', 'browser_actual_fps', 'png_profile',
                   'presentation_stage', 'c7_parent_run_id',
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
            row['presentation_stage'] = job['presentation_stage']
            row['c7_parent_run_id'] = job.get('c7_parent', {}).get('run_id')
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
            for job in selected:
                if job['status'] in ('COMPLETED', 'FAILED', 'CANCELLED'):
                    for source in sorted((self.directory / job['run_id']).iterdir()):
                        if source.is_file() and not source.name.endswith('.tmp'):
                            bundle.write(source, job['run_id'] + '/' + source.name)
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


class Refine(API):
    def post(self, run_id):
        try:
            self.respond(self.manager.submit_refinement(run_id,self.body()),202)
        except KeyError:
            self.respond({'error':'Unknown original run'},404)
        except (RequestError,BusyError) as exc:
            self.reject(exc)


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
        (r'/api/runs/([a-f0-9]{32})/refinement', Refine, args),
        (r'/api/runs/([a-f0-9]{32})/browser-timing', Timing, args),
        (r'/api/runs/([a-f0-9]{32})/images/(original|enhanced|mask|overlay|response|before|added)', ResultImage, args),
        (r'/api/runs/([a-f0-9]{32})/export', Export, args),
        (r'/api/session/export', Export, args),
        (r'/(.*)', OfflineStatic, {'path': str(manager.root / 'ui'), 'default_filename': 'index.html'})
    ], debug=False, autoreload=False, xsrf_cookies=False)
