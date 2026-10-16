"""Host attribution/ownership faults. Synthetic DMA/video is never board evidence."""
import contextlib
import copy
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import b_profile_board_test as profiler
import package_b_profile as package
import test_b_integration as fixtures
import test_b_video_imports as import_fixtures


class NativeVideoFacade(fixtures.FakeHDMI):
    """Only the ownership/flush boundary is simulated, not native hardware."""
    def __init__(self):
        super().__init__()
        self.frames = []
        self.misalign = False

    def newframe(self):
        frame = super().newframe()
        frame.cacheable, frame.coherent = True, False
        frame.flush_count = 0

        def flush():
            frame.flush_count += 1

        frame.flush = flush
        if self.misalign:
            frame.physical_address += 1
        self.frames.append(frame)
        return frame

    def writeframe(self, frame):
        if self.fail:
            raise TimeoutError('Synthetic native video failure')
        frame.flush()  # Facade for the pinned official writeframe's single flush.
        super().writeframe(frame)


def synthetic_samples():
    rows, cursor = [], 1000
    for index in range(profiler.COUNT + profiler.WARMUP):
        step = 900 if index < profiler.WARMUP else 100
        boundaries = [cursor + offset * step for offset in range(len(profiler.STAGES) + 1)]
        rows.append({'index': index, 'warmup': index < profiler.WARMUP,
                     'boundaries_ns': boundaries, 'durations_ns': profiler.stage_durations(boundaries),
                     'sample_ns': boundaries[-1] - boundaries[0]})
        cursor = boundaries[-1] + 7
    return rows, rows[profiler.WARMUP]['boundaries_ns'][0], cursor + 25


class TimestampTests(unittest.TestCase):
    def test_raw_boundaries_exactly_reconcile_and_warmup_is_excluded(self):
        rows, start, end = synthetic_samples()
        result = profiler.summarize(rows, start, end)
        self.assertEqual(result['count'], 30)
        self.assertEqual(result['sample_sum_ns'], 30000)
        self.assertEqual(sum(s['sum_ns'] for s in result['stages'].values()), 30000)
        self.assertAlmostEqual(sum(s['share_of_sample_time_percent'] for s in result['stages'].values()), 100)
        self.assertEqual(result['loop_unattributed_ns'], end - start - 30000)
        self.assertEqual(result['loop_fps'], 30 * 1e9 / (end - start))

    def test_substage_zero_is_valid_but_dma_zero_or_clock_reverse_is_rejected(self):
        boundaries = [10, 20] + [20] * (len(profiler.STAGES) - 1)
        self.assertEqual(sum(profiler.stage_durations(boundaries).values()), 10)
        for invalid in ([20] * 11, [10, 20, 19] + [30] * 8, [10, 20], [0.1] * 11, [-1] + [20] * 10):
            with self.subTest(invalid=invalid), self.assertRaises(RuntimeError):
                profiler.stage_durations(invalid)

    def test_missing_reordered_mutated_or_overlapping_samples_rejected(self):
        for fault in ('missing', 'index', 'warmup', 'duration', 'total', 'overlap', 'loopstart', 'loopend'):
            with self.subTest(fault=fault):
                rows, start, end = synthetic_samples()
                if fault == 'missing':
                    rows.pop()
                elif fault == 'index':
                    rows[3]['index'] = 4
                elif fault == 'warmup':
                    rows[3]['warmup'] = True
                elif fault == 'duration':
                    rows[3]['durations_ns']['word_compare'] += 1
                elif fault == 'total':
                    rows[3]['sample_ns'] += 1
                elif fault == 'overlap':
                    rows[3]['boundaries_ns'] = rows[2]['boundaries_ns'].copy()
                    rows[3]['durations_ns'] = profiler.stage_durations(rows[3]['boundaries_ns'])
                    rows[3]['sample_ns'] = sum(rows[3]['durations_ns'].values())
                elif fault == 'loopstart':
                    start -= 1
                else:
                    end = rows[-1]['boundaries_ns'][-1] - 1
                with self.assertRaises(RuntimeError):
                    profiler.summarize(rows, start, end)


class ProfileRunnerTests(unittest.TestCase):
    def context(self):
        fixture = fixtures.BRunnerTests()
        self.addCleanup(fixture.doCleanups)
        context, buffers = fixture.context()
        context['hdmi_out'] = NativeVideoFacade()
        context['video'].axi_vdma.writechannel.cacheable_frames = True
        with contextlib.redirect_stdout(io.StringIO()):
            profiler.b.smoke_b(context)
            profiler.b.start_hdmi_b(context)
        context['report']['profile'] = {'contract': copy.deepcopy(profiler.CONTRACT), 'samples': []}

        def save():
            (context['directory'] / 'b_profile_result.json').write_text(json.dumps(context['report']), encoding='utf-8')

        context['save'] = save
        return context, buffers

    def run_profile(self, context):
        with contextlib.redirect_stdout(io.StringIO()):
            profiler.profile_frames(context)

    def test_complete_profile_uses_original_canvas_and_ownership_then_packages_real_format(self):
        context, buffers = self.context()
        self.run_profile(context)
        profile = context['report']['profile']
        self.assertEqual(context['report']['status'], 'B_PROFILE_TIMING_COMPLETE')
        self.assertEqual(profile['total_algorithm_frames'], 34)
        self.assertEqual(len(profile['samples']), 33)
        self.assertEqual(context['hdmi_out'].count, 34)  # Color + 33 diagnostic submissions.
        self.assertEqual(len(buffers), 4)  # Short test and one reused diagnostic pair.
        self.assertTrue(all(buffer.freed for buffer in buffers))
        self.assertEqual(context['retained'], [])
        self.assertEqual(context['display_retained'], [])
        self.assertTrue(all(not frame.freed and frame.flush_count == 1 for frame in context['hdmi_out'].frames))
        self.assertTrue(profile['native_video_cacheable_frames'])
        for row in profile['samples']:
            self.assertTrue(row['display_buffer']['cacheable'])
            self.assertFalse(row['display_buffer']['coherent'])
            self.assertEqual(sum(row['durations_ns'].values()), row['sample_ns'])
            self.assertEqual(row['output_sha256'], profile['expected_sha256'])
        output = np.load(context['directory'] / 'b_profile_output_512.npy', allow_pickle=False)
        source = profiler.b.make_pattern(512, 'stare', 0, context['directory'])
        np.testing.assert_array_equal(output, profiler.b.segmentation_expected(source, 3))
        expected_canvas = profiler.b.medical_canvas(output, 29)
        actual_rgb = np.asarray(Image.open(context['directory'] / 'b_profile_display.png'))
        np.testing.assert_array_equal(actual_rgb[:, :, ::-1], expected_canvas)
        np.testing.assert_array_equal(context['hdmi_out'].last, expected_canvas)
        with contextlib.redirect_stdout(io.StringIO()):
            profiler.finish_profile(context)
        self.assertTrue(context['hdmi_out'].closed)
        self.assertEqual(context['report']['status'], 'B_PROFILE_RECORDS_READY_VISUAL_PENDING')
        self.assertEqual(context['report']['display']['visual_status'], 'PENDING_USER_OBSERVATION')
        with ZipFile(context['directory'] / 'b_profile_bundle.zip') as archive:
            self.assertEqual(set(archive.namelist()), set(profiler.OUTPUTS))
            original = json.loads(archive.read('b_profile_result.json'))
            self.assertEqual(original['overlay_downloads'], 1)
            self.assertEqual(original['profile']['summary'], profile['summary'])
        for action in (profiler.profile_frames, profiler.finish_profile, profiler.start_profile, profiler.load_profile):
            with self.assertRaises(RuntimeError):
                action(context)

    def test_algorithm_failures_preserve_pair_and_block_close(self):
        for fault in ('corrupt', 'bad_length', 'counter_error'):
            with self.subTest(fault=fault):
                context, buffers = self.context()
                setattr(context['dma'], fault, True)
                with self.assertRaises(RuntimeError):
                    self.run_profile(context)
                self.assertEqual(context['report']['status'], 'FAILED_OR_INTERRUPTED')
                self.assertEqual(len(context['retained']), 2)
                self.assertFalse(any(buffer.freed for buffer in buffers[-2:]))
                self.assertEqual(context['hdmi_out'].count, 1)
                self.assertFalse((context['directory'] / 'b_profile_output_512.npy').exists())
                with self.assertRaises(RuntimeError):
                    profiler.finish_profile(context)

    def test_video_submission_failure_preserves_display_and_algorithm_buffers(self):
        context, buffers = self.context()
        context['hdmi_out'].fail = True
        with self.assertRaises(TimeoutError):
            self.run_profile(context)
        self.assertEqual(context['report']['retained_display_frames'], 1)
        self.assertEqual(len(context['retained']), 2)
        self.assertFalse(context['display_retained'][0].freed)
        self.assertFalse(any(buffer.freed for buffer in buffers[-2:]))
        self.assertFalse(context['hdmi_out'].closed)

    def test_bad_native_frame_rejected_before_copy_submission(self):
        context, _ = self.context()
        context['hdmi_out'].misalign = True
        with self.assertRaisesRegex(RuntimeError, 'Invalid video DDR'):
            self.run_profile(context)
        self.assertEqual(context['hdmi_out'].count, 1)
        self.assertEqual(len(context['display_retained']), 1)
        self.assertEqual(context['display_retained'][0].flush_count, 0)

    def test_bad_algorithm_allocation_rejected_before_transfer_and_kept(self):
        context, _ = self.context()
        allocate = context['allocate']

        def bad_allocate(**kwargs):
            buffer = allocate(**kwargs)
            buffer.physical_address += 1
            return buffer

        context['allocate'] = bad_allocate
        with self.assertRaisesRegex(RuntimeError, 'Invalid official algorithm allocation'):
            self.run_profile(context)
        self.assertEqual(context['gpio'].status, 1 | 1 << 14)
        self.assertEqual(len(context['retained']), 2)
        self.assertFalse(any(buffer.freed for buffer in context['retained']))

    def test_changed_overlay_blocks_measurement_before_allocation(self):
        context, buffers = self.context()
        context['overlay'].loaded = False
        with self.assertRaises(RuntimeError):
            self.run_profile(context)
        self.assertEqual(len(buffers), 2)
        self.assertEqual(context['report']['profile']['samples'], [])

    def test_clock_fault_prevents_timing_pass_and_keeps_pair(self):
        context, buffers = self.context()
        with patch.object(profiler.time, 'perf_counter_ns', return_value=10), self.assertRaises(RuntimeError):
            self.run_profile(context)
        self.assertEqual(context['report']['status'], 'FAILED_OR_INTERRUPTED')
        self.assertNotIn('summary', context['report']['profile'])
        self.assertFalse(any(buffer.freed for buffer in buffers[-2:]))

    def test_progress_and_json_io_are_separate_from_per_frame_intervals(self):
        context, _ = self.context()
        saves = []
        original_save = context['save']

        def save():
            saves.append(len(context['report']['profile']['samples']))
            original_save()

        context['save'] = save
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            profiler.profile_frames(context)
        self.assertEqual(saves, [0, 0, 33])
        self.assertEqual(output.getvalue().count('B_PROFILE_PROGRESS:'), 6)
        self.assertIn('B_PROFILE_COMPLETE:', output.getvalue())


class ProfilePackageTests(unittest.TestCase):
    def staged(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        manifest = package.stage_package(ROOT / 'build/deploy/b_integration_2017_4_r2', directory,
                                         {'scope': 'SYNTHETIC HOST PACKAGE CHECK ONLY'})
        return directory, manifest

    def test_original_thirteen_files_exact_and_new_package_not_run(self):
        directory, manifest = self.staged()
        self.assertEqual(len(list(directory.iterdir())), 17)
        self.assertEqual(manifest['board_status'], 'NOT_RUN')
        self.assertFalse(manifest['baseline']['hardware_rebuilt'])
        for name in profiler.INHERITED:
            self.assertEqual((directory / name).read_bytes(),
                             (ROOT / 'build/deploy/b_integration_2017_4_r2' / name).read_bytes())
        profiler.validate_profile_package(directory, manifest)

    def test_saved_notebook_outputs_allowed_but_code_mutation_rejected(self):
        directory, manifest = self.staged()
        original = (directory / profiler.NOTEBOOK).read_bytes()
        package.check_saved_notebook(directory, manifest)
        self.assertEqual((directory / profiler.NOTEBOOK).read_bytes(), original)
        notebook = json.loads(original)
        next(cell for cell in notebook['cells'] if cell['cell_type'] == 'code')['source'] = ['raise ValueError("changed")\n']
        (directory / profiler.NOTEBOOK).write_text(json.dumps(notebook), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'notebook code'):
            profiler.validate_profile_package(directory, manifest)

    def autosave_inherited(self, directory):
        path = directory / profiler.b.NOTEBOOK
        notebook = json.loads(path.read_text(encoding='utf-8'))
        notebook['metadata']['host_saved_probe'] = 'HOST ONLY; not board evidence'
        for cell in notebook['cells']:
            if cell['cell_type'] == 'code':
                cell['execution_count'] = 2
                cell['outputs'] = [{'output_type': 'stream', 'name': 'stdout', 'text': 'HOST SAVE PROBE\n'}]
            else:
                cell['source'] = ['Host-only Markdown save change\n']
        path.write_text(json.dumps(notebook), encoding='utf-8')

    def test_inherited_notebook_autosave_accepted_with_original_code_contract(self):
        directory, manifest = self.staged()
        original = (directory / profiler.b.NOTEBOOK).read_bytes()
        self.autosave_inherited(directory)
        result = profiler.validate_profile_package(directory, manifest)
        self.assertNotEqual((directory / profiler.b.NOTEBOOK).read_bytes(), original)
        self.assertEqual(result['baseline']['notebook_code'], 'PASS_CANONICAL_CODE_SHA256')
        self.assertNotEqual(result['baseline']['current_notebook_sha256'], result['baseline']['original_notebook_sha256'])

    def test_inherited_notebook_code_change_rejected_even_with_mutable_json(self):
        directory, manifest = self.staged()
        self.autosave_inherited(directory)
        path = directory / profiler.b.NOTEBOOK
        notebook = json.loads(path.read_text(encoding='utf-8'))
        next(cell for cell in notebook['cells'] if cell['cell_type'] == 'code')['source'] = ['raise RuntimeError("changed code")\n']
        path.write_text(json.dumps(notebook), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'Notebook code mismatch'):
            profiler.validate_profile_package(directory, manifest)

    def test_r1_reproduces_screenshot_error_on_benign_save_before_overlay(self):
        old_dir = ROOT / 'build/deploy/b_profile_2017_4_r1'
        legacy = types.ModuleType('legacy_b_profile_r1')
        path = old_dir / 'b_profile_board_test.py'
        legacy.__file__ = str(path)
        exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), legacy.__dict__)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in profiler.ARTIFACTS | {'b_profile_manifest.json'}:
                (directory / name).write_bytes((old_dir / name).read_bytes())
            self.autosave_inherited(directory)
            with patch.object(legacy.b, 'prepare_b') as prepare, self.assertRaisesRegex(RuntimeError,
                    'Profiling package mismatch: b_integration_check.ipynb'):
                legacy.prepare_profile(directory, [])
            prepare.assert_not_called()

    def test_three_file_patch_recovers_r1_folder_with_saved_inherited_notebook(self):
        _, manifest = self.staged()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination, folder = root / 'fix', root / 'board_folder'
            folder.mkdir()
            baseline = ROOT / 'build/deploy/b_profile_2017_4_r1'
            package.stage_fix(baseline, destination, manifest)
            self.assertEqual({path.name for path in destination.iterdir()},
                             {'b_profile_board_test.py', 'b_profile_manifest.json', profiler.GUIDE})
            for name in profiler.ARTIFACTS | {'b_profile_manifest.json'}:
                (folder / name).write_bytes((baseline / name).read_bytes())
            self.autosave_inherited(folder)
            for path in destination.iterdir():
                (folder / path.name).write_bytes(path.read_bytes())
            validation = profiler.validate_profile_package(folder, manifest)
            self.assertEqual(validation['baseline']['notebook_code'], 'PASS_CANONICAL_CODE_SHA256')
            self.assertEqual((folder / 'b_integration.bit').read_bytes(), (baseline / 'b_integration.bit').read_bytes())

    def test_new_script_original_hardware_manifest_and_input_mutations_rejected(self):
        directory, manifest = self.staged()
        for name in ('b_profile_board_test.py', 'b_integration.bit', 'b_manifest.json', 'stare_im0001_512.npy'):
            with self.subTest(name=name):
                path = directory / name
                raw = path.read_bytes()
                path.write_bytes(raw + b'changed')
                with self.assertRaisesRegex(RuntimeError, 'package mismatch'):
                    profiler.validate_profile_package(directory, manifest)
                path.write_bytes(raw)

    def test_altered_contract_incomplete_package_or_board_claim_rejected(self):
        directory, manifest = self.staged()
        for fault in ('contract', 'board', 'artifacts'):
            changed = copy.deepcopy(manifest)
            if fault == 'contract':
                changed['contract']['timed_frames'] = 31
            elif fault == 'board':
                changed['board_status'] = 'PASS'
            else:
                del changed['artifacts']['b_integration.hwh']
            with self.subTest(fault=fault), self.assertRaises(RuntimeError):
                profiler.validate_profile_package(directory, changed)

    def test_prepare_wrapper_persists_profile_without_loading_or_allocating(self):
        directory, _ = self.staged()
        self.autosave_inherited(directory)
        fixture = import_fixtures.BVideoImportTests()
        self.addCleanup(fixture.doCleanups)
        calls, _ = fixture.environment()  # Execute pinned Common and video initializer.
        with patch.object(profiler.b.platform, 'machine', return_value='armv7l'), contextlib.redirect_stdout(io.StringIO()):
            context = profiler.prepare_profile(directory, [])
        self.assertEqual(calls, [False])  # Overlay metadata only; allocation facade rejects all calls.
        self.assertEqual(context['report']['overlay_downloads'], 0)
        self.assertEqual(json.loads((directory / 'b_profile_result.json').read_text())['profile']['samples'], [])
        self.assertEqual(context['report']['profile']['clock']['name'], 'perf_counter_ns')

    def test_stale_imported_release_rejected_before_overlay_creation(self):
        directory, _ = self.staged()
        stale = directory / 'stale_script.py'
        stale.write_bytes(b'old release')
        with patch.object(profiler.b, '__file__', str(stale)), \
             patch.object(profiler.b, 'prepare_b') as prepare, self.assertRaisesRegex(RuntimeError, 'Imported module mismatch'):
            profiler.prepare_profile(directory, [])
        prepare.assert_not_called()

    def test_previous_outputs_are_never_overwritten_and_precheck_failures_do_not_load(self):
        for name in profiler.OUTPUTS + ('b_profile_bundle.zip', 'b_integration_result.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / name
                path.write_bytes(b'preserve')
                with patch.object(profiler.b, 'prepare_b') as prepare, self.assertRaisesRegex(RuntimeError, 'preserve earlier'):
                    profiler.prepare_profile(directory, [])
                prepare.assert_not_called()
                self.assertEqual(path.read_bytes(), b'preserve')

    def test_low_resolution_clock_rejected_before_underlying_precheck(self):
        directory, _ = self.staged()
        clock = types.SimpleNamespace(monotonic=True, resolution=0.015625)
        with patch.object(profiler.time, 'get_clock_info', return_value=clock), \
             patch.object(profiler.b, 'prepare_b') as prepare, self.assertRaisesRegex(RuntimeError, 'high-resolution'):
            profiler.prepare_profile(directory, [])
        prepare.assert_not_called()


if __name__ == '__main__':
    unittest.main()
