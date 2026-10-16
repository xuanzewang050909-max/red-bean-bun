"""Actual paired evidence and corruption tests; never execute downloaded cells."""
import copy
import io
import json
import stat
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
import archive_b_layout_results as archive

RAW = ROOT / 'build/board_results/b_layout_2026-10-12'
DOWNLOADS = Path('C:/Users/Gabriel/Downloads')
PACKAGE = ROOT / 'build/deploy/b_layout_2017_4_r1'


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

    def test_duplicate_or_unexpected_path_rejected(self):
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
        bundle = RAW / 'b_layout_bundle.zip'
        notebook = RAW / 'b_layout_compare_executed.ipynb'
        if not bundle.exists():
            bundle, notebook = DOWNLOADS / 'b_layout_bundle.zip', DOWNLOADS / 'b_layout_compare.ipynb'
        # Required real fixture; absence is an error, not a silently skipped test.
        cls.members = archive.read_bundle(bundle)
        cls.report = json.loads(cls.members['b_layout_result.json'])
        cls.notebook = json.loads(notebook.read_bytes())
        cls.manifest = json.loads(archive.RELEASE.read_bytes())
        archive.validate_package(PACKAGE, cls.manifest)

    def verify(self, report=None, notebook=None, members=None):
        return archive.verify_records(self.notebook if notebook is None else notebook,
            self.report if report is None else report, self.manifest, PACKAGE, self.members if members is None else members)

    def cells(self, notebook):
        return [cell for cell in notebook['cells'] if cell['cell_type'] == 'code']

    def png(self, pixels):
        buffer = io.BytesIO()
        Image.fromarray(pixels).save(buffer, format='PNG')
        return buffer.getvalue()

    def test_actual_68_frames_arrays_full_canvas_pairs_and_two_raw_timing_groups_pass(self):
        result = self.verify()
        self.assertEqual(len(result['frames']), 68)
        self.assertEqual(sum(frame['words'] for frame in result['frames']), 17629184)
        self.assertEqual(result['raw_array']['words'], 262144)
        self.assertEqual(result['raw_array']['mismatched_words'], 0)
        comparison = result['timing']['comparison']
        self.assertAlmostEqual(comparison['original_layout_mean_ms'], 528.4004766)
        self.assertAlmostEqual(comparison['cached_layout_mean_ms'], 105.15569016666667)
        self.assertAlmostEqual(comparison['loop_ratio_cached_over_original'], 3.1303428445814294)
        self.assertEqual(result['display']['final_pair_mismatched_pixels'], 0)
        self.assertTrue(result['display']['pixel_gate_png_bytes_identical'])
        self.assertTrue(result['display']['final_png_bytes_identical'])
        self.assertEqual(result['notebook']['ignored_single_trailing_empty_lines'],
                         [{'code_cell': 3, 'extra_trailing_empty_lines': 1}])

    def test_inert_tail_absent_also_passes(self):
        notebook = copy.deepcopy(self.notebook)
        notebook['cells'].pop()
        self.assertEqual(self.verify(notebook=notebook)['notebook']['inert_trailing_cells'], 0)

    def test_exact_released_third_cell_with_no_added_empty_line_passes(self):
        notebook = copy.deepcopy(self.notebook)
        self.cells(notebook)[2]['source'] = ['load_layout(layout_context)\n']
        self.assertEqual(self.verify(notebook=notebook)['notebook']['ignored_single_trailing_empty_lines'], [])

    def test_more_blank_lines_comments_or_executable_changes_rejected(self):
        for source in ('load_layout(layout_context)\n\n\n', 'load_layout(layout_context)\n# added\n',
                       'load_layout(layout_context)\nprint("changed")\n', ' load_layout(layout_context)\n'):
            notebook = copy.deepcopy(self.notebook)
            self.cells(notebook)[2]['source'] = [source]
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'Notebook code changed'):
                self.verify(notebook=notebook)

    def test_core_source_and_executable_or_output_bearing_tail_rejected(self):
        for fault in ('core', 'tail', 'tail_executed', 'tail_output'):
            notebook = copy.deepcopy(self.notebook)
            if fault == 'core':
                self.cells(notebook)[0]['source'] = ['print("changed")\n']
            elif fault == 'tail':
                notebook['cells'][-1]['source'] = ['print("changed")\n']
            elif fault == 'tail_executed':
                notebook['cells'][-1]['execution_count'] = 8
            else:
                notebook['cells'][-1]['outputs'] = [{'output_type': 'stream', 'text': 'changed'}]
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(notebook=notebook)

    def test_wrong_execution_sequence_error_output_or_stage_marker_rejected(self):
        for fault in ('order', 'error', 'marker'):
            notebook = copy.deepcopy(self.notebook)
            cells = self.cells(notebook)
            if fault == 'order':
                cells[1]['execution_count'] = 99
            elif fault == 'error':
                cells[5]['outputs'].append({'output_type': 'error'})
            else:
                cells[1]['outputs'] = []
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(notebook=notebook)

    def test_release_runtime_driver_reload_or_incomplete_status_rejected(self):
        for fault in ('release', 'runtime', 'driver', 'reload', 'status', 'retained'):
            report = copy.deepcopy(self.report)
            if fault == 'release':
                report['layout_manifest']['revision'] = 'changed'
            elif fault == 'runtime':
                report['pynq'] = '2.2.1'
            elif fault == 'driver':
                report['drivers']['vdma'] = 'fake.Driver'
            elif fault == 'reload':
                report['overlay_downloads'] = 2
            elif fault == 'status':
                report['status'] = 'B_LAYOUT_COMPARING'
            else:
                report['retained_buffers'] = 2
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_layout_and_inherited_code_validation_tampering_rejected(self):
        for key in ('fixed_artifacts', 'notebook_code_sha256', 'baseline'):
            report = copy.deepcopy(self.report)
            if key == 'baseline':
                report['layout_package_validation'][key]['notebook_code_sha256'] = '0' * 64
            else:
                report['layout_package_validation'][key] = 'SKIP'
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_cache_contract_group_order_missing_samples_and_warmup_rejected(self):
        for fault in ('bytes', 'count', 'order', 'missing', 'warmup'):
            report = copy.deepcopy(self.report)
            value = report['layout']
            if fault == 'bytes':
                value['ordinary_cpu_cache_bytes'] += 1
            elif fault == 'count':
                value['total_algorithm_frames'] = 69
            elif fault == 'order':
                value['groups'].reverse()
            elif fault == 'missing':
                value['groups'][1]['samples'].pop()
            else:
                value['groups'][1]['samples'][0]['warmup'] = False
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_prefix_input_hash_counter_and_saved_raw_provenance_rejected(self):
        for fault in ('input', 'counter', 'saved'):
            report = copy.deepcopy(self.report)
            record = report['transfers'][1]
            if fault == 'input':
                record['input_sha256'] = '0' * 64
            elif fault == 'counter':
                record['frame_status'] += 1
            else:
                record['saved_output']['sha256'] = '0' * 64
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_pair_frame_byte_count_dma_vdma_or_output_hash_rejected(self):
        for fault in ('frame', 'counter', 'bytes', 'dma', 'vdma', 'hash'):
            report = copy.deepcopy(self.report)
            sample = report['layout']['groups'][1]['samples'][3]
            if fault == 'frame':
                sample['frame_count'] += 1
            elif fault == 'counter':
                sample['frame_status'] |= 1 << 28
            elif fault == 'bytes':
                sample['recv_bytes'] -= 4
            elif fault == 'dma':
                sample['dma_status']['s2mm'] |= 0x20
            elif fault == 'vdma':
                sample['vdma_status']['mm2s'] |= 0x20
            else:
                sample['output_sha256'] = '0' * 64
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_native_frame_cache_stride_address_and_algorithm_overlap_rejected(self):
        for fault in ('cache', 'stride', 'misaligned', 'overlap'):
            report = copy.deepcopy(self.report)
            description = report['layout']['groups'][1]['samples'][3]['display_buffer']
            if fault == 'cache':
                description['cacheable'] = False
            elif fault == 'stride':
                description['strides'] = [1, 3, 1]
            elif fault == 'misaligned':
                description['physical_address'] += 1
            else:
                description['physical_address'] = report['layout']['algorithm_buffers']['tx']['physical_address']
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_raw_timestamp_reverse_overlap_duration_and_zero_dma_rejected(self):
        for fault in ('reverse', 'overlap', 'duration', 'zero_dma'):
            report = copy.deepcopy(self.report)
            samples = report['layout']['groups'][1]['samples']
            sample = samples[3]
            if fault == 'reverse':
                sample['boundaries_ns'][2] = sample['boundaries_ns'][1] - 1
            elif fault == 'overlap':
                sample['boundaries_ns'][0] = samples[2]['boundaries_ns'][-1] - 1
            elif fault == 'duration':
                sample['durations_ns']['ps_layout'] += 1
            else:
                sample['boundaries_ns'][1] = sample['boundaries_ns'][0]
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_stage_statistics_loop_formulas_and_ratio_tampering_rejected(self):
        for fault in ('mean', 'share', 'loop', 'gap', 'start', 'ratio'):
            report = copy.deepcopy(self.report)
            summary = report['layout']['groups'][1]['summary']
            if fault == 'mean':
                summary['stages']['ps_layout']['mean_ms'] -= 1
            elif fault == 'share':
                summary['stages']['ps_layout']['share_of_sample_time_percent'] -= 1
            elif fault == 'loop':
                summary['loop_fps'] += 1
            elif fault == 'gap':
                summary['loop_unattributed_ns'] += 1
            elif fault == 'start':
                summary['loop_start_ns'] -= 1
            else:
                report['layout']['comparison']['loop_ratio_cached_over_original'] += 1
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_consistent_within_group_clock_shift_still_rejects_cross_group_overlap(self):
        report = copy.deepcopy(self.report)
        original, cached = report['layout']['groups']
        delta = cached['samples'][0]['boundaries_ns'][0] - original['summary']['loop_end_ns'] + 1
        for sample in cached['samples']:
            sample['boundaries_ns'] = [value - delta for value in sample['boundaries_ns']]
        for key in ('loop_start_ns', 'loop_end_ns'):
            cached['summary'][key] -= delta
        with self.assertRaisesRegex(ValueError, 'groups overlap'):
            self.verify(report=report)

    def test_monotonic_clock_properties_rejected(self):
        for key, value in (('monotonic', False), ('resolution_seconds', 0), ('name', 'wall_clock')):
            report = copy.deepcopy(self.report)
            report['layout']['clock'][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'monotonic timing clock'):
                self.verify(report=report)

    def test_corrupted_actual_array_with_updated_file_hash_rejected(self):
        report, members = copy.deepcopy(self.report), dict(self.members)
        words = np.load(io.BytesIO(members['a4_output_stare_512_mode3.npy']), allow_pickle=False)
        words[100, 100] ^= np.uint32(1)
        buffer = io.BytesIO()
        np.save(buffer, words, allow_pickle=False)
        members['a4_output_stare_512_mode3.npy'] = buffer.getvalue()
        report['transfers'][1]['saved_output']['sha256'] = archive.digest(buffer.getvalue())
        with self.assertRaisesRegex(ValueError, 'Actual raw FPGA output'):
            self.verify(report=report, members=members)

    def test_pixel_gate_pair_both_tampered_cannot_match_actual_array(self):
        members = dict(self.members)
        pixels = archive.decode_png(members['b_layout_reference.png'])
        pixels[300, 200] ^= np.uint8(1)
        for name in ('b_layout_reference.png', 'b_layout_cached.png'):
            members[name] = self.png(pixels)
        with self.assertRaisesRegex(ValueError, 'Actual array panels'):
            self.verify(members=members)

    def test_final_pair_both_tampered_with_updated_hashes_rejected(self):
        members, report = dict(self.members), copy.deepcopy(self.report)
        pixels = archive.decode_png(members['b_layout_original_final.png'])
        pixels[300, 200] ^= np.uint8(1)
        for group in report['layout']['groups']:
            name = group['final_display']['name']
            members[name] = self.png(pixels)
            group['final_display']['sha256'] = archive.digest(members[name])
            group['final_display']['sha256_bgr'] = archive.digest(pixels[:, :, ::-1].tobytes())
        with self.assertRaisesRegex(ValueError, 'Final entire canvas'):
            self.verify(report=report, members=members)

    def test_actual_gate_geometry_or_color_provenance_rejected(self):
        for fault in ('actual', 'geometry', 'color'):
            report = copy.deepcopy(self.report)
            if fault == 'actual':
                report['layout']['actual_pixel_checks'][1]['sha256_bgr'] = '0' * 64
            elif fault == 'geometry':
                report['layout']['geometry_checks'][1]['sha256_bgr'] = '0' * 64
            else:
                report['display']['submissions'][0]['sha256_bgr'] = '0' * 64
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_notebook_metrics_or_missing_image_rejected(self):
        for fault in ('metric', 'image'):
            notebook = copy.deepcopy(self.notebook)
            cells = self.cells(notebook)
            if fault == 'metric':
                for output in cells[5]['outputs']:
                    if output.get('output_type') == 'stream':
                        output['text'] = archive.flatten_text(output['text']).replace(
                            'cached: checked loop 5.015968 FPS', 'cached: checked loop 50.015968 FPS')
            else:
                cells[6]['outputs'] = [output for output in cells[6]['outputs'] if output.get('output_type') != 'display_data']
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(notebook=notebook)

    def test_raw_visual_pending_not_promoted(self):
        report = copy.deepcopy(self.report)
        report['display']['visual_status'] = 'PASS'
        with self.assertRaisesRegex(ValueError, 'pending/closed'):
            self.verify(report=report)


if __name__ == '__main__':
    unittest.main()
