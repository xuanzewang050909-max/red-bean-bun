"""HOST TEST ONLY: real official SDMA methods with simulated MMIO/PL/DDR.

CPU golden generation is confined to this test module. It is never deployed.
"""
import ast
import importlib.util
import threading
import time
import types
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_a4_vectors import expected_words
from pynq_app.hardware import PynqHardware


def sdma_class():
    path = ROOT / 'references/PYNQ/v3.0.1/pynq/lib/dma.py'
    tree = ast.parse(path.read_bytes())
    node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == '_SDMAChannel')
    scope = {'DMA_TYPE_RX': 0, 'DMA_TYPE_TX': 1}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), scope)
    return scope['_SDMAChannel']


class Buffer(np.ndarray):
    def __new__(cls, shape, dtype, address, role, owner):
        value = np.empty(shape, dtype=dtype).view(cls)
        value.physical_address, value.role, value.owner = address, role, owner
        value.cacheable, value.coherent, value.freed = True, False, False
        return value

    def flush(self):
        self.owner.calls.append(self.role + '.flush')

    def invalidate(self):
        self.owner.calls.append(self.role + '.invalidate')
        if self.owner.pending is not None:
            self[:] = self.owner.pending.reshape(-1)

    def freebuffer(self):
        self.owner.calls.append(self.role + '.free')
        if self.owner.fault == 'free_' + self.role:
            raise RuntimeError('HOST injected free fault')
        self.freed = True


class Channel:
    def __init__(self, gpio, output):
        self.gpio, self.output = gpio, output

    def read(self):
        return self.gpio.status

    def write(self, value, mask):
        self.gpio.control = value

    def setdirection(self, direction):
        pass


class GPIO:
    def __init__(self):
        self.status, self.control = 0, 0
        self.channel1, self.channel2 = Channel(self, True), Channel(self, False)


class MMIO:
    def __init__(self, owner):
        self.owner = owner
        self.regs = {0x04: 2, 0x34: 2}

    def read(self, offset):
        return self.regs.get(offset, 0)

    def write(self, offset, value):
        self.regs[offset] = value
        if offset in (0x28, 0x58):
            self.owner.calls.append(('tx' if offset == 0x28 else 'rx') + '.transfer')
        if offset == 0x28:
            if self.owner.delay:
                time.sleep(self.owner.delay)
            tx = self.owner.buffers[-2]
            self.owner.pending = expected_words(np.asarray(tx).reshape(self.owner.side, self.owner.side), self.owner.gpio.control & 3)
            count = ((self.owner.gpio.status & 0x3fff) + 1) & 0x3fff
            self.owner.gpio.status = count | (count << 14)
            fault = self.owner.fault
            if fault == 'raw_corrupt':
                self.owner.pending[0, 0] ^= np.uint32(1)
            if fault == 'nonbinary':
                self.owner.pending[0, 0] |= np.uint32(17 << 16)
            if fault == 'outside_fov':
                self.owner.pending[0, 0] |= np.uint32(255 << 16)
            if fault == 'counter':
                self.owner.gpio.status |= 1 << 28
            if fault == 'bytes':
                self.regs[0x58] -= 4
            if fault == 'dma_error':
                self.regs[0x34] = 0x42


class HostHardware(PynqHardware):
    evidence_kind = 'HOST_TEST_DOUBLE_NOT_BOARD'

    def __init__(self, root, fault=None, delay=0):
        super().__init__(root)
        self.fault, self.delay = fault, delay
        self.buffers, self.calls, self.pending = [], [], None
        self.state = 'PRECHECK_FPGA_UNCHANGED'
        self.environment = {'evidence_kind': self.evidence_kind, 'python': sys.version.split()[0],
                            'warning': 'Simulated PL/MMIO. No new board test or real performance.'}

    def open(self):
        self.owner, self.downloads = threading.get_ident(), 1
        self.gpio = GPIO()
        self.overlay = types.SimpleNamespace(is_loaded=lambda: self.fault != 'overlay')
        mmio = MMIO(self)
        original = sdma_class()
        self.dma = types.SimpleNamespace(mmio=mmio,
            sendchannel=original(mmio, (1 << 23) - 1, 8, 1, False),
            recvchannel=original(mmio, (1 << 23) - 1, 4, 0, False))
        path = self.root / 'a0_dma_board_test.py'
        spec = importlib.util.spec_from_file_location('host_original_wait', path)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        def poll(dma):
            self.calls.append('bounded.poll')
            if self.fault == 'timeout':
                raise TimeoutError('HOST injected bounded timeout')
            return helper.wait_both_idle(dma)
        self.wait_both_idle = poll
        self.allocate = self._allocate
        self.state, self.last_status = 'IDLE', 0

    def _allocate(self, shape, dtype):
        role = 'tx' if len(self.buffers) % 2 == 0 else 'rx'
        if self.fault == 'allocation' and role == 'rx':
            raise RuntimeError('HOST injected second allocation failure')
        address = 0x10000000 + (0 if role == 'tx' else 0x00200000)
        if self.fault == 'alignment':
            address += 4
        if self.fault == 'overlap':
            address = 0x10000000
        value = Buffer(shape, dtype, address, role, self)
        self.buffers.append(value)
        self.side = int(np.sqrt(shape[0]))
        return value
