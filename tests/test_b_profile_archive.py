"""Real profiling evidence and corruption boundaries; never run board code."""
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
import archive_b_profile_results as archive

RAW = ROOT / 'build/board_results/b_profile_2026-10-12'
PACKAGE = ROOT / 'build/deploy/b_profile_2017_4_r2'


class ZipBoundaries(unittest.TestCase):
    def bundle(self, fault):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'test.zip'
        names = sorted(archive.NAMES)
        if fault == 'duplicate':
            names[-1] = names[0]
        if fault == 'path':
            names[0] = '../outside.json'
        if fault == 'missing':
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

    def test_duplicate_or_unexpected_path(self):
        for fault in ('duplicate', 'path'):
            with self.subTest(fault=fault), self.assertRaisesRegex(ValueError, 'ZIP member'):
                archive.read_bundle(self.bundle(fault))

    def test_missing_member(self):
        with self.assertRaisesRegex(ValueError, 'ZIP member'):
            archive.read_bundle(self.bundle('missing'))

    def test_symlink(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported ZIP'):
            archive.read_bundle(self.bundle('symlink'))

    def test_large_member(self):
        with self.assertRaisesRegex(ValueError, 'member size'):
            archive.read_bundle(self.bundle('size'))


@unittest.skipUnless((RAW / 'b_profile_bundle.zip').exists(), 'Real raw profiling downloads remain in ignored local archive')
class ActualEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.members = archive.read_bundle(RAW / 'b_profile_bundle.zip')
        cls.report = json.loads(cls.members['b_profile_result.json'])
        cls.notebook = json.loads((RAW / 'b_performance_profile_executed.ipynb').read_bytes())
        cls.manifest = json.loads(archive.RELEASE.read_bytes())
        archive.validate_profile_package(PACKAGE, cls.manifest)

    def verify(self, report=None, notebook=None, members=None):
        return archive.verify_records(self.notebook if notebook is None else notebook,
            self.report if report is None else report, self.manifest, PACKAGE, self.members if members is None else members)

    def test_complete_actual_data_and_independent_stage_metrics(self):
        result = self.verify()
        self.assertEqual(len(result['frames']), 34)
        self.assertEqual(sum(frame['words'] for frame in result['frames']), 8716288)
        self.assertEqual(result['raw_array']['words'], 262144)
        self.assertEqual(result['raw_array']['mismatched_words'], 0)
        self.assertAlmostEqual(result['timing']['loop_fps'], 1.6221984608383528)
        self.assertAlmostEqual(result['timing']['stages']['ps_layout']['mean_ms'], 523.0630877333333)
        self.assertEqual(result['notebook']['inert_trailing_cells'], 1)

    def test_no_trailing_cell_also_matches_fixed_executed_sources(self):
        notebook = copy.deepcopy(self.notebook)
        notebook['cells'].pop()
        self.assertEqual(self.verify(notebook=notebook)['notebook']['inert_trailing_cells'], 0)

    def test_code_changes_in_core_or_trailing_cell_rejected(self):
        for position in ('core', 'tail'):
            notebook = copy.deepcopy(self.notebook)
            cell = next(c for c in notebook['cells'] if c['cell_type'] == 'code') if position == 'core' else notebook['cells'][-1]
            cell['source'] = ['print("changed")\n']
            with self.subTest(position=position), self.assertRaises(ValueError):
                self.verify(notebook=notebook)

    def test_executed_or_output_bearing_blank_tail_rejected(self):
        for key, value in (('execution_count', 7), ('outputs', [{'output_type': 'stream', 'text': 'changed'}])):
            notebook = copy.deepcopy(self.notebook)
            notebook['cells'][-1][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'executable notebook tail'):
                self.verify(notebook=notebook)

    def test_wrong_execution_order_and_error_rejected(self):
        for fault in ('order', 'error'):
            notebook = copy.deepcopy(self.notebook)
            cell = next(c for c in notebook['cells'] if c['cell_type'] == 'code')
            if fault == 'order':
                cell['execution_count'] = 99
            else:
                cell['outputs'].append({'output_type': 'error'})
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(notebook=notebook)

    def test_wrong_release_runtime_driver_or_reload_rejected(self):
        for fault in ('release', 'runtime', 'driver', 'reload', 'incomplete'):
            report = copy.deepcopy(self.report)
            if fault == 'release':
                report['profile_manifest']['revision'] = 'wrong'
            elif fault == 'runtime':
                report['pynq'] = '2.2.1'
            elif fault == 'driver':
                report['drivers']['vdma'] = 'fake.Driver'
            elif fault == 'reload':
                report['overlay_downloads'] = 2
            else:
                report['status'] = 'B_PROFILE_RUNNING'
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_profile_package_or_inherited_code_validation_tampering_rejected(self):
        for fault in ('policy', 'inherited'):
            report = copy.deepcopy(self.report)
            if fault == 'policy':
                report['profile_package_validation']['fixed_artifacts'] = 'SKIP'
            else:
                report['profile_package_validation']['baseline']['notebook_code_sha256'] = '0' * 64
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_missing_sample_and_wrong_warmup_rejected(self):
        for fault in ('sample', 'warmup'):
            report = copy.deepcopy(self.report)
            if fault == 'sample':
                report['profile']['samples'].pop()
            else:
                report['profile']['samples'][0]['warmup'] = False
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_counter_dma_length_error_or_golden_hash_rejected(self):
        for fault in ('counter', 'length', 'dma', 'hash'):
            report = copy.deepcopy(self.report)
            sample = report['profile']['samples'][3]
            if fault == 'counter':
                sample['frame_status'] += 1
            elif fault == 'length':
                sample['recv_bytes'] -= 4
            elif fault == 'dma':
                sample['dma_status']['s2mm'] |= 0x20
            else:
                sample['output_sha256'] = '0' * 64
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_overlap_and_non_native_frame_properties_rejected(self):
        for fault in ('overlap', 'cache', 'stride'):
            report = copy.deepcopy(self.report)
            description = report['profile']['samples'][3]['display_buffer']
            if fault == 'overlap':
                description['physical_address'] = report['profile']['algorithm_buffers']['tx']['physical_address']
            elif fault == 'cache':
                description['cacheable'] = False
            else:
                description['strides'] = [1, 3, 1]
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_timestamp_reverse_overlap_or_duration_change_rejected(self):
        for fault in ('reverse', 'overlap', 'duration'):
            report = copy.deepcopy(self.report)
            sample = report['profile']['samples'][3]
            if fault == 'reverse':
                sample['boundaries_ns'][2] = sample['boundaries_ns'][1] - 1
            elif fault == 'overlap':
                sample['boundaries_ns'][0] = report['profile']['samples'][2]['boundaries_ns'][-1] - 1
            else:
                sample['durations_ns']['ps_layout'] += 1
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_stage_share_mean_and_loop_metrics_cannot_be_changed(self):
        for fault in ('mean', 'share', 'loop', 'gap', 'start'):
            report = copy.deepcopy(self.report)
            summary = report['profile']['summary']
            if fault == 'mean':
                summary['stages']['ps_layout']['mean_ms'] -= 1
            elif fault == 'share':
                summary['stages']['ps_layout']['share_of_sample_time_percent'] -= 1
            elif fault == 'loop':
                summary['loop_fps'] += 10
            elif fault == 'gap':
                summary['loop_unattributed_ns'] += 1
            else:
                summary['loop_start_ns'] -= 1
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.verify(report=report)

    def test_corrupted_raw_array_even_with_updated_file_hash_rejected(self):
        members, report = dict(self.members), copy.deepcopy(self.report)
        words = np.load(io.BytesIO(members['b_profile_output_512.npy']), allow_pickle=False)
        words[0, 0] ^= np.uint32(1)
        buffer = io.BytesIO()
        np.save(buffer, words, allow_pickle=False)
        members['b_profile_output_512.npy'] = buffer.getvalue()
        report['profile']['final_output']['sha256'] = archive.digest(buffer.getvalue())
        with self.assertRaisesRegex(ValueError, 'Actual raw FPGA output'):
            self.verify(report=report, members=members)

    def test_wrong_preview_pixels_even_with_updated_hash_rejected(self):
        members, report = dict(self.members), copy.deepcopy(self.report)
        pixels = archive.decode_png(members['b_profile_display.png'])
        pixels[300, 200] ^= np.uint8(1)
        buffer = io.BytesIO()
        Image.fromarray(pixels).save(buffer, format='PNG')
        members['b_profile_display.png'] = buffer.getvalue()
        report['profile']['final_display']['sha256'] = archive.digest(buffer.getvalue())
        with self.assertRaisesRegex(ValueError, 'Medical image panels'):
            self.verify(report=report, members=members)

    def test_missing_embedded_image_rejected(self):
        notebook = copy.deepcopy(self.notebook)
        cells = [c for c in notebook['cells'] if c['cell_type'] == 'code']
        cells[5]['outputs'] = [o for o in cells[5]['outputs'] if o.get('output_type') != 'display_data']
        with self.assertRaisesRegex(ValueError, 'notebook image missing'):
            self.verify(notebook=notebook)

    def test_original_visual_pending_not_promoted(self):
        report = copy.deepcopy(self.report)
        report['display']['visual_status'] = 'PASS'
        with self.assertRaisesRegex(ValueError, 'pending/closed'):
            self.verify(report=report)


if __name__ == '__main__':
    unittest.main()
