"""Host pixel/ownership checks only; synthetic timings are never board evidence."""
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
from zipfile import ZipFile

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import b_layout_board_test as layout
import package_b_layout as package
import test_b_integration as fixtures
import test_b_profile as profile_fixtures
import test_b_video_imports as import_fixtures


class CanvasTests(unittest.TestCase):
    def words(self, mask):
        rng = np.random.default_rng(784)
        words = rng.integers(0, 2**32, size=(512, 512), dtype=np.uint32)
        return (words & np.uint32(0xff00ffff)) | (np.asarray(mask, dtype=np.uint32) << 16)

    def test_all_pixels_equal_for_varied_masks_channels_and_wrapped_markers(self):
        y, x = np.indices((512, 512))
        canvas = layout.CachedCanvas()
        for mask in (np.zeros((512, 512)), np.full((512, 512), 255),
                     ((x + y) % 2) * 255, ((x % 13 == 0) & (y % 17 == 0)) * 255):
            words = self.words(mask)
            for marker in (0, 29, 99, 100, -1, 2**31 + 7):
                with self.subTest(marker=marker, white=int(np.count_nonzero(mask))):
                    np.testing.assert_array_equal(canvas.render(words, marker), layout.b.medical_canvas(words, marker))

    def test_downloaded_actual_fpga_array_equal_on_host_without_reexecution(self):
        path = ROOT / 'build/board_results/b_profile_2026-10-12/b_profile_output_512.npy'
        self.assertEqual(layout.b.sha256_file(path), '14ddd40a2b05061c212f56c00b90df87d5cd4ea3f196cd3659935251a636088b')
        words = np.load(path, allow_pickle=False)
        canvas = layout.CachedCanvas()
        for marker in (0, 1, 29, 99, 100, -1):
            np.testing.assert_array_equal(canvas.render(words, marker), layout.b.medical_canvas(words, marker))

    def test_reuse_has_no_stale_green_or_progress_pixels(self):
        canvas = layout.CachedCanvas()
        for mask, marker in ((255, 0), (0, 99), (255, 1), (0, -1), (0, 100)):
            words = self.words(np.full((512, 512), mask))
            np.testing.assert_array_equal(canvas.render(words, marker), layout.b.medical_canvas(words, marker))

    def test_borrowed_numpy_storage_reused_and_input_unmodified(self):
        canvas = layout.CachedCanvas()
        words = self.words(np.full((512, 512), 255))
        original = words.copy()
        identities = {name: id(value) for name, value in vars(canvas).items() if isinstance(value, np.ndarray)}
        for marker in (0, 1, 29):
            self.assertIs(canvas.render(words, marker), canvas.image)
        np.testing.assert_array_equal(words, original)
        self.assertEqual(identities, {name: id(value) for name, value in vars(canvas).items() if isinstance(value, np.ndarray)})
        self.assertTrue(np.shares_memory(canvas.left, canvas.image) and np.shares_memory(canvas.right, canvas.image))
        self.assertFalse(canvas.template.flags.writeable)
        self.assertTrue(all(type(value) is np.ndarray and not hasattr(value, 'physical_address')
                            for value in vars(canvas).values() if isinstance(value, np.ndarray)))
        self.assertEqual(sum(value.nbytes for value in vars(canvas).values()
                             if isinstance(value, np.ndarray) and value.flags.owndata), 7626752)

    def test_repeated_render_does_not_redraw_pil_titles(self):
        with patch.object(layout.b, 'medical_canvas', wraps=layout.b.medical_canvas) as original:
            canvas = layout.CachedCanvas()
            original.assert_called_once()
        with patch.object(layout.b, 'medical_canvas', side_effect=AssertionError('No original renderer per frame')), \
             patch.object(Image, 'fromarray', side_effect=AssertionError('No PIL per frame')):
            canvas.render(self.words(np.zeros((512, 512))), 10)
            canvas.render(self.words(np.full((512, 512), 255)), 29)

    def test_invalid_shape_type_and_mask_cannot_be_submitted(self):
        canvas = layout.CachedCanvas()
        invalid = (np.zeros((256, 256), dtype=np.uint32), np.zeros((512, 512), dtype=np.int32),
                   np.zeros((512, 512), dtype=np.uint8), np.full((512, 512), 128 << 16, dtype=np.uint32))
        for words in invalid:
            with self.subTest(dtype=str(words.dtype), shape=words.shape), self.assertRaises(RuntimeError):
                canvas.render(words)

    def test_noncontiguous_packed_input_supported(self):
        canvas = layout.CachedCanvas()
        source = self.words(np.full((512, 512), 255))
        for view in (source.T, source[::-1, ::-1]):
            self.assertFalse(view.flags.c_contiguous)
            np.testing.assert_array_equal(canvas.render(view), layout.b.medical_canvas(view))


class LayoutRunnerTests(unittest.TestCase):
    def context(self, pixel_gate=True):
        fixture = fixtures.BRunnerTests()
        self.addCleanup(fixture.doCleanups)
        context, buffers = fixture.context()
        context['hdmi_out'] = profile_fixtures.NativeVideoFacade()
        context['video'].axi_vdma.writechannel.cacheable_frames = True
        context['cached_canvas'] = layout.CachedCanvas()
        context['report']['layout'] = {'contract': copy.deepcopy(layout.CONTRACT), 'groups': []}

        def save():
            (context['directory'] / 'b_layout_result.json').write_text(json.dumps(context['report']), encoding='utf-8')

        context['save'] = save
        with contextlib.redirect_stdout(io.StringIO()):
            layout.start_layout(context)
            if pixel_gate:
                layout.check_actual_pixels(context)
        return context, buffers

    def run_compare(self, context):
        with contextlib.redirect_stdout(io.StringIO()):
            layout.compare_layout(context)

    def test_complete_paired_flow_reuses_algorithm_pair_preserves_native_ownership_and_reconciles(self):
        context, buffers = self.context()
        saves, original_save = [], context['save']

        def save():
            saves.append([len(group['samples']) for group in context['report']['layout']['groups']])
            original_save()

        context['save'] = save
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            layout.compare_layout(context)
        report = context['report']
        groups = report['layout']['groups']
        self.assertEqual(saves, [[], [0], [33], [33, 0], [33, 33], [33, 33]])
        self.assertEqual(output.getvalue().count('B_LAYOUT_PROGRESS:'), 12)
        self.assertEqual(report['status'], 'B_LAYOUT_MEASURED')
        self.assertEqual(report['overlay_downloads'], 1)
        self.assertEqual(report['layout']['total_algorithm_frames'], 68)
        self.assertEqual(context['gpio'].status, 68 | 68 << 14)
        self.assertEqual(len(report['transfers']), 2)
        self.assertEqual(len(buffers), 6)  # Two prefix pairs; same final pair reused in both groups.
        self.assertTrue(all(buffer.freed for buffer in buffers))
        self.assertEqual(context['retained'], [])
        self.assertEqual(context['display_retained'], [])
        self.assertEqual(context['hdmi_out'].count, 68)  # Color + actual pixel gate + 66 compare frames.
        self.assertTrue(all(not frame.freed and frame.flush_count == 1 for frame in context['hdmi_out'].frames))
        self.assertTrue(report['layout']['native_video_cacheable_frames'])
        self.assertEqual([group['name'] for group in groups], list(layout.GROUPS))
        for group_index, group in enumerate(groups):
            self.assertEqual(len(group['samples']), 33)
            self.assertEqual(sum(row['warmup'] for row in group['samples']), 3)
            for index, row in enumerate(group['samples']):
                self.assertEqual(row['frame_count'], 3 + group_index * 33 + index)
                self.assertEqual(sum(row['durations_ns'].values()), row['sample_ns'])
                self.assertEqual(row['output_sha256'], report['layout']['expected_sha256'])
                self.assertTrue(row['display_buffer']['cacheable'])
                self.assertFalse(row['display_buffer']['coherent'])
            summary = group['summary']
            self.assertEqual(sum(stage['sum_ns'] for stage in summary['stages'].values()), summary['sample_sum_ns'])
            self.assertEqual(summary['loop_ns'], summary['sample_sum_ns'] + summary['loop_unattributed_ns'])
            self.assertEqual(summary['loop_fps'], 30 * 1e9 / summary['loop_ns'])
            self.assertIn(group['name'] + ' PS layout', summary['loop_includes'])
        comparison = report['layout']['comparison']
        self.assertEqual(comparison['loop_ratio_cached_over_original'], groups[1]['summary']['loop_fps'] / groups[0]['summary']['loop_fps'])
        self.assertEqual(comparison['layout_ratio_original_over_cached'], groups[0]['summary']['stages']['ps_layout']['mean_ms'] /
                         groups[1]['summary']['stages']['ps_layout']['mean_ms'])
        words = np.load(context['directory'] / 'a4_output_stare_512_mode3.npy', allow_pickle=False)
        original = layout.b.medical_canvas(words, 29)
        for group in groups:
            rgb = np.asarray(Image.open(context['directory'] / group['final_display']['name']))
            np.testing.assert_array_equal(rgb[:, :, ::-1], original)
        np.testing.assert_array_equal(context['hdmi_out'].last, original)
        with contextlib.redirect_stdout(io.StringIO()):
            layout.finish_layout(context)
        self.assertTrue(context['hdmi_out'].closed)
        self.assertEqual(report['status'], 'B_LAYOUT_RECORDS_READY_VISUAL_PENDING')
        self.assertEqual(report['display']['visual_status'], 'PENDING_USER_OBSERVATION')
        with ZipFile(context['directory'] / 'b_layout_bundle.zip') as archive:
            self.assertEqual(set(archive.namelist()), set(layout.OUTPUTS))
            recorded = json.loads(archive.read('b_layout_result.json'))
            self.assertEqual(recorded['layout']['comparison'], comparison)
        for action in (layout.load_layout, layout.start_layout, layout.check_actual_pixels, layout.compare_layout, layout.finish_layout):
            with self.assertRaises(RuntimeError):
                action(context)

    def test_algorithm_faults_keep_both_buffers_and_block_final_close(self):
        for fault in ('corrupt', 'bad_length', 'counter_error'):
            with self.subTest(fault=fault):
                context, buffers = self.context()
                setattr(context['dma'], fault, True)
                with self.assertRaises(RuntimeError):
                    self.run_compare(context)
                self.assertEqual(context['report']['status'], 'FAILED_OR_INTERRUPTED')
                self.assertEqual(len(context['retained']), 2)
                self.assertFalse(any(buffer.freed for buffer in buffers[-2:]))
                self.assertFalse(context['hdmi_out'].closed)
                with self.assertRaises(RuntimeError):
                    layout.finish_layout(context)

    def test_native_video_failure_keeps_submitted_reference_and_algorithm_pair(self):
        context, buffers = self.context()
        context['hdmi_out'].fail = True
        with self.assertRaises(TimeoutError):
            self.run_compare(context)
        self.assertEqual(context['report']['retained_display_frames'], 1)
        self.assertFalse(context['display_retained'][0].freed)
        self.assertEqual(len(context['retained']), 2)
        self.assertFalse(any(buffer.freed for buffer in buffers[-2:]))
        self.assertFalse(context['hdmi_out'].closed)

    def test_misaligned_native_frame_rejected_before_copy_or_flush(self):
        context, _ = self.context()
        context['hdmi_out'].misalign = True
        with self.assertRaisesRegex(RuntimeError, 'Invalid native video DDR'):
            self.run_compare(context)
        self.assertEqual(context['hdmi_out'].count, 2)
        self.assertEqual(context['display_retained'][0].flush_count, 0)

    def test_invalid_algorithm_ddr_kept_before_any_compare_transfer(self):
        context, _ = self.context()
        allocate = context['allocate']

        def invalid(**kwargs):
            buffer = allocate(**kwargs)
            buffer.physical_address += 1
            return buffer

        context['allocate'] = invalid
        with self.assertRaisesRegex(RuntimeError, 'Invalid algorithm allocation'):
            self.run_compare(context)
        self.assertEqual(context['gpio'].status, 2 | 2 << 14)
        self.assertEqual(len(context['retained']), 2)
        self.assertFalse(any(buffer.freed for buffer in context['retained']))

    def test_changed_overlay_blocks_compare_before_allocating(self):
        context, buffers = self.context()
        context['overlay'].loaded = False
        with self.assertRaises(RuntimeError):
            self.run_compare(context)
        self.assertEqual(len(buffers), 4)
        self.assertEqual(context['report']['layout']['groups'], [])

    def test_clock_fault_cannot_claim_compare_complete(self):
        context, buffers = self.context()
        with patch.object(layout.time, 'perf_counter_ns', return_value=10), self.assertRaises(RuntimeError):
            self.run_compare(context)
        self.assertEqual(context['report']['status'], 'FAILED_OR_INTERRUPTED')
        self.assertNotIn('comparison', context['report']['layout'])
        self.assertFalse(any(buffer.freed for buffer in buffers[-2:]))

    def test_pixel_gate_mismatch_blocks_timing_without_inflight_buffers(self):
        context, buffers = self.context(pixel_gate=False)
        render = context['cached_canvas'].render

        def bad_render(*args):
            image = render(*args)
            image[5, 7] ^= 1
            return image

        with patch.object(context['cached_canvas'], 'render', side_effect=bad_render), \
             contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, 'full canvas pixels differ'):
            layout.check_actual_pixels(context)
        self.assertEqual(context['report']['status'], 'FAILED_OR_INTERRUPTED')
        self.assertEqual(context['retained'], [])
        self.assertTrue(all(buffer.freed for buffer in buffers))
        with self.assertRaises(RuntimeError):
            layout.compare_layout(context)

    def test_paired_measurement_requires_actual_gate_and_empty_groups(self):
        context, _ = self.context(pixel_gate=False)
        with self.assertRaisesRegex(RuntimeError, 'Actual pixel gate'):
            layout.compare_layout(context)
        with contextlib.redirect_stdout(io.StringIO()):
            layout.check_actual_pixels(context)
        context['report']['layout']['groups'].append({'name': 'original', 'samples': []})
        with self.assertRaisesRegex(RuntimeError, 'Run paired comparison once'):
            self.run_compare(context)
        self.assertEqual(context['retained'], [])


class LayoutPackageTests(unittest.TestCase):
    def staged(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        manifest = package.stage_package(ROOT / 'build/deploy/b_integration_2017_4_r2',
            ROOT / 'build/deploy/b_profile_2017_4_r2', directory, {'scope': 'HOST ONLY; no board evidence'})
        return directory, manifest

    def test_eighteen_files_seven_cells_original_thirteen_and_profiler_bytes_exact(self):
        directory, manifest = self.staged()
        self.assertEqual(len(list(directory.iterdir())), 18)
        self.assertEqual(manifest['board_status'], 'NOT_RUN')
        self.assertEqual(manifest['performance_improvement'], 'NOT_MEASURED')
        for name in layout.INHERITED - {'b_profile_board_test.py'}:
            self.assertEqual((directory / name).read_bytes(), (ROOT / 'build/deploy/b_integration_2017_4_r2' / name).read_bytes())
        self.assertEqual((directory / 'b_profile_board_test.py').read_bytes(),
                         (ROOT / 'build/deploy/b_profile_2017_4_r2/b_profile_board_test.py').read_bytes())
        notebook = json.loads((directory / layout.NOTEBOOK).read_text(encoding='utf-8'))
        self.assertEqual(len([cell for cell in notebook['cells'] if cell['cell_type'] == 'code']), 7)
        self.assertTrue(all(cell['execution_count'] is None and cell['outputs'] == []
                            for cell in notebook['cells'] if cell['cell_type'] == 'code'))
        layout.validate_package(directory, manifest)

    def test_both_notebook_autosave_outputs_metadata_and_markdown_allowed(self):
        directory, manifest = self.staged()
        raw = {name: (directory / name).read_bytes() for name in (layout.NOTEBOOK, layout.b.NOTEBOOK)}
        result = package.check_saved_notebooks(directory, manifest)
        self.assertEqual(result['baseline']['notebook_code'], 'PASS_CANONICAL_CODE_SHA256')
        for name, content in raw.items():
            self.assertEqual((directory / name).read_bytes(), content)

    def test_either_notebook_code_mutation_rejected(self):
        directory, manifest = self.staged()
        for name in (layout.NOTEBOOK, layout.b.NOTEBOOK):
            raw = (directory / name).read_bytes()
            notebook = json.loads(raw)
            next(cell for cell in notebook['cells'] if cell['cell_type'] == 'code')['source'] = ['raise RuntimeError("changed")\n']
            (directory / name).write_text(json.dumps(notebook), encoding='utf-8')
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, '[Nn]otebook code mismatch'):
                layout.validate_package(directory, manifest)
            (directory / name).write_bytes(raw)

    def test_fixed_scripts_hardware_manifest_inputs_are_not_mutable(self):
        directory, manifest = self.staged()
        for name in ('b_layout_board_test.py', 'b_profile_board_test.py', 'b_integration.bit',
                     'b_integration.hwh', 'b_manifest.json', 'stare_im0001_512.npy', layout.GUIDE):
            raw = (directory / name).read_bytes()
            (directory / name).write_bytes(raw + b'changed')
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'Layout package mismatch'):
                layout.validate_package(directory, manifest)
            (directory / name).write_bytes(raw)

    def test_release_contract_inventory_and_not_run_claim_enforced(self):
        directory, manifest = self.staged()
        for fault in ('contract', 'board', 'artifacts'):
            changed = copy.deepcopy(manifest)
            if fault == 'contract':
                changed['contract']['algorithm_frames'] = 69
            elif fault == 'board':
                changed['board_status'] = 'PASS'
            else:
                del changed['artifacts']['b_profile_board_test.py']
            with self.subTest(fault=fault), self.assertRaises(RuntimeError):
                layout.validate_package(directory, changed)

    def test_prepare_geometry_gate_uses_pinned_imports_without_download_or_dma_allocations(self):
        directory, _ = self.staged()
        fixture = import_fixtures.BVideoImportTests()
        self.addCleanup(fixture.doCleanups)
        calls, _ = fixture.environment()
        with patch.object(layout.b.platform, 'machine', return_value='armv7l'), contextlib.redirect_stdout(io.StringIO()):
            context = layout.prepare_layout(directory, [])
        self.assertEqual(calls, [False])
        self.assertEqual(context['report']['overlay_downloads'], 0)
        self.assertEqual(context['report']['status'], 'B_PRECHECK_FPGA_UNCHANGED')
        self.assertEqual(len(context['report']['layout']['geometry_checks']), 4)
        self.assertEqual(context['report']['layout']['ordinary_cpu_cache_bytes'], 7626752)
        report = json.loads((directory / 'b_layout_result.json').read_text())
        self.assertEqual(report['layout']['groups'], [])

    def test_geometry_failure_is_saved_before_any_hardware_mutation(self):
        directory, _ = self.staged()
        fixture = import_fixtures.BVideoImportTests()
        self.addCleanup(fixture.doCleanups)
        calls, _ = fixture.environment()
        render = layout.CachedCanvas.render

        def bad_render(self, *args):
            image = render(self, *args)
            image[5, 7] ^= 1
            return image

        with patch.object(layout.b.platform, 'machine', return_value='armv7l'), \
             patch.object(layout.CachedCanvas, 'render', bad_render), contextlib.redirect_stdout(io.StringIO()), \
             self.assertRaisesRegex(RuntimeError, 'geometry pixels differ'):
            layout.prepare_layout(directory, [])
        self.assertEqual(calls, [False])
        report = json.loads((directory / 'b_layout_result.json').read_text())
        self.assertEqual(report['overlay_downloads'], 0)
        self.assertEqual(report['status'], 'FAILED_OR_INTERRUPTED')
        self.assertEqual(report['retained_buffers'], 0)

    def test_stale_module_and_low_resolution_clock_rejected_before_baseline_precheck(self):
        directory, _ = self.staged()
        stale = directory / 'stale.py'
        stale.write_bytes(b'old version')
        with patch.object(layout.p, '__file__', str(stale)), patch.object(layout.b, 'prepare_b') as prepare, \
             self.assertRaisesRegex(RuntimeError, 'Imported module mismatch'):
            layout.prepare_layout(directory, [])
        prepare.assert_not_called()
        clock = types.SimpleNamespace(monotonic=True, resolution=0.015625)
        with patch.object(layout.time, 'get_clock_info', return_value=clock), patch.object(layout.b, 'prepare_b') as prepare, \
             self.assertRaisesRegex(RuntimeError, 'high-resolution'):
            layout.prepare_layout(directory, [])
        prepare.assert_not_called()

    def test_previous_outputs_and_bundle_are_never_overwritten(self):
        for name in layout.OUTPUTS + ('b_layout_bundle.zip', 'b_integration_result.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                path = directory / name
                path.write_bytes(b'preserve')
                with patch.object(layout.b, 'prepare_b') as prepare, self.assertRaisesRegex(RuntimeError, 'preserve result'):
                    layout.prepare_layout(directory, [])
                prepare.assert_not_called()
                self.assertEqual(path.read_bytes(), b'preserve')


if __name__ == '__main__':
    unittest.main()
