"""Host fault injection for A1 deployment runner, never a board PASS."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import a1_point_board_test as runner
from software.reference import LUT
from test_a0_board_runner import Buffer


class FakeGPIO:
    def __init__(self):
        self.control = 0
        self.status = 0
        self.channel1 = SimpleNamespace(write=self.write)
        self.channel2 = SimpleNamespace(read=lambda: self.status)
    def write(self, value, mask):
        self.control = value & mask


class FakeDMA:
    def __init__(self, gpio, corrupt=False, counter_error=False, bad_length=False):
        self.gpio = gpio
        self.corrupt, self.counter_error, self.bad_length = corrupt, counter_error, bad_length
        self.mmio = SimpleNamespace(read=lambda offset: 2)
        self.recvchannel = SimpleNamespace(transfer=self.receive, wait=lambda: None, transferred=0)
        self.sendchannel = SimpleNamespace(transfer=self.send, wait=lambda: None, transferred=0)
    def receive(self, buffer):
        assert buffer.flushed
        self.rx = buffer
    def send(self, buffer):
        # Fake device computes via the already independently tested golden LUT.
        g = (np.asarray(buffer) >> 8) & 255
        mode = self.gpio.control & 3
        self.rx[:] = buffer if mode == 0 else g | ((g if mode == 1 else LUT[g].astype(np.uint32)) << 8)
        if self.corrupt:
            self.rx[-1] ^= np.uint32(1)
        self.sendchannel.transferred = buffer.nbytes
        self.recvchannel.transferred = buffer.nbytes - (4 if self.bad_length else 0)
        count = (self.gpio.status & 0x3FFF) + 1
        self.gpio.status = count | (count << 14) | (1 << 28 if self.counter_error else 0)


class PointRunnerTests(unittest.TestCase):
    def context(self, **faults):
        gpio = FakeGPIO()
        buffers = []
        def allocate(shape, dtype):
            buffer = Buffer(shape, dtype)
            buffer.physical_address = 0x10000000 + (len(buffers) % 2) * 0x00200000
            buffers.append(buffer)
            return buffer
        return {"gpio": gpio, "dma": FakeDMA(gpio, **faults), "allocate": allocate,
                "retained": [], "save": lambda: None,
                "report": {"status": "A1_LOADED_NO_TRANSFER", "transfers": []}}, buffers

    def test_all_modes_and_lut_levels_match_independent_golden(self):
        words = np.arange(256, dtype=np.uint32) << 8
        np.testing.assert_array_equal(runner.point_expected(words, 0), words)
        np.testing.assert_array_equal((runner.point_expected(words, 1) >> 8) & 255, np.arange(256))
        np.testing.assert_array_equal((runner.point_expected(words, 2) >> 8) & 255, LUT)

    def test_full_suite_requires_smoke_and_checks_17_complete_frames(self):
        context, buffers = self.context()
        with self.assertRaises(RuntimeError): runner.full_a1(context)
        with contextlib.redirect_stdout(io.StringIO()):
            runner.smoke_a1(context)
            runner.full_a1(context)
        self.assertEqual(len(context["report"]["transfers"]), 17)
        self.assertEqual(context["report"]["status"], "A1_PASS_17_POINT_FRAMES_NOT_FULL_MEDICAL_ALGORITHM")
        self.assertEqual(context["retained"], [])
        self.assertTrue(all(buffer.freed for buffer in buffers))

    def test_corruption_counter_error_and_bad_length_retain_buffers(self):
        for fault in ("corrupt", "counter_error", "bad_length"):
            with self.subTest(fault=fault):
                context, buffers = self.context(**{fault: True})
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(AssertionError):
                    runner.smoke_a1(context)
                self.assertEqual(context["report"]["status"], "FAILED_OR_INTERRUPTED")
                self.assertEqual(context["report"]["transfers"], [])
                self.assertEqual(len(context["retained"]), 2)
                self.assertTrue(all(not buffer.freed for buffer in buffers))
                with self.assertRaises(RuntimeError): runner.full_a1(context)

    def test_invalid_size_rejected_before_allocation_and_mmio(self):
        context, buffers = self.context()
        with self.assertRaises(ValueError): runner.transfer_a1(context, 17, 2, "ramp")
        self.assertEqual(buffers, [])


if __name__ == "__main__":
    unittest.main()
