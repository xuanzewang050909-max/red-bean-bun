"""Verify real snapshot downloads and reject altered evidence without running cells."""
import copy
import io
import json
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import archive_b_snapshot_results as archive

RAW = ROOT / 'build/board_results/b_snapshot_2026-10-12'
DOWNLOADS = Path('C:/Users/Gabriel/Downloads')
PACKAGE = ROOT / 'build/deploy/b_snapshot_2017_4_r1'
TEMP = Path('C:/Users/Gabriel/AppData/Local/Temp')


class ZipBoundaries(unittest.TestCase):
    def bundle(self, fault):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'test.zip'
        names = sorted(archive.NAMES)
        if fault == 'duplicate':
            names[-1] = names[0]
        elif fault == 'path':
            names[0] = '../outside.json'
        elif fault == 'missing':
            names.pop()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with ZipFile(path, 'w') as output:
                for index, name in enumerate(names):
                    if fault == 'symlink' and index == 0:
                        entry = ZipInfo(name)
                        entry.create_system = 3
                        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                        output.writestr(entry, b'target')
                    else:
                        output.writestr(name, b'x' * (500001 if fault == 'size' and name.endswith('.json') else 1))
        return path

    def test_duplicate_and_unexpected_path_rejected(self):
        for fault in ('duplicate', 'path'):
            with self.subTest(fault=fault), self.assertRaisesRegex(ValueError, 'ZIP member'):
                archive.read_bundle(self.bundle(fault))

    def test_missing_member_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ZIP member'):
            archive.read_bundle(self.bundle('missing'))

    def test_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported ZIP'):
            archive.read_bundle(self.bundle('symlink'))

    def test_oversized_member_rejected(self):
        with self.assertRaisesRegex(ValueError, 'member size'):
            archive.read_bundle(self.bundle('size'))


class ActualEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle_path, cls.notebook_path = RAW / 'b_snapshot_bundle.zip', RAW / 'b_snapshot_compare_executed.ipynb'
        if not cls.bundle_path.exists():
            cls.bundle_path, cls.notebook_path = DOWNLOADS / 'b_snapshot_bundle.zip', DOWNLOADS / 'b_snapshot_compare.ipynb'
        # Real downloaded fixture is required; its absence is an error, never a skip.
        cls.members = archive.read_bundle(cls.bundle_path)
        cls.report = json.loads(cls.members['b_snapshot_result.json'])
        cls.notebook = json.loads(cls.notebook_path.read_bytes())
        cls.manifest = json.loads(archive.RELEASE.read_bytes())
        archive.validate_package(PACKAGE, cls.manifest)

    def setUp(self):
        self.report = copy.deepcopy(type(self).report)
        self.notebook = copy.deepcopy(type(self).notebook)
        self.members = dict(type(self).members)

    def verify(self):
        return archive.verify_records(self.notebook, self.report, self.manifest, PACKAGE, self.members)

    def group(self, index=1):
        return self.report['snapshot_compare']['groups'][index]

    def cells(self):
        return [cell for cell in self.notebook['cells'] if cell['cell_type'] == 'code']

    def png(self, name, row, col):
        image = archive.decode_png(self.members[name])
        image[row, col, 0] ^= 1
        buffer = io.BytesIO()
        Image.fromarray(image).save(buffer, format='PNG')
        self.members[name] = buffer.getvalue()

    def test_actual_four_arrays_pixels_68_records_and_copy_cost(self):
        checks = self.verify()
        self.assertEqual(len(checks['frames']), 68)
        self.assertEqual(checks['raw_arrays']['total_words'], 1048576)
        self.assertEqual(checks['raw_arrays']['mismatched_words'], 0)
        self.assertTrue(checks['raw_arrays']['all_npy_bytes_identical'])
        self.assertTrue(checks['display']['pixel_gate_png_bytes_identical'])
        self.assertTrue(checks['display']['final_png_bytes_identical'])
        self.assertEqual(checks['cpu_copy']['captures'], 34)
        self.assertEqual(checks['notebook']['inert_trailing_cells'], 1)
        self.assertTrue(checks['timing']['cpu_copy_cost_included'])
        self.assertAlmostEqual(checks['timing']['comparison']['loop_fps_increase_percent'], 35.3027952799)
        self.assertAlmostEqual(checks['timing']['comparison']['snapshot_copy_mean_ms'], 5.4816351333333)

    def test_all_four_raw_arrays_reject_word_changes_even_with_updated_hashes(self):
        for index, name in enumerate(archive.RAW_NAMES):
            with self.subTest(name=name):
                self.setUp()
                output = np.load(io.BytesIO(self.members[name]), allow_pickle=False)
                output[200, 200] ^= 1
                buffer = io.BytesIO()
                np.save(buffer, output, allow_pickle=False)
                self.members[name] = buffer.getvalue()
                provenance = {'sha256': archive.digest(self.members[name]), 'word_sha256': archive.word_digest(output)}
                if index < 2:
                    self.report['snapshot_compare']['actual_gate']['raw_files'][name] = provenance
                else:
                    self.group(index - 2)['final_output'] = {'name': name, **provenance}
                with self.assertRaisesRegex(ValueError, 'independent M0'):
                    self.verify()

    def test_raw_shape_dtype_and_endianness_rejected(self):
        original = np.load(io.BytesIO(self.members[archive.RAW_NAMES[0]]), allow_pickle=False)
        for output in (original.reshape(-1), original.astype('float64'), original.astype('>u4')):
            with self.subTest(shape=output.shape, dtype=output.dtype):
                buffer = io.BytesIO()
                np.save(buffer, output, allow_pickle=False)
                self.members[archive.RAW_NAMES[0]] = buffer.getvalue()
                with self.assertRaisesRegex(ValueError, 'raw output format'):
                    self.verify()

    def test_saved_array_provenance_rejected(self):
        self.group()['final_output']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'final raw hash'):
            self.verify()

    def test_prefix_input_and_golden_hash_rejected(self):
        self.report['transfers'][0]['input_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'prefix input/golden'):
            self.verify()

    def test_per_frame_output_hash_rejected(self):
        self.group()['samples'][12]['output_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'pair output hash'):
            self.verify()

    def test_copy_gate_counts_rejected(self):
        self.report['snapshot_compare']['actual_gate']['matched_words'] -= 1
        with self.assertRaisesRegex(ValueError, 'gate word/capture'):
            self.verify()

    def test_total_and_prefix_cpu_captures_rejected(self):
        for key, value in (('total_cpu_captures', 33), ('total_algorithm_frames', 67)):
            with self.subTest(key=key):
                self.setUp()
                self.report['snapshot_compare'][key] = value
                with self.assertRaisesRegex(ValueError, 'workload/capture'):
                    self.verify()
        self.setUp()
        self.report['snapshot_compare']['actual_gate']['captures'] = 0
        with self.assertRaisesRegex(ValueError, 'gate word/capture'):
            self.verify()

    def test_per_frame_copy_flags_rejected_in_both_groups_and_warmup(self):
        for group_index, sample_index in ((0, 0), (0, 10), (1, 0), (1, 10)):
            with self.subTest(group=group_index, index=sample_index):
                self.setUp()
                row = self.group(group_index)['samples'][sample_index]
                row['cpu_copy_performed'] = not row['cpu_copy_performed']
                with self.assertRaisesRegex(ValueError, 'CPU copy ledger'):
                    self.verify()

    def test_cpu_storage_ownership_readonly_and_native_attribute_rejected(self):
        for field, value in (('owndata', False), ('readonly_between_captures', False), ('has_physical_address', True), ('owndata', 1)):
            with self.subTest(field=field, value=value):
                self.setUp()
                self.report['snapshot_compare']['cpu_storage_after'][field] = value
                with self.assertRaisesRegex(ValueError, 'CPU storage'):
                    self.verify()

    def test_order_frame_counter_and_bytes_rejected(self):
        for field in ('frame_count', 'frame_status', 'send_bytes', 'recv_bytes'):
            with self.subTest(field=field):
                self.setUp()
                self.group()['samples'][20][field] -= 1
                with self.assertRaisesRegex(ValueError, 'Pair frame/bytes/counter'):
                    self.verify()
        self.setUp()
        self.report['snapshot_compare']['groups'].reverse()
        with self.assertRaisesRegex(ValueError, 'group order'):
            self.verify()

    def test_raw_timestamps_type_count_and_reversal_rejected(self):
        for fault in ('float', 'count', 'reversed'):
            with self.subTest(fault=fault):
                self.setUp()
                boundary = self.group()['samples'][0]['boundaries_ns']
                if fault == 'float':
                    boundary[1] = float(boundary[1])
                elif fault == 'count':
                    boundary.pop(2)
                else:
                    boundary[2] = boundary[1] - 1
                with self.assertRaisesRegex(ValueError, 'timestamps|clock reversed'):
                    self.verify()

    def test_stage_duration_and_sample_sum_rejected(self):
        self.group()['samples'][7]['durations_ns']['cpu_snapshot'] += 1
        with self.assertRaisesRegex(ValueError, 'Raw stage sum'):
            self.verify()
        self.setUp()
        self.group()['samples'][7]['sample_ns'] -= 1
        with self.assertRaisesRegex(ValueError, 'Raw stage sum'):
            self.verify()

    def test_copy_interval_cannot_be_subtracted_from_checked_loop(self):
        summary = self.group()['summary']
        summary['loop_end_ns'] -= summary['stages']['cpu_snapshot']['sum_ns']
        with self.assertRaisesRegex(ValueError, 'Complete loop timestamps'):
            self.verify()

    def test_summary_mean_p95_and_stage_share_rejected(self):
        for key in ('mean_ms', 'p95_ms', 'loop_fps'):
            with self.subTest(key=key):
                self.setUp()
                self.group()['summary'][key] *= 1.1
                with self.assertRaises(ValueError):
                    self.verify()
        self.setUp()
        self.group()['summary']['stages']['cpu_snapshot']['share_of_sample_time_percent'] += 1
        with self.assertRaises(ValueError):
            self.verify()

    def test_comparison_ratio_and_copy_cost_rejected(self):
        for key in ('loop_ratio_snapshot_over_direct', 'snapshot_copy_mean_ms'):
            with self.subTest(key=key):
                self.setUp()
                self.report['snapshot_compare']['comparison'][key] += 1
                with self.assertRaises(ValueError):
                    self.verify()

    def test_printed_metrics_rejected(self):
        outputs = self.cells()[5]['outputs']
        stream = next(output for output in outputs if output['output_type'] == 'stream')
        stream['text'] = archive.flatten_text(stream['text']).replace('snapshot: checked loop 6.733681 FPS', 'snapshot: checked loop 60.000000 FPS')
        with self.assertRaisesRegex(ValueError, 'precision loop FPS'):
            self.verify()

    def test_executable_notebook_source_change_rejected(self):
        self.cells()[4]['source'].append('print("extra executable code")\n')
        with self.assertRaisesRegex(ValueError, 'Notebook code changed'):
            self.verify()

    def test_notebook_execution_order_and_error_rejected(self):
        self.cells()[2]['execution_count'] = 4
        with self.assertRaisesRegex(ValueError, 'execution order'):
            self.verify()
        self.setUp()
        self.cells()[2]['outputs'].append({'output_type': 'error', 'ename': 'RuntimeError', 'evalue': 'failed', 'traceback': []})
        with self.assertRaisesRegex(ValueError, 'error output'):
            self.verify()

    def test_nonempty_or_executed_tail_rejected(self):
        for field, value in (('source', ['print(1)']), ('execution_count', 8), ('outputs', [{'output_type': 'stream', 'text': 'x'}])):
            with self.subTest(field=field):
                self.setUp()
                self.notebook['cells'][-1][field] = value
                with self.assertRaisesRegex(ValueError, 'executable notebook tail'):
                    self.verify()

    def test_stage_flags_and_progress_rejected(self):
        output = next(output for output in self.cells()[5]['outputs'] if output['output_type'] == 'stream')
        output['text'] = archive.flatten_text(output['text']).replace('B_SNAPSHOT_PROGRESS: direct 15/30', 'B_SNAPSHOT_PROGRESS: direct 14/30')
        with self.assertRaisesRegex(ValueError, 'paired progress'):
            self.verify()
        self.setUp()
        output = next(output for output in self.cells()[4]['outputs'] if output['output_type'] == 'stream')
        output['text'] = archive.flatten_text(output['text']).replace('B_SNAPSHOT_PIXELS_PASS:', 'WRONG_FLAG:')
        with self.assertRaisesRegex(ValueError, 'stage marker'):
            self.verify()

    def test_whole_canvas_pair_including_caption_rejected(self):
        self.png('b_snapshot_cpu.png', 90, 100)
        with self.assertRaisesRegex(ValueError, 'pixel-gate entire canvas'):
            self.verify()

    def test_equal_pair_with_wrong_actual_array_panes_rejected(self):
        self.png('b_snapshot_reference.png', 200, 200)
        self.members['b_snapshot_cpu.png'] = self.members['b_snapshot_reference.png']
        with self.assertRaisesRegex(ValueError, 'array panels'):
            self.verify()

    def test_final_canvas_and_color_pattern_rejected(self):
        self.png('b_snapshot_snapshot_final.png', 200, 800)
        with self.assertRaisesRegex(ValueError, 'Final entire canvas'):
            self.verify()
        self.setUp()
        self.png('b_color_pattern.png', 200, 200)
        with self.assertRaisesRegex(ValueError, 'Color pattern pixels'):
            self.verify()

    def test_actual_marker_and_geometry_hash_rejected(self):
        self.report['snapshot_compare']['actual_gate']['pixel_checks'][2]['sha256_bgr'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'full canvas hash/gate'):
            self.verify()
        self.setUp()
        self.report['layout']['geometry_checks'][2]['sha256_bgr'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Geometry full-canvas'):
            self.verify()

    def test_notebook_embedded_image_rejected(self):
        output = next(output for output in self.cells()[6]['outputs'] if 'image/png' in output.get('data', {}))
        output['data'].pop('image/png')
        with self.assertRaisesRegex(ValueError, 'image missing/not unique'):
            self.verify()

    def test_driver_dma_video_error_and_overlapping_buffers_rejected(self):
        self.report['drivers']['dma'] = 'private.DMA'
        with self.assertRaisesRegex(ValueError, 'Official driver'):
            self.verify()
        for field, value in (('dma_status', {'mm2s': 0x12, 's2mm': 4098}), ('vdma_status', {'mm2s': 0x70, 's2mm': 65537})):
            with self.subTest(field=field):
                self.setUp()
                self.group()['samples'][0][field] = value
                with self.assertRaises(ValueError):
                    self.verify()
        self.setUp()
        self.group()['samples'][0]['display_buffer']['physical_address'] = self.report['snapshot_compare']['algorithm_buffers']['rx']['physical_address']
        with self.assertRaisesRegex(ValueError, 'Video/algorithm DDR overlap'):
            self.verify()

    def test_nested_release_and_precheck_validation_rejected(self):
        self.report['snapshot_package_validation']['notebook_code_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Snapshot package validation'):
            self.verify()
        self.setUp()
        self.report['layout_manifest']['board_status'] = 'PASS'
        with self.assertRaisesRegex(ValueError, 'Release manifest'):
            self.verify()

    def test_overlay_clock_incomplete_and_pending_record_rejected(self):
        for field, value in (('overlay_downloads', 2), ('status', 'B_SNAPSHOT_MEASURED')):
            with self.subTest(field=field):
                self.setUp()
                self.report[field] = value
                with self.assertRaises(ValueError):
                    self.verify()
        self.setUp()
        self.report['snapshot_compare']['clock']['monotonic'] = False
        with self.assertRaisesRegex(ValueError, 'timing clock'):
            self.verify()
        self.setUp()
        self.report['display']['visual_status'] = 'PASS'
        with self.assertRaisesRegex(ValueError, 'pending/closed'):
            self.verify()

    def test_archive_preserves_fourteen_original_files_and_refuses_overwrite(self):
        color, medical = RAW / 'monitor_color_photo.jpg', RAW / 'monitor_medical_photo.jpg'
        if not color.exists():
            color = TEMP / 'codex-clipboard-95bb157d-d683-44d1-9b5a-244bc1a0b510.jpg'
            medical = TEMP / 'codex-clipboard-bdcf6d45-da01-454d-b2ec-2f81f0ab86c5.jpg'
        with tempfile.TemporaryDirectory() as temporary:
            destination, raw = Path(temporary) / 'evidence', Path(temporary) / 'originals'
            command = [sys.executable, '-B', str(ROOT / 'scripts/archive_b_snapshot_results.py'), str(self.notebook_path), str(self.bundle_path),
                       '--package', str(PACKAGE), '--destination', str(destination), '--raw-destination', str(raw),
                       '--color-photo', str(color), '--medical-photo', str(medical)]
            process = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            manifest = json.loads((destination / 'archive_manifest.json').read_bytes())
            self.assertEqual(len(manifest['files']), 14)
            expected = {'b_snapshot_compare_executed.ipynb': self.notebook_path.read_bytes(),
                        'b_snapshot_bundle.zip': self.bundle_path.read_bytes(), **self.members,
                        'monitor_color_photo.jpg': color.read_bytes(), 'monitor_medical_photo.jpg': medical.read_bytes()}
            self.assertEqual(set(manifest['files']), set(expected))
            for name, data in expected.items():
                self.assertEqual((raw / name).read_bytes(), data)
                self.assertEqual(manifest['files'][name]['sha256'], archive.digest(data))
            self.assertEqual((destination / 'b_snapshot_result.json').read_bytes(), self.members['b_snapshot_result.json'])
            self.assertEqual(manifest['board_clock_utc_unverified'], self.report['board_clock_utc_unverified'])
            process = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(process.returncode, 0)
            self.assertIn('Preserve earlier archive', process.stderr)
            for name, data in expected.items():
                self.assertEqual((raw / name).read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
