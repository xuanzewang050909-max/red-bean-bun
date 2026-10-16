"""CPU copy/pixel/ownership tests only; synthetic timings are never board results."""
import contextlib
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import b_snapshot_board_test as runner
import package_b_snapshot as package
import test_b_integration as fixtures
import test_b_profile as profile_fixtures
import test_b_video_imports as import_fixtures
from test_a0_board_runner import Buffer


class CpuSnapshotTests(unittest.TestCase):
    def test_copies_all_random_packed_bits_without_mutating_or_aliasing_source(self):
        words = np.random.default_rng(781).integers(0, 2**32, size=262144, dtype=np.uint32)
        original = words.copy()
        cpu = runner.CpuSnapshot()
        result = cpu.capture(words)
        np.testing.assert_array_equal(result, original)
        np.testing.assert_array_equal(words, original)
        self.assertIs(result, cpu.words)
        self.assertFalse(np.shares_memory(result, words))
        self.assertEqual(type(result), np.ndarray)
        self.assertEqual(cpu.description(), {'shape': [262144], 'strides': [4], 'dtype': 'uint32', 'nbytes': 1048576,
                         'owndata': True, 'readonly_between_captures': True, 'has_physical_address': False})

    def test_repeated_capture_reuses_one_cpu_allocation_and_refreshes_all_words(self):
        cpu = runner.CpuSnapshot()
        identity = id(cpu.words)
        for value in (0, 0xffffffff, 0x12345678, 0):
            source = np.full((262144,), value, dtype=np.uint32)
            result = cpu.capture(source)
            self.assertEqual(id(result), identity)
            np.testing.assert_array_equal(result, source)
        self.assertEqual(cpu.captures, 4)

    def test_borrowed_data_readonly_between_captures(self):
        cpu = runner.CpuSnapshot()
        data = cpu.capture(np.arange(262144, dtype=np.uint32))
        with self.assertRaises(ValueError):
            data[0] = 8
        self.assertFalse(cpu.words.flags.writeable)

    def test_bad_type_shape_stride_and_self_alias_rejected(self):
        cpu = runner.CpuSnapshot()
        for source in (np.zeros(262144, dtype=np.int32), np.zeros(256, dtype=np.uint32),
                       np.zeros((512, 512), dtype=np.uint32), np.zeros(524288, dtype=np.uint32)[::2], cpu.words):
            with self.subTest(dtype=str(source.dtype), shape=source.shape), self.assertRaises(RuntimeError):
                cpu.capture(source)
        self.assertEqual(cpu.captures, 0)

    def test_invalid_target_dtype_view_or_writeability_rejected(self):
        source = np.zeros(262144, dtype=np.uint32)
        for fault in ('dtype', 'view', 'writable'):
            cpu = runner.CpuSnapshot()
            if fault == 'dtype':
                cpu.words = np.empty(262144, dtype=np.uint8)
                cpu.words.setflags(write=False)
            elif fault == 'view':
                cpu.words = cpu.words.view()
            else:
                cpu.words.setflags(write=True)
            with self.subTest(fault=fault), self.assertRaisesRegex(RuntimeError, 'CPU snapshot ownership'):
                cpu.capture(source)

    def test_failed_copy_restores_readonly_without_claiming_capture(self):
        cpu = runner.CpuSnapshot()
        with patch.object(runner.np, 'copyto', side_effect=RuntimeError('Synthetic copy fault')), self.assertRaises(RuntimeError):
            cpu.capture(np.zeros(262144, dtype=np.uint32))
        self.assertFalse(cpu.words.flags.writeable)
        self.assertEqual(cpu.captures, 0)

    def test_copy_never_flushes_invalidates_or_frees_native_source(self):
        source = Buffer((262144,), np.uint32)
        source[:] = np.arange(262144, dtype=np.uint32)
        with patch.object(source, 'flush') as flush, patch.object(source, 'invalidate', create=True) as invalidate, \
             patch.object(source, 'freebuffer') as free:
            runner.CpuSnapshot().capture(source)
        flush.assert_not_called()
        invalidate.assert_not_called()
        free.assert_not_called()

    def test_actual_downloaded_output_bytes_and_cached_canvas_equal_on_host(self):
        path = ROOT / 'build/board_results/b_layout_2026-10-12/a4_output_stare_512_mode3.npy'
        self.assertEqual(runner.b.sha256_file(path), '14ddd40a2b05061c212f56c00b90df87d5cd4ea3f196cd3659935251a636088b')
        actual = np.load(path, allow_pickle=False)
        cpu = runner.CpuSnapshot()
        copied = cpu.capture(actual.reshape(-1))
        self.assertEqual(hashlib.sha256(copied.tobytes()).hexdigest(), hashlib.sha256(actual.tobytes()).hexdigest())
        canvas = runner.l.CachedCanvas()
        for marker in (0, 29, 99, 100, -1):
            direct = canvas.render(actual, marker).copy()
            np.testing.assert_array_equal(direct, canvas.render(copied.reshape(512, 512), marker))


def samples():
    result, cursor = [], 1000
    for index in range(33):
        step = 900 if index < 3 else 100
        bounds = [cursor + offset * step for offset in range(len(runner.STAGES) + 1)]
        result.append({'index': index, 'warmup': index < 3, 'boundaries_ns': bounds,
                       'durations_ns': runner.stage_durations(bounds), 'sample_ns': bounds[-1] - bounds[0]})
        cursor = bounds[-1] + 7
    return result, result[3]['boundaries_ns'][0], cursor + 25


class TimestampTests(unittest.TestCase):
    def test_cpu_copy_included_in_sample_stage_and_loop_totals_warmups_excluded(self):
        rows, start, end = samples()
        result = runner.summarize(rows, start, end)
        self.assertEqual(result['sample_sum_ns'], 33000)
        self.assertEqual(result['stages']['cpu_snapshot']['sum_ns'], 3000)
        self.assertEqual(sum(stage['sum_ns'] for stage in result['stages'].values()), 33000)
        self.assertEqual(result['loop_fps'], 30 * 1e9 / (end - start))
        self.assertEqual(result['loop_unattributed_ns'], end - start - 33000)

    def test_zero_source_selection_cost_allowed_but_dma_zero_or_reverse_rejected(self):
        bounds = [10, 20, 20] + list(range(21, 30))
        self.assertEqual(runner.stage_durations(bounds)['cpu_snapshot'], 0)
        for invalid in ([20] * 12, [10, 20, 19] + [30] * 9, [10, 20], [-1] + [20] * 11):
            with self.subTest(bounds=invalid), self.assertRaises(RuntimeError):
                runner.stage_durations(invalid)

    def test_missing_reordered_warmup_mutated_duration_and_overlap_rejected(self):
        for fault in ('missing', 'index', 'warmup', 'duration', 'loopstart', 'overlap'):
            rows, start, end = samples()
            if fault == 'missing':
                rows.pop()
            elif fault == 'index':
                rows[3]['index'] += 1
            elif fault == 'warmup':
                rows[3]['warmup'] = True
            elif fault == 'duration':
                rows[3]['durations_ns']['cpu_snapshot'] += 1
            elif fault == 'loopstart':
                start -= 1
            else:
                rows[3]['boundaries_ns'][0] = rows[2]['boundaries_ns'][-1] - 1
            with self.subTest(fault=fault), self.assertRaises(RuntimeError):
                runner.summarize(rows, start, end)


class SnapshotRunnerTests(unittest.TestCase):
    def context(self, gate=True):
        fixture = fixtures.BRunnerTests()
        self.addCleanup(fixture.doCleanups)
        context, buffers = fixture.context()
        context['hdmi_out'] = profile_fixtures.NativeVideoFacade()
        context['video'].axi_vdma.writechannel.cacheable_frames = True
        context['cached_canvas'] = runner.l.CachedCanvas()
        context['cpu_snapshot'] = runner.CpuSnapshot()
        context['report']['snapshot_compare'] = {'contract': copy.deepcopy(runner.CONTRACT), 'groups': []}

        def save():
            (context['directory'] / 'b_snapshot_result.json').write_text(json.dumps(context['report']), encoding='utf-8')

        context['save'] = save
        with contextlib.redirect_stdout(io.StringIO()):
            runner.start_snapshot(context)
            if gate:
                runner.check_snapshot(context)
        return context, buffers

    def run_compare(self, context):
        with contextlib.redirect_stdout(io.StringIO()):
            runner.compare_snapshot(context)

    def test_complete_68_frame_workflow_copy_counts_all_checks_native_ownership_and_bundle(self):
        context, buffers = self.context()
        copies = []
        capture = context['cpu_snapshot'].capture

        def counted(received):
            copies.append(context['gpio'].status & 0x3fff)
            return capture(received)

        output = io.StringIO()
        with patch.object(context['cpu_snapshot'], 'capture', side_effect=counted), contextlib.redirect_stdout(output):
            runner.compare_snapshot(context)
        report = context['report']['snapshot_compare']
        self.assertEqual(copies, list(range(36, 69)))  # Direct group performs no CPU capture.
        self.assertEqual(report['total_cpu_captures'], 34)
        self.assertEqual(report['total_algorithm_frames'], 68)
        self.assertEqual(context['report']['overlay_downloads'], 1)
        self.assertEqual(len(context['report']['transfers']), 2)
        self.assertEqual(len(buffers), 6)
        self.assertTrue(all(buffer.freed for buffer in buffers))
        self.assertEqual(context['retained'], [])
        self.assertEqual(context['display_retained'], [])
        self.assertEqual(context['hdmi_out'].count, 68)
        self.assertTrue(all(not frame.freed and frame.flush_count == 1 for frame in context['hdmi_out'].frames))
        self.assertEqual(output.getvalue().count('B_SNAPSHOT_PROGRESS:'), 12)
        self.assertTrue(report['cpu_storage_after']['readonly_between_captures'])
        for group_index, group in enumerate(report['groups']):
            self.assertEqual(group['name'], runner.GROUPS[group_index])
            self.assertEqual(len(group['samples']), 33)
            self.assertEqual(sum(row['warmup'] for row in group['samples']), 3)
            for index, row in enumerate(group['samples']):
                self.assertEqual(row['frame_count'], 3 + group_index * 33 + index)
                self.assertEqual(row['cpu_copy_performed'], group_index == 1)
                self.assertEqual(row['output_sha256'], report['expected_sha256'])
                self.assertEqual(len(row['boundaries_ns']), 12)
                self.assertEqual(sum(row['durations_ns'].values()), row['sample_ns'])
            summary = group['summary']
            self.assertEqual(sum(stage['sum_ns'] for stage in summary['stages'].values()), summary['sample_sum_ns'])
            self.assertEqual(summary['loop_ns'], summary['sample_sum_ns'] + summary['loop_unattributed_ns'])
            self.assertEqual(summary['loop_fps'], 30 * 1e9 / summary['loop_ns'])
        files = [np.load(context['directory'] / name, allow_pickle=False) for name in runner.OUTPUTS if name.endswith('.npy')]
        for data in files[1:]:
            np.testing.assert_array_equal(data, files[0])
        expected_canvas = runner.b.medical_canvas(files[0], 29)
        for group in report['groups']:
            rgb = np.asarray(Image.open(context['directory'] / group['final_display']['name']))
            np.testing.assert_array_equal(rgb[:, :, ::-1], expected_canvas)
        with contextlib.redirect_stdout(io.StringIO()):
            runner.finish_snapshot(context)
        self.assertTrue(context['hdmi_out'].closed)
        self.assertEqual(context['report']['status'], 'B_SNAPSHOT_RECORDS_READY_VISUAL_PENDING')
        self.assertEqual(context['report']['display']['visual_status'], 'PENDING_USER_OBSERVATION')
        with ZipFile(context['directory'] / 'b_snapshot_bundle.zip') as archive:
            self.assertEqual(set(archive.namelist()), set(runner.OUTPUTS))
            self.assertEqual(len(archive.namelist()), 10)
        for action in (runner.load_snapshot, runner.start_snapshot, runner.check_snapshot, runner.compare_snapshot, runner.finish_snapshot):
            with self.assertRaises(RuntimeError):
                action(context)

    def test_capture_occurs_after_original_receive_wait(self):
        context, _ = self.context(gate=False)
        events = []
        wait = context['dma'].recvchannel.wait
        capture = context['cpu_snapshot'].capture

        def waited():
            result = wait()
            events.append('receive_wait_finished')
            return result

        def captured(received):
            self.assertEqual(events[-1], 'receive_wait_finished')
            events.append('cpu_copy')
            return capture(received)

        with patch.object(context['dma'].recvchannel, 'wait', side_effect=waited), \
             patch.object(context['cpu_snapshot'], 'capture', side_effect=captured), contextlib.redirect_stdout(io.StringIO()):
            runner.check_snapshot(context)
        self.assertEqual(events, ['receive_wait_finished', 'cpu_copy'])

    def test_gate_failure_keeps_native_pair_and_blocks_timing(self):
        context, buffers = self.context(gate=False)
        context['dma'].corrupt = True
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            runner.check_snapshot(context)
        self.assertEqual(context['report']['status'], 'FAILED_OR_INTERRUPTED')
        self.assertEqual(len(context['retained']), 2)
        self.assertFalse(any(buffer.freed for buffer in buffers[-2:]))
        with self.assertRaises(RuntimeError):
            runner.compare_snapshot(context)

    def test_dma_byte_counter_and_word_faults_keep_pair(self):
        for fault in ('corrupt', 'bad_length', 'counter_error'):
            context, buffers = self.context()
            setattr(context['dma'], fault, True)
            with self.subTest(fault=fault), self.assertRaises(RuntimeError):
                self.run_compare(context)
            self.assertEqual(context['report']['status'], 'FAILED_OR_INTERRUPTED')
            self.assertEqual(len(context['retained']), 2)
            self.assertFalse(any(buffer.freed for buffer in buffers[-2:]))
            with self.assertRaises(RuntimeError):
                runner.finish_snapshot(context)

    def test_bad_cpu_copy_in_candidate_group_fails_full_words_and_retains_pair(self):
        context, buffers = self.context()
        capture = context['cpu_snapshot'].capture

        def corrupted(received):
            result = capture(received)
            result.setflags(write=True)
            result[0] ^= np.uint32(1)
            result.setflags(write=False)
            return result

        with patch.object(context['cpu_snapshot'], 'capture', side_effect=corrupted), self.assertRaisesRegex(RuntimeError, 'FPGA words differ'):
            self.run_compare(context)
        self.assertEqual(len(context['report']['snapshot_compare']['groups'][0]['samples']), 33)
        self.assertEqual(context['report']['snapshot_compare']['groups'][1]['samples'], [])
        self.assertFalse(any(buffer.freed for buffer in buffers[-2:]))

    def test_post_compare_data_mutation_detected_by_per_frame_hash(self):
        context, buffers = self.context()
        render = context['cached_canvas'].render

        def mutating(data, marker):
            image = render(data, marker)
            data[0, 0] ^= np.uint32(1)  # Direct native view; fault injection only.
            return image

        with patch.object(context['cached_canvas'], 'render', side_effect=mutating), self.assertRaisesRegex(RuntimeError, 'output hash differs'):
            self.run_compare(context)
        self.assertFalse(any(buffer.freed for buffer in buffers[-2:]))
        self.assertNotIn('comparison', context['report']['snapshot_compare'])

    def test_native_video_failure_retains_display_reference_and_algorithm_pair(self):
        context, buffers = self.context()
        context['hdmi_out'].fail = True
        with self.assertRaises(TimeoutError):
            self.run_compare(context)
        self.assertEqual(context['report']['retained_display_frames'], 1)
        self.assertFalse(context['display_retained'][0].freed)
        self.assertFalse(any(buffer.freed for buffer in buffers[-2:]))
        self.assertFalse(context['hdmi_out'].closed)

    def test_bad_native_address_or_changed_overlay_blocks_submission(self):
        for fault in ('address', 'overlay'):
            context, buffers = self.context()
            if fault == 'address':
                context['hdmi_out'].misalign = True
            else:
                context['overlay'].loaded = False
            with self.subTest(fault=fault), self.assertRaises(RuntimeError):
                self.run_compare(context)
            self.assertEqual(context['hdmi_out'].count, 2)
            if fault == 'overlay':
                self.assertEqual(len(buffers), 4)
            else:
                self.assertEqual(context['display_retained'][0].flush_count, 0)

    def test_clock_fault_retains_pair_and_does_not_claim_result(self):
        context, buffers = self.context()
        with patch.object(runner.time, 'perf_counter_ns', return_value=10), self.assertRaises(RuntimeError):
            self.run_compare(context)
        self.assertFalse(any(buffer.freed for buffer in buffers[-2:]))
        self.assertNotIn('comparison', context['report']['snapshot_compare'])

    def test_incomplete_caller_ledger_rejected_before_comparison_allocations(self):
        context, buffers = self.context()
        context['cpu_snapshot'].captures += 1
        with self.assertRaisesRegex(RuntimeError, 'comparison once'):
            self.run_compare(context)
        self.assertEqual(len(buffers), 4)


class SnapshotPackageTests(unittest.TestCase):
    def staged(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        manifest = package.stage_package(ROOT / 'build/deploy/b_layout_2017_4_r1', directory, {'scope': 'HOST ONLY'})
        return directory, manifest

    def test_twenty_two_files_seven_code_cells_and_original_eighteen_exact(self):
        directory, manifest = self.staged()
        self.assertEqual(len(list(directory.iterdir())), 22)
        self.assertEqual(manifest['board_status'], 'NOT_RUN')
        self.assertEqual(manifest['performance_improvement'], 'NOT_MEASURED')
        for name in runner.INHERITED:
            self.assertEqual((directory / name).read_bytes(), (ROOT / 'build/deploy/b_layout_2017_4_r1' / name).read_bytes())
        nb = json.loads((directory / runner.NOTEBOOK).read_text(encoding='utf-8'))
        self.assertEqual(len([cell for cell in nb['cells'] if cell['cell_type'] == 'code']), 7)
        runner.validate_package(directory, manifest)

    def test_all_three_notebook_autosaves_allowed_and_original_bytes_restored(self):
        directory, manifest = self.staged()
        raw = {name: (directory / name).read_bytes() for name in (runner.NOTEBOOK, runner.l.NOTEBOOK, runner.b.NOTEBOOK)}
        package.check_saved_notebooks(directory, manifest)
        for name, payload in raw.items():
            self.assertEqual((directory / name).read_bytes(), payload)

    def test_any_of_three_notebook_code_mutations_rejected(self):
        directory, manifest = self.staged()
        for name in (runner.NOTEBOOK, runner.l.NOTEBOOK, runner.b.NOTEBOOK):
            raw = (directory / name).read_bytes()
            notebook = json.loads(raw)
            next(cell for cell in notebook['cells'] if cell['cell_type'] == 'code')['source'] = ['raise RuntimeError("changed")\n']
            (directory / name).write_text(json.dumps(notebook), encoding='utf-8')
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, '[Nn]otebook code mismatch'):
                runner.validate_package(directory, manifest)
            (directory / name).write_bytes(raw)

    def test_fixed_hardware_helpers_manifest_inputs_and_guide_mutation_rejected(self):
        directory, manifest = self.staged()
        for name in ('b_integration.bit', 'b_layout_board_test.py', 'b_layout_manifest.json', 'b_snapshot_board_test.py',
                     'stare_im0001_512.npy', runner.GUIDE):
            raw = (directory / name).read_bytes()
            (directory / name).write_bytes(raw + b'changed')
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'Snapshot package mismatch'):
                runner.validate_package(directory, manifest)
            (directory / name).write_bytes(raw)

    def test_contract_inventory_and_not_run_status_enforced(self):
        directory, manifest = self.staged()
        for fault in ('contract', 'inventory', 'status'):
            changed = copy.deepcopy(manifest)
            if fault == 'contract':
                changed['contract']['stages'].remove('cpu_snapshot')
            elif fault == 'inventory':
                del changed['artifacts']['b_layout_board_test.py']
            else:
                changed['board_status'] = 'PASS'
            with self.subTest(fault=fault), self.assertRaises(RuntimeError):
                runner.validate_package(directory, changed)

    def test_precheck_uses_pinned_imports_and_ordinary_cpu_array_without_native_allocations(self):
        directory, _ = self.staged()
        fixture = import_fixtures.BVideoImportTests()
        self.addCleanup(fixture.doCleanups)
        calls, _ = fixture.environment()
        with patch.object(runner.b.platform, 'machine', return_value='armv7l'), contextlib.redirect_stdout(io.StringIO()):
            context = runner.prepare_snapshot(directory, [])
        self.assertEqual(calls, [False])
        self.assertEqual(context['report']['overlay_downloads'], 0)
        self.assertEqual(context['cpu_snapshot'].captures, 0)
        self.assertTrue(context['report']['snapshot_compare']['cpu_storage']['readonly_between_captures'])
        self.assertEqual(context['report']['status'], 'B_PRECHECK_FPGA_UNCHANGED')
        self.assertTrue((directory / 'b_snapshot_result.json').exists())

    def test_stale_module_rejected_before_inherited_precheck(self):
        directory, _ = self.staged()
        stale = directory / 'stale.py'
        stale.write_bytes(b'old version')
        with patch.object(runner.l, '__file__', str(stale)), patch.object(runner.l, 'prepare_layout') as prepare, \
             self.assertRaisesRegex(RuntimeError, 'Imported module mismatch'):
            runner.prepare_snapshot(directory, [])
        prepare.assert_not_called()

    def test_prior_outputs_or_bundle_never_overwritten(self):
        for name in runner.OUTPUTS + ('b_snapshot_bundle.zip',):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                path = directory / name
                path.write_bytes(b'preserve')
                with patch.object(runner.l, 'prepare_layout') as prepare, self.assertRaisesRegex(RuntimeError, 'preserve result'):
                    runner.prepare_snapshot(directory, [])
                prepare.assert_not_called()
                self.assertEqual(path.read_bytes(), b'preserve')


if __name__ == '__main__':
    unittest.main()
