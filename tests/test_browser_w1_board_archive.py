"""Offline regressions using preserved board evidence, never fresh board measurements.

Raw archive/Notebook remain in ignored build/board_results; corrupt variants are
temporary HOST negative fixtures and cannot replace the preserved originals.
"""
import csv
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_browser_w1_archive import verify

PACKAGE = ROOT / 'build/deploy/browser_a4_w1_r1'
ORIGINAL = ROOT / 'build/board_results/browser_w1_2026-10-13'
ARCHIVE = ORIGINAL / 'browser_session_bundle.zip'
NOTEBOOK = ORIGINAL / 'browser_start.ipynb'


class BoardArchiveRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checked = verify(ARCHIVE, NOTEBOOK, PACKAGE, allow_incomplete_display=True)

    def corrupt_archive(self, directory, changes):
        target = Path(directory) / 'HOST_NEGATIVE_CORRUPTED_ARCHIVE.zip'
        with zipfile.ZipFile(ARCHIVE) as original, zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as altered:
            for name in original.namelist():
                data = original.read(name)
                altered.writestr(name, changes[name](data) if name in changes else data)
        return target

    def test_partial_audit_keeps_all_numeric_checks_and_missing_display_pending(self):
        report = self.checked
        self.assertEqual(report['verified_runs'], 24)
        self.assertEqual(report['matched_words'], 6094848)
        self.assertEqual(report['matched_png_images'], 120)
        self.assertEqual(report['matched_png_values'], 54853632)
        self.assertEqual(report['lifecycle']['execution_counts'], [1, 2, 3, 4, 5, 6])
        self.assertEqual(report['coverage']['sides'], [256, 512])
        self.assertTrue(report['numeric_and_functional_evidence_verified'])
        self.assertFalse(report['visible_20_frame_loop_verified'])
        self.assertFalse(report['final_acceptance_pass'])
        self.assertFalse(report['full_performance_pass'])
        self.assertFalse(report['adjustable_threshold_pass'])
        self.assertIsNone(report['pl_core_frame_ns'])
        loop, = report['display_loops'].values()
        self.assertEqual(loop['hidden_indices'], [2, 5, 14, 15])
        self.assertIsNone(loop['verified_fps'])
        summary, = report['timing_summary'].values()
        self.assertEqual(summary['native_runs'], 20)
        self.assertEqual(summary['visible_request_latency_ms']['n'], 16)
        self.assertAlmostEqual(summary['server_latency_ms']['dma_transaction_ms']['mean'], 6.57690325)
        self.assertAlmostEqual(summary['server_latency_ms']['inference_ms']['mean'], 31.8435444)
        self.assertAlmostEqual(summary['server_latency_ms']['png_encoding_ms']['mean'], 4654.51913315)
        self.assertIsNone(summary['browser_actual_fps'])

    def test_strict_audit_still_rejects_hidden_display_loop(self):
        with self.assertRaisesRegex(ValueError, 'Visible 20-frame browser loop missing'):
            verify(ARCHIVE, NOTEBOOK, PACKAGE)

    def test_partial_audit_rejects_corrupted_csv_latency(self):
        def change(data):
            reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
            rows = list(reader)
            rows[0]['dma_transaction_ns'] = str(int(rows[0]['dma_transaction_ns']) + 1)
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=reader.fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            return stream.getvalue().encode('utf-8-sig')
        with tempfile.TemporaryDirectory(prefix='HOST_w1_negative_') as directory:
            changed = self.corrupt_archive(directory, {'measurements.csv': change})
            with self.assertRaisesRegex(ValueError, 'CSV latency mismatch'):
                verify(changed, NOTEBOOK, PACKAGE, allow_incomplete_display=True)

    def test_partial_audit_rejects_invented_fps_after_hidden_frame(self):
        name = self.checked['runs'][-1]['run_id'] + '/browser_timing.json'
        def change(data):
            value = json.loads(data)
            value['browser_actual_fps'] = 0.18
            return json.dumps(value).encode()
        with tempfile.TemporaryDirectory(prefix='HOST_w1_negative_') as directory:
            changed = self.corrupt_archive(directory, {name: change})
            with self.assertRaisesRegex(ValueError, 'Client FPS not unique'):
                verify(changed, NOTEBOOK, PACKAGE, allow_incomplete_display=True)

    def test_csv_quality_must_still_match_recomputed_real_mask(self):
        def change(data):
            reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
            rows = list(reader)
            rows[0]['dice_AH'] = '0.99'
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=reader.fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            return stream.getvalue().encode('utf-8-sig')
        with tempfile.TemporaryDirectory(prefix='HOST_w1_negative_') as directory:
            changed = self.corrupt_archive(directory, {'measurements.csv': change})
            with self.assertRaisesRegex(ValueError, 'CSV quality/browser observation mismatch'):
                verify(changed, NOTEBOOK, PACKAGE, allow_incomplete_display=True)

    def test_missing_close_output_cannot_prove_clean_lifecycle(self):
        notebook = json.loads(NOTEBOOK.read_bytes())
        code = [cell for cell in notebook['cells'] if cell['cell_type'] == 'code' and cell.get('execution_count') is not None]
        code[-1]['outputs'] = []
        with tempfile.TemporaryDirectory(prefix='HOST_w1_negative_') as directory:
            target = Path(directory) / 'HOST_NEGATIVE_MISSING_CLOSE.ipynb'
            target.write_text(json.dumps(notebook), encoding='utf-8', newline='\n')
            with self.assertRaisesRegex(ValueError, 'Notebook lifecycle marker missing'):
                verify(ARCHIVE, target, PACKAGE, allow_incomplete_display=True)

    def test_partial_audit_cannot_accept_host_preview_as_board(self):
        def change(data):
            value = json.loads(data)
            value['evidence_kind'] = 'HOST_TEST_DOUBLE_NOT_BOARD'
            return json.dumps(value).encode()
        with tempfile.TemporaryDirectory(prefix='HOST_w1_negative_') as directory:
            changed = self.corrupt_archive(directory, {'capabilities.json': change})
            with self.assertRaisesRegex(ValueError, 'HOST TEST preview is not board evidence'):
                verify(changed, NOTEBOOK, PACKAGE, allow_incomplete_display=True)

    def test_supplement_must_be_new_native_session_not_reexport(self):
        with self.assertRaisesRegex(ValueError, 'Supplement repeats prior session'):
            verify(ARCHIVE, NOTEBOOK, PACKAGE, allow_incomplete_display=True, prior_bringup=(ARCHIVE, NOTEBOOK))


if __name__ == '__main__':
    unittest.main(verbosity=2)
