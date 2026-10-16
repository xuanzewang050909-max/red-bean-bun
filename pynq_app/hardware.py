"""Thin application adapter around unchanged official DMA, GPIO and allocate.

No video, CPU medical reference, label reader or kernel/cache override is used.
The unchanged released A0 helper supplies the already verified bounded poll.
"""
import importlib.util
import inspect
import platform
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .protocol import file_info, require, sha


def buffer_info(buffer):
    return {'physical_address': int(buffer.physical_address), 'nbytes': int(buffer.nbytes),
            'shape': list(buffer.shape), 'strides': list(buffer.strides), 'dtype': str(buffer.dtype),
            'cacheable': bool(buffer.cacheable), 'coherent': bool(buffer.coherent)}


def check_metadata(overlay):
    dma, gpio = overlay.ip_dict['axi_dma_0'], overlay.ip_dict['point_control']
    require(dma['type'] == 'xilinx.com:ip:axi_dma:7.1' and dma['phys_addr'] == 0x40400000, 'Wrong DMA mapping')
    expected = {'c_include_sg': 0, 'c_micro_dma': 0, 'c_sg_length_width': 23,
                'c_m_axis_mm2s_tdata_width': 32, 'c_s_axis_s2mm_tdata_width': 32,
                'c_m_axi_mm2s_data_width': 64, 'c_m_axi_s2mm_data_width': 32}
    require(all(int(dma['parameters'][key]) == value for key, value in expected.items()), 'Wrong original DMA parameters')
    require(gpio['type'] == 'xilinx.com:ip:axi_gpio:2.0' and gpio['phys_addr'] == 0x41200000, 'Wrong GPIO mapping')
    expected = {'C_IS_DUAL': 1, 'C_GPIO_WIDTH': 32, 'C_GPIO2_WIDTH': 32, 'C_ALL_OUTPUTS': 1,
                'C_ALL_INPUTS_2': 1, 'C_INTERRUPT_PRESENT': 0}
    require(all(int(gpio['parameters'][key]) == value for key, value in expected.items()), 'Wrong original GPIO parameters')


class PynqHardware:
    evidence_kind = 'PYNQ_PL_DMA'

    def __init__(self, root):
        self.root = Path(root)
        self.retained = []
        self.state = 'NOT_LOADED'
        self.owner = None
        self.downloads = 0
        self.last_status = None
        self.environment = None
        self.last_attempt = None

    def prepare(self):
        import pynq
        from pynq import Overlay, allocate
        from pynq.lib.dma import DMA
        from pynq.lib.axigpio import AxiGPIO
        require(pynq.__version__ == '3.0.1' and platform.machine() in ('armv7l', 'armv7'), 'Use measured PYNQ-Z2 3.0.1')
        require(self.state == 'NOT_LOADED' and not self.retained, 'Prepare once with no retained buffers')
        self.overlay = Overlay(str(self.root / 'a4_segmentation.bit'), download=False)
        check_metadata(self.overlay)
        self.allocate, self.dma_type, self.gpio_type = allocate, DMA, AxiGPIO
        spec = importlib.util.spec_from_file_location('retina_released_a0_wait', self.root / 'a0_dma_board_test.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.wait_both_idle = module.wait_both_idle
        self.environment = {'pynq': pynq.__version__, 'python': platform.python_version(),
                            'kernel': platform.release(), 'machine': platform.machine(),
                            'board_clock_utc_unverified': datetime.now(timezone.utc).isoformat(),
                            'runtime_driver_sources': {name: {'path': inspect.getfile(value), **file_info(inspect.getfile(value))}
                                                       for name, value in (('DMA', DMA), ('AxiGPIO', AxiGPIO), ('allocate', allocate), ('Overlay', Overlay))}}
        self.state = 'PRECHECK_FPGA_UNCHANGED'

    def open(self):
        require(self.state == 'PRECHECK_FPGA_UNCHANGED' and self.downloads == 0, 'Load once after precheck')
        self.owner = threading.get_ident()
        try:
            self.overlay.download()
            self.downloads += 1
            self.dma, self.gpio = self.overlay.axi_dma_0, self.overlay.point_control
            require(isinstance(self.dma, self.dma_type) and isinstance(self.gpio, self.gpio_type), 'Official drivers did not bind')
            self.gpio.channel1.setdirection('out')
            self.gpio.channel2.setdirection('in')
            require(int(self.gpio.channel2.read()) == 0, 'Frame state not reset')
            self.state, self.last_status = 'IDLE', 0
        except BaseException:
            self.state = 'FAULT'
            raise

    def run(self, words, request):
        require(threading.get_ident() == self.owner, 'Only the single hardware worker may use DMA')
        require(self.state == 'IDLE' and not self.retained, 'Hardware is not idle or failure buffers remain')
        side, mode = request['side'], request['mode_code']
        require(side in (256, 512) and mode in (0, 1, 2, 3) and request['threshold'] == 28,
                'Unsupported PL configuration')
        require(words.dtype == np.uint32 and words.shape == (side, side), 'Wrong input')
        self.state = 'RUNNING'
        marks = {}
        self.last_attempt = {'request': dict(request), 'phase': 'BEFORE_CONFIG', 'raw_timestamps_ns': marks}
        try:
            require(self.overlay.is_loaded(), 'Another application changed the loaded Overlay')
            before = int(self.gpio.channel2.read())
            require(before >> 28 == 0 and (before & 0x3fff) == ((before >> 14) & 0x3fff), 'Frame state/error mismatch before request')
            marks['config_start_ns'] = time.perf_counter_ns()
            control = mode | (4 if side == 256 else 0)
            self.gpio.channel1.write(control, 0xffffffff)
            self.last_attempt['requested_control_word'] = control
            marks['config_end_ns'] = time.perf_counter_ns()
            tx = self.allocate(shape=(side * side,), dtype=np.uint32)
            self.retained.append(tx)
            rx = self.allocate(shape=(side * side,), dtype=np.uint32)
            self.retained.append(rx)
            self.last_attempt['phase'] = 'BUFFERS_ALLOCATED'
            nbytes = side * side * 4
            for buffer in (tx, rx):
                require(buffer.dtype == np.uint32 and buffer.shape == (side * side,) and buffer.strides == (4,) and
                        buffer.physical_address % 8 == 0 and 0x100000 <= buffer.physical_address <= 0x20000000 - nbytes,
                        'Invalid native algorithm buffer')
            require(abs(tx.physical_address - rx.physical_address) >= nbytes, 'Algorithm buffers overlap')
            tx[:] = words.reshape(-1)
            rx[:] = np.uint32(0xA55AA55A)
            rx.flush()
            marks['dma_start_ns'] = time.perf_counter_ns()
            self.dma.recvchannel.transfer(rx)
            self.last_attempt['phase'] = 'RECEIVE_ARMED'
            self.dma.sendchannel.transfer(tx)
            self.last_attempt['phase'] = 'TRANSFER_STARTED'
            statuses = self.wait_both_idle(self.dma)
            self.dma.sendchannel.wait()
            self.dma.recvchannel.wait()
            marks['dma_end_ns'] = time.perf_counter_ns()
            self.last_attempt['phase'] = 'OFFICIAL_WAITS_COMPLETED'
            require(all(value & 2 and not value & 0x771 for value in statuses.values()), 'DMA halted or failed')
            send_bytes, recv_bytes = int(self.dma.sendchannel.transferred), int(self.dma.recvchannel.transferred)
            require(send_bytes == recv_bytes == nbytes, 'DMA byte count mismatch')
            after = int(self.gpio.channel2.read())
            count = ((before & 0x3fff) + 1) & 0x3fff
            require(after == (count | (count << 14)), 'PL frame counters or sticky errors differ')
            require(self.overlay.is_loaded(), 'Overlay changed during request')
            marks['snapshot_start_ns'] = time.perf_counter_ns()
            output = np.empty((side, side), dtype=np.uint32)
            np.copyto(output, np.asarray(rx).reshape(side, side), casting='no')
            output.setflags(write=False)
            marks['snapshot_end_ns'] = time.perf_counter_ns()
            if mode == 0:
                require(np.array_equal(output, words), 'Bypass output differs from actual input')
            else:
                require(np.array_equal(output & 255, (words >> 8) & 255), 'PL raw-green channel differs')
                mask = (output >> 16) & 255
                require(np.all((mask == 0) | (mask == 255)), 'Output mask is not binary; stale/invalid DMA data')
                if mode == 3:
                    require(np.all(mask[(words >> 24) == 0] == 0), 'Final PL mask outside FOV')
            output_sha = sha(output.tobytes())
            record = {'evidence_kind': self.evidence_kind, 'requested_control_word': control,
                      'hardware_latched_parameter_readback': None,
                      'config_evidence': 'Host control submission plus completed PL counters; threshold fixed by immutable firmware. No latched readback capability.',
                      'frame_status_before': before, 'frame_status_after': after, 'frame_count': count,
                      'frame_counter_wrapped': count == 0, 'dma_status': statuses,
                      'send_bytes': send_bytes, 'recv_bytes': recv_bytes,
                      'buffers': {'tx': buffer_info(tx), 'rx': buffer_info(rx)}, 'output_sha256': output_sha,
                      'raw_timestamps_ns': marks,
                      'timing_ns': {'config_ns': marks['config_end_ns'] - marks['config_start_ns'],
                                    'dma_transaction_ns': marks['dma_end_ns'] - marks['dma_start_ns'],
                                    'cpu_snapshot_ns': marks['snapshot_end_ns'] - marks['snapshot_start_ns'],
                                    'inference_ns': marks['snapshot_end_ns'] - marks['config_start_ns'],
                                    'pl_core_frame_ns': None, 'pl_core_cycles': None, 'pure_dma_transport_ns': None},
                      'numeric_validation': 'Structural/raw-channel/binary/FOV checks only; download raw NPY for independent full M0 comparison.',
                      'native_cache_policy': 'Unmodified official transfer/wait/flush/invalidate; cacheable flag is not kernel mapping proof.'}
            rx.freebuffer()
            require(self.retained.pop() is rx, 'Receive ownership changed')
            tx.freebuffer()
            require(self.retained.pop() is tx, 'Send ownership changed')
            self.state, self.last_status = 'IDLE', after
            self.last_attempt['phase'] = 'COMPLETED_AND_RELEASED'
            return output, record
        except BaseException as exc:
            self.state = 'FAULT'
            self.last_attempt['error'] = type(exc).__name__ + ': ' + str(exc)
            raise
