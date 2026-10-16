"""Host-only fault tests for the runner; never counted as hardware DMA PASS."""
import importlib.util
import contextlib
import io
from pathlib import Path
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location(
    "runner", Path(__file__).resolve().parents[1] / "scripts/a0_dma_board_test.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class Buffer(np.ndarray):
    def __new__(cls, shape, dtype):
        result = np.empty(shape, dtype=dtype).view(cls)
        result.physical_address = 0x10000000
        result.freed = False
        result.flushed = False
        return result

    def flush(self):
        self.flushed = True

    def freebuffer(self):
        self.freed = True


class Channel:
    def __init__(self, parent, receive):
        self.parent = parent
        self.receive = receive
        self.transferred = 0

    def transfer(self, buf):
        if self.receive:
            assert buf.flushed
            self.parent.rx = buf
        else:
            self.parent.rx[:] = buf
            if self.parent.corrupt:
                self.parent.rx[-1] ^= np.uint32(1)
            self.transferred = buf.nbytes
            self.parent.recvchannel.transferred = buf.nbytes
            if self.parent.bad_length:
                self.parent.recvchannel.transferred -= 4

    def wait(self):
        pass


class FakeDMA:
    def __init__(self, status=2, corrupt=False, bad_length=False):
        self.status = status
        self.corrupt = corrupt
        self.bad_length = bad_length
        self.mmio = self
        self.sendchannel = Channel(self, False)
        self.recvchannel = Channel(self, True)

    def read(self, offset):
        return self.status


class RunnerTests(unittest.TestCase):
    def suite(self, dma):
        report = {"transfers": []}
        retained = []
        all_buffers = []

        def allocate(shape, dtype):
            buf = Buffer(shape, dtype)
            all_buffers.append(buf)
            return buf

        return report, retained, all_buffers, allocate

    def test_success_releases_only_completed_buffers(self):
        dma = FakeDMA()
        report, retained, buffers, allocate = self.suite(dma)
        with contextlib.redirect_stdout(io.StringIO()):
            runner.run_suite(dma, allocate, report, retained, lambda: None)
        self.assertEqual(report["status"], "PASS_ALL_EXACT_WORD_COMPARE")
        self.assertEqual(len(report["transfers"]), 70)
        self.assertEqual(retained, [])
        self.assertTrue(all(buf.freed for buf in buffers))

    def test_corruption_retains_buffers_and_never_reports_pass(self):
        dma = FakeDMA(corrupt=True)
        report, retained, buffers, allocate = self.suite(dma)
        with self.assertRaisesRegex(AssertionError, "Mismatch"):
            runner.run_suite(dma, allocate, report, retained, lambda: None)
        self.assertEqual(len(retained), 2)
        self.assertTrue(all(not buf.freed for buf in buffers))
        self.assertEqual(report["transfers"], [])

    def test_length_mismatch_retains_buffers(self):
        dma = FakeDMA(bad_length=True)
        report, retained, buffers, allocate = self.suite(dma)
        with self.assertRaisesRegex(AssertionError, "byte count"):
            runner.run_suite(dma, allocate, report, retained, lambda: None)
        self.assertEqual(len(retained), 2)
        self.assertTrue(all(not buf.freed for buf in buffers))

    def test_timeout_and_hardware_error_are_bounded(self):
        with self.assertRaises(TimeoutError):
            runner.wait_both_idle(FakeDMA(status=0), timeout=0)
        with self.assertRaises(RuntimeError):
            runner.wait_both_idle(FakeDMA(status=0x12), timeout=0)

    def test_full_suite_rejected_before_smoke_without_changing_state(self):
        context = {"report": {"status": "OVERLAY_LOADED_NO_DMA_TRANSFER"}}
        with self.assertRaisesRegex(RuntimeError, "Short loopback"):
            runner.full_test(context)
        self.assertEqual(context["report"]["status"], "OVERLAY_LOADED_NO_DMA_TRANSFER")

    def test_failed_smoke_records_stage_and_retains_buffers(self):
        dma = FakeDMA(corrupt=True)
        report, retained, buffers, allocate = self.suite(dma)
        report["status"] = "OVERLAY_LOADED_NO_DMA_TRANSFER"
        report["dma_description"] = {}

        class FakeOverlay:
            axi_dma_0 = dma

        saved_states = []
        context = {"report": report, "retained": retained, "allocate": allocate,
                   "overlay": FakeOverlay(), "driver_class": FakeDMA,
                   "save": lambda: saved_states.append(report["status"])}
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(AssertionError, "Mismatch"):
                runner.smoke_test(context)
        self.assertEqual(report["status"], "FAILED_OR_INTERRUPTED")
        self.assertEqual(report["failed_stage"], "SMOKE_TRANSFERRING_17_WORDS")
        self.assertIn("SMOKE_TRANSFERRING_17_WORDS", saved_states)
        self.assertTrue(all(not buf.freed for buf in buffers))
        self.assertEqual(report["retained_buffers"], 2)
        with self.assertRaisesRegex(RuntimeError, "Short loopback"):
            runner.full_test(context)


if __name__ == "__main__":
    unittest.main()
