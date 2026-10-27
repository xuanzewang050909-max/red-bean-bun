"""C7 dispatch for byte-identified targeted inputs. Import never accesses hardware.

The original C7 DMA words remain unmodified. A second, already verified PL
overlay receives live RGB/FOV/C7 mask words and computes the added/final mask.
Reference hashes only reject mismatches; no reference mask is sent or returned.
"""
import importlib
import inspect
import json
import platform
import sys
import threading
import time
from pathlib import Path

import numpy as np

from .hardware import PynqHardware
from .protocol import file_info, require, sha, write_json


def select_target(words, request, config):
    if not (request['algorithm'] == 'C7' and request['side'] == 512
            and request['mode_code'] == 3 and request['threshold'] == 112
            and words.dtype == np.uint32 and words.shape == (512, 512)):
        return None
    digest = sha(words.tobytes())
    targets = [t for t in config['targets'].values() if t['input_word_sha256'] == digest]
    require(len(targets) <= 1, 'AMBIGUOUS_TARGET_IDENTITY')
    return targets[0] if targets else None


def eligible(words, request, config):
    return select_target(words, request, config) is not None


def pack_live_input(words, c7, config):
    require(sha(c7.tobytes()) == config['c7_output_word_sha256'],
            'C7_LIVE_PARENT_MISMATCH: preserve raw output; do not refine')
    old = ((c7 >> 16) & 255) != 0
    # Bit packing only, no PS vessel identification/selection.
    packed = words | (old.astype(np.uint32) << 25)
    require(sha(packed.tobytes()) == config['refinement_input_raw_sha256'],
            'REFINEMENT_INPUT_BINDING_MISMATCH')
    return packed


def decode_workspace(actual, words, c7, config):
    n = words.size
    require(actual.dtype == np.uint32 and actual.shape == (6*n+32,), 'WORKSPACE_LAYOUT')
    require(np.all(actual[6*n:] == np.uint32(0xdeadbeef)), 'WORKSPACE_GUARD')
    require(sha(actual[:6*n].tobytes()) == config['expected_workspace_raw_sha256'],
            'PL_WORKSPACE_NUMERIC_MISMATCH')
    flags = actual[5*n:6*n].reshape(words.shape)
    require(np.all((flags & np.uint32(0xfffffff8)) == 0), 'INVALID_OUTPUT_FLAGS')
    mask, added, uncertain = [(flags & bit) != 0 for bit in (1, 2, 4)]
    old = ((c7 >> 16) & 255) != 0
    require(not np.any(old & ~mask), 'OLD_MASK_DAMAGED')
    require(np.array_equal(mask, old | added) and not np.any(old & added), 'UNION_LAYOUT')
    require(not np.any(mask & ((words >> 24) == 0)), 'OUTSIDE_FOV')
    require(sha(mask.tobytes()) == config['expected_final_mask_raw_sha256'], 'FINAL_MASK_MISMATCH')
    return mask, added, uncertain


def helpers(root):
    payload = Path(root) / 'refinement'
    sys.path.insert(0, str(payload))
    try:
        for name in ('refinement_clock_contract', 'transport', 'evidence_io', 'board_run'):
            if name in sys.modules:
                require(Path(sys.modules[name].__file__).resolve() == (payload/(name+'.py')).resolve(),
                        'STALE_MODULE: use a fresh dedicated web kernel: ' + name)
            importlib.import_module(name)
        board = sys.modules['board_run']
        board.verify(payload)
        return board
    finally:
        sys.path.remove(str(payload))


class IntegratedHardware:
    evidence_kind = 'PYNQ_PL_DMA'

    def __init__(self, root):
        self.root = Path(root)
        self.config = json.loads((self.root/'integration.json').read_bytes())
        self.base = PynqHardware(self.root)
        self.completed_c7_instances = []
        self.refinement_context = None
        self.overlay_mode = 'C7'
        self.fault = False
        self.refinement_busy = False
        self.total_downloads = 0
        self.environment = None
        self.last_attempt = None
        self.last_status = None

    @property
    def retained(self):
        return self.base.retained + (self.refinement_context['buffers'] if self.refinement_context else [])

    @property
    def state(self):
        if self.fault:
            return 'FAULT'
        if self.refinement_busy:
            return 'RUNNING'
        return self.base.state if self.overlay_mode == 'C7' else 'IDLE'

    @property
    def downloads(self):
        return self.total_downloads

    def prepare(self):
        self.board = helpers(self.root)
        self.base.prepare()
        self.environment = dict(self.base.environment)
        self.environment['targeted_image_integration'] = self.config

    def open(self):
        self.owner = threading.get_ident()
        self.base.open()
        self.total_downloads += 1
        self.environment.update(self.base.environment)

    def run(self, words, request):
        require(not self.fault and threading.get_ident() == self.owner, 'WORKER_OR_FAULT')
        self.last_attempt = dict(request=dict(request), phase='C7_PREPARE', raw_timestamps_ns={})
        try:
            # Only a NEW explicit request may restore C7 after a completed repair.
            # This is planned overlay switching, never recovery from a failed run.
            switch_start = time.perf_counter_ns()
            if self.overlay_mode == 'REFINEMENT_COMPLETE':
                require(not self.retained, 'BUFFERS_REMAIN')
                self.completed_c7_instances.append(self.base)
                self.base = PynqHardware(self.root)
                self.base.prepare()
                self.base.open()
                self.total_downloads += 1
                self.overlay_mode = 'C7'
                restore_ns = time.perf_counter_ns()-switch_start
            else:
                restore_ns = 0
            output, evidence = self.base.run(words, request)
            self.last_attempt = self.base.last_attempt
            self.last_status = self.base.last_status
            evidence['timing_ns']['c7_overlay_restore_ns'] = restore_ns
            evidence['overlay_downloads_at_c7'] = self.total_downloads
            evidence['counter_scope'] = 'C7 counters restart with each planned C7 overlay load; per-run latched checks remain exact'
            return output, evidence
        except BaseException:
            self.fault = True
            if self.base.last_attempt:
                self.last_attempt = self.base.last_attempt
            raise

    def refine(self, words, c7, request, directory):
        target = select_target(words, request, self.config)
        if target is None:
            return None
        require(not self.fault and threading.get_ident() == self.owner, 'WORKER_OR_FAULT')
        require(self.base.state == 'IDLE' and not self.retained, 'C7_NOT_COMPLETED')
        self.refinement_busy = True
        ctx = dict(dest=Path(directory), start=time.perf_counter(), phase='REFINEMENT_PREPARE',
                   buffers=[], failed=False)
        self.refinement_context = ctx
        self.last_attempt = dict(request=dict(request), phase=ctx['phase'], raw_timestamps_ns={})
        board = self.board
        start_ns = time.perf_counter_ns()
        try:
            packed = pack_live_input(words, c7, target)
            board.persist(ctx, 'refinement_input', packed)
            from pynq import Overlay, allocate, Clocks
            import pynq
            require(pynq.__version__ == '3.0.1' and platform.machine() in ('armv7l', 'armv7'), 'PYNQ_RUNTIME')
            payload = self.root/target['payload']
            contract = json.loads((payload/'runtime_contract.json').read_bytes())
            runtime = {}
            for name, obj in (('Overlay', Overlay), ('allocate', allocate)):
                info = file_info(inspect.getfile(obj))
                require(info == {k: contract[name][k] for k in ('bytes','sha256')}, 'RUNTIME_SOURCE:'+name)
                runtime[name] = info
            write_json(Path(directory)/'refinement_runtime.json', runtime)
            write_json(Path(directory)/'refinement_boot.json', board.evidence_io.boot_context())
            overlay = board.call(ctx, 'REFINEMENT_METADATA',
                                 lambda: Overlay(str(payload/'single_repair.bit'), download=False))
            ctx['overlay'] = overlay
            require(overlay.ip_dict['repair_0']['type'] == 'xilinx.com:hls:valley_repair:1.0'
                    and overlay.ip_dict['repair_0']['phys_addr'] == 0x43c00000, 'REFINEMENT_ABI')
            load_start = time.perf_counter_ns()
            board.call(ctx, 'REFINEMENT_DOWNLOAD', overlay.download)
            self.total_downloads += 1
            load_ns = time.perf_counter_ns()-load_start
            clock = board.call(ctx, 'REFINEMENT_CLOCK',
                               lambda: board.require_refinement_clock(Clocks, overlay.clock_dict))
            ip = overlay.repair_0
            n = packed.size
            buffer = board.call(ctx, 'ALLOCATE', lambda: allocate((6*n+32,), dtype=np.uint32), words=6*n+32)
            ctx['buffers'].append(buffer)
            buffer[:] = np.uint32(0xdeadbeef)
            buffer[:n] = packed.ravel()  # The only image written: CURRENT RGB/FOV/C7.
            address = int(buffer.physical_address)
            require(address % 4 == 0 and 0 <= address <= 0x20000000-buffer.nbytes, 'BUFFER_RANGE')
            board.call(ctx, 'SYNC_TO_DEVICE', buffer.flush)
            controls = [(0x18,address),(0x28,512),(0x30,512),(0x38,6*n)]
            if target['profile'] is not None:
                controls.append((0x40,target['profile']))
            for reg, value in controls:
                board.call(ctx, 'CONTROL_WRITE', lambda r=reg,v=value: ip.write(r,v), offset=reg,value=value)
                read = board.call(ctx, 'CONTROL_READBACK', lambda r=reg: int(ip.read(r)), offset=reg)
                require(read == value, 'CONTROL_READBACK')
            compute_start = time.perf_counter_ns()
            for index, op in enumerate([0,1,2]+[3]*16+[4]):
                ctx['phase'] = 'REFINEMENT_OP_'+str(index)
                self.last_attempt['phase'] = ctx['phase']
                board.transaction(ctx, ip, op)
            compute_ns = time.perf_counter_ns()-compute_start
            board.call(ctx, 'SYNC_FROM_DEVICE', buffer.invalidate)
            actual = np.array(buffer, dtype=np.uint32, copy=True)
            actual_file = board.persist(ctx, 'refinement_actual', actual)
            mask, added, uncertain = decode_workspace(actual, words, c7, target)
            files = {name: board.persist(ctx, name, array) for name,array in
                     (('final_mask',mask),('added_mask',added),('uncertain_mask',uncertain))}
            require(overlay.is_loaded(), 'OVERLAY_CHANGED_DURING_REFINEMENT')
            board.call(ctx, 'RELEASE_COMPLETED_BUFFER', buffer.freebuffer)
            require(ctx['buffers'].pop() is buffer, 'BUFFER_OWNERSHIP')
            self.overlay_mode = 'REFINEMENT_COMPLETE'
            ctx['phase'] = 'COMPLETE'
            record = dict(applied=True, annotation='此图已专项优化', algorithm_name='C7',
                          source='REAL_PYNQ_PL', implementation=target['implementation'],
                          target_image=target['image_id'],profile=target['profile'],
                          refinement_artifacts={name:file_info(payload/name) for name in ('single_repair.bit','single_repair.hwh')},
                          input_from='CURRENT_REQUEST_RGB_FOV_AND_CURRENT_C7_PL_MASK',
                          image_identity_sha256=sha(words.tobytes()), c7_raw_sha256=sha(c7.tobytes()),
                          final_mask_sha256=sha(mask.tobytes()), files=files, actual=actual_file,
                          added_pixels=int(added.sum()), old_pixels=int(np.count_nonzero((c7>>16)&255)),
                          final_pixels=int(mask.sum()), uncertain_pixels=int(uncertain.sum()),
                          clock=clock, overlay_load_ns=load_ns, operations_wall_ns=compute_ns,
                          total_ns=time.perf_counter_ns()-start_ns, downloads=self.total_downloads,
                          operation_count=20, board_numeric='ALL_WORKSPACE_WORDS_MATCH_FIXED_REFERENCE',
                          quality='TARGETED_IMAGE_VISUAL_REVIEW_ONLY', inference_on_PS=False,
                          timing_scope='operations_wall_ns includes polling/journal overhead; not a hardware cycle counter',
                          next_request='Reload original 100MHz C7 only on the next explicit request; no retry')
            write_json(Path(directory)/'refinement_record.json', record)
            self.refinement_busy = False
            return dict(mask=mask, added=added, uncertain=uncertain, record=record)
        except BaseException as exc:
            self.fault = True
            ctx['failed'] = True
            self.last_attempt.update(phase=ctx['phase'], error=type(exc).__name__+': '+str(exc))
            write_json(Path(directory)/'refinement_FAULT.json', self.last_attempt)
            raise
