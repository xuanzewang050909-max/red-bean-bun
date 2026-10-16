"""A3 host reference/fault regressions. Fake DMA is never a board result."""
import contextlib
import copy
import hashlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import a3_background_board_test as runner
from a2_gaussian_board_test import gaussian_expected
from a1_point_board_test import notebook_code_hash
from prepare_a3_vectors import expected_words, diagnostic_pattern
from test_a0_board_runner import Buffer
from test_a1_board_runner import FakeGPIO, FakeDMA


class BackgroundFakeDMA(FakeDMA):
    def send(self, buffer):
        side = int(round(np.sqrt(buffer.size)))
        words = np.asarray(buffer).reshape(side, side)
        self.rx[:] = expected_words(words, self.gpio.control & 3).reshape(-1)
        if self.corrupt:
            self.rx[side + 7] ^= np.uint32(1 << 16)
        self.sendchannel.transferred = buffer.nbytes
        self.recvchannel.transferred = buffer.nbytes - (4 if self.bad_length else 0)
        count = (self.gpio.status & 0x3fff) + 1
        self.gpio.status = count | (count << 14) | (1 << 28 if self.counter_error else 0)


class BackgroundRunnerTests(unittest.TestCase):
    def context(self, **faults):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        for side in (256, 512):
            np.save(directory / f"stare_im0001_{side}.npy", runner.make_pattern(side, "gradient", 0))
        gpio, buffers = FakeGPIO(), []
        def allocate(shape, dtype):
            buffer = Buffer(shape, dtype)
            buffer.physical_address = 0x10000000 + (len(buffers) % 2) * 0x00200000
            buffers.append(buffer)
            return buffer
        context = {"directory": directory, "gpio": gpio, "dma": BackgroundFakeDMA(gpio, **faults),
                   "allocate": allocate, "retained": [], "report": {"status": "A3_LOADED_NO_TRANSFER", "transfers": []}}
        context["save"] = lambda: (directory / "a3_background_result.json").write_text(json.dumps(context["report"]), encoding="utf-8")
        return context, buffers

    def test_all_modes_match_m0_and_mode1_matches_board_verified_a2_mode3(self):
        for side in (256, 512):
            for index, pattern in enumerate(("gradient", "random", "checker", "impulse", "black", "white", "vessel_stripes", "rounding")):
                source = runner.make_pattern(side, pattern, index)
                np.testing.assert_array_equal(source, diagnostic_pattern(side, pattern, index))
                for mode in range(4):
                    np.testing.assert_array_equal(runner.background_expected(source, mode), expected_words(source, mode))
                np.testing.assert_array_equal(runner.background_expected(source, 1), gaussian_expected(source, 3))

    def test_response_saturates_both_signs_and_retains_background_for_diagnostics(self):
        source = runner.make_pattern(256, "vessel_stripes", 0)
        output = runner.background_expected(source, 3)
        response = output >> 24
        self.assertTrue(np.any(response == 0))
        self.assertTrue(np.any(response == 255))
        self.assertTrue(np.any(((source >> 24) == 0) & (response > 0)))
        output2 = runner.background_expected(source, 2)
        np.testing.assert_array_equal(output & 0x00ffffff, output2 & 0x00ffffff)
        np.testing.assert_array_equal(output2 >> 24, source >> 24)

    def test_full_45_frame_suite_frees_only_completed_buffers(self):
        context, buffers = self.context()
        with self.assertRaises(RuntimeError):
            runner.full_a3(context)
        with contextlib.redirect_stdout(io.StringIO()):
            runner.smoke_a3(context)
            runner.full_a3(context)
        self.assertEqual(context["report"]["status"], "A3_PASS_45_BACKGROUND_FRAMES_NOT_FULL_SEGMENTATION")
        self.assertEqual(len(context["report"]["transfers"]), 45)
        self.assertEqual(sum(item["words"] for item in context["report"]["transfers"]), 7_274_496)
        self.assertEqual(context["retained"], [])
        self.assertTrue(all(buffer.freed for buffer in buffers))
        self.assertEqual({item["saved_output"]["name"] for item in context["report"]["transfers"] if "saved_output" in item},
                         {f"a3_output_stare_{side}_mode{mode}.npy" for side in (256, 512) for mode in (2, 3)})

    def test_faults_retain_buffers_and_block_full_suite(self):
        for fault in ("corrupt", "bad_length", "counter_error"):
            with self.subTest(fault=fault):
                context, buffers = self.context(**{fault: True})
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(AssertionError):
                    runner.smoke_a3(context)
                self.assertEqual(context["report"]["status"], "FAILED_OR_INTERRUPTED")
                self.assertEqual(len(context["retained"]), 2)
                self.assertTrue(all(not buffer.freed for buffer in buffers))
                with self.assertRaises(RuntimeError):
                    runner.full_a3(context)

    def test_invalid_size_mode_rejected_before_memory_or_hardware_access(self):
        context, buffers = self.context()
        for side, mode in ((128, 3), (256, 4)):
            with self.assertRaises(ValueError):
                runner.transfer_a3(context, side, mode, "gradient")
        self.assertEqual(buffers, [])
        self.assertEqual(context["gpio"].control, 0)

    def test_preview_uses_actual_saved_bytes_and_protects_earlier_bundle(self):
        display_module = types.ModuleType("IPython.display")
        displayed = []
        display_module.display = displayed.append
        display_patch = patch.dict(sys.modules, {"IPython.display": display_module})
        display_patch.start()
        self.addCleanup(display_patch.stop)
        context, _ = self.context()
        with self.assertRaises(RuntimeError):
            runner.show_a3_results(context)
        with contextlib.redirect_stdout(io.StringIO()):
            runner.smoke_a3(context)
            runner.full_a3(context)
            runner.show_a3_results(context)
        self.assertEqual(displayed[0].size, (1024, 280))
        bundle = context["directory"] / "a3_results_bundle.zip"
        before = bundle.read_bytes()
        with self.assertRaises(RuntimeError):
            runner.show_a3_results(context)
        self.assertEqual(bundle.read_bytes(), before)

    def test_fixed_artifacts_and_code_contract_allow_save_metadata_only(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        notebook = {"nbformat": 4, "cells": [{"cell_type": "code", "source": ["print('unchanged')\n"], "execution_count": None, "outputs": []}]}
        for name in runner.FIXED:
            (directory / name).write_bytes(b"test-only artifact")
        (directory / runner.NOTEBOOK).write_text(json.dumps(notebook), encoding="utf-8")
        manifest = {"revision": runner.REVISION,
                    "artifacts": {name: {"sha256": hashlib.sha256((directory / name).read_bytes()).hexdigest()}
                                  for name in runner.FIXED | {runner.NOTEBOOK}},
                    "notebook_validation": {"algorithm": "sha256-code-cells-v1", "sha256": notebook_code_hash(notebook)}}
        runner.validate_a3_package(directory, manifest)
        saved = copy.deepcopy(notebook)
        saved["cells"][0].update(execution_count=1, outputs=[{"output_type": "stream", "text": "test only"}])
        (directory / runner.NOTEBOOK).write_text(json.dumps(saved), encoding="utf-8")
        runner.validate_a3_package(directory, manifest)
        saved["cells"][0]["source"] += ["raise RuntimeError('changed')\n"]
        (directory / runner.NOTEBOOK).write_text(json.dumps(saved), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Notebook code mismatch"):
            runner.validate_a3_package(directory, manifest)
        (directory / runner.NOTEBOOK).write_text(json.dumps(notebook), encoding="utf-8")
        (directory / "a2_gaussian_board_test.py").write_bytes(b"changed helper")
        with self.assertRaisesRegex(ValueError, "Package mismatch"):
            runner.validate_a3_package(directory, manifest)


if __name__ == "__main__":
    unittest.main()
