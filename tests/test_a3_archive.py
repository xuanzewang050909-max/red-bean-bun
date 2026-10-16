"""Archive corruption checks; these host checks are not new board executions."""
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import archive_a3_board_results as archive

RAW = ROOT / "build/board_results/a3_background_2026-10-12"
PACKAGE = ROOT / "build/deploy/a3_background_2017_4_r1"


class BundleBoundaryTests(unittest.TestCase):
    def bundle(self, names, symlink=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "evidence.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with ZipFile(path, "w") as output:
                for index, name in enumerate(names):
                    if symlink and index == 0:
                        item = ZipInfo(name)
                        item.create_system = 3
                        item.external_attr = (stat.S_IFLNK | 0o777) << 16
                        output.writestr(item, b"target")
                    else:
                        output.writestr(name, b"placeholder")
        return path

    def test_duplicate_members_rejected(self):
        names = sorted(archive.BUNDLE_NAMES)
        names[-1] = names[0]
        with self.assertRaisesRegex(ValueError, "ZIP member"):
            archive.read_bundle(self.bundle(names))

    def test_traversal_member_rejected_without_extraction(self):
        names = sorted(archive.BUNDLE_NAMES)
        names[0] = "../a3_background_result.json"
        with self.assertRaisesRegex(ValueError, "ZIP member"):
            archive.read_bundle(self.bundle(names))

    def test_missing_member_rejected(self):
        with self.assertRaisesRegex(ValueError, "ZIP member"):
            archive.read_bundle(self.bundle(sorted(archive.BUNDLE_NAMES)[:-1]))

    def test_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported ZIP member"):
            archive.read_bundle(self.bundle(sorted(archive.BUNDLE_NAMES), symlink=True))

    def test_oversized_member_rejected(self):
        path = self.bundle(sorted(archive.BUNDLE_NAMES))
        with ZipFile(path, "w") as output:
            for name in sorted(archive.BUNDLE_NAMES):
                output.writestr(name, b"x" * (500_001 if name == "a3_background_result.json" else 1))
        with self.assertRaisesRegex(ValueError, "member size"):
            archive.read_bundle(path)


@unittest.skipUnless((RAW / "a3_results_bundle.zip").is_file() and (PACKAGE / "a3_manifest.json").is_file(),
                     "Real A3 data are kept in the ignored local archive, not redistributed in Git")
class ActualEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.members = archive.read_bundle(RAW / "a3_results_bundle.zip")
        cls.report = json.loads(cls.members["a3_background_result.json"])
        cls.notebook = json.loads((RAW / "a3_background_check_executed.ipynb").read_bytes())
        cls.manifest = json.loads((PACKAGE / "a3_manifest.json").read_bytes())
        archive.validate_a3_package(PACKAGE, cls.manifest)

    def verify(self, report=None, notebook=None, members=None):
        return archive.verify_records(self.notebook if notebook is None else notebook,
                                      self.report if report is None else report, self.manifest, PACKAGE,
                                      self.members if members is None else members)

    def test_actual_downloaded_records_and_all_raw_arrays_match(self):
        checks = self.verify()
        self.assertEqual(sum(item["words"] for item in checks["frames"]), 7_274_496)
        self.assertEqual(sum(item["words"] for item in checks["raw_arrays"]), 655_360)
        self.assertTrue(all(item["mismatched_words"] == 0 for item in checks["raw_arrays"]))

    def test_notebook_save_metadata_and_markdown_remain_mutable(self):
        notebook = copy.deepcopy(self.notebook)
        notebook["metadata"]["archive_test"] = True
        next(cell for cell in notebook["cells"] if cell["cell_type"] == "markdown")["source"] = ["Changed explanatory text"]
        self.verify(notebook=notebook)

    def test_code_edit_rejected(self):
        notebook = copy.deepcopy(self.notebook)
        next(cell for cell in notebook["cells"] if cell["cell_type"] == "code")["source"] += ["\nraise RuntimeError('changed')"]
        with self.assertRaisesRegex(ValueError, "code changed"):
            self.verify(notebook=notebook)

    def test_error_output_rejected(self):
        notebook = copy.deepcopy(self.notebook)
        next(cell for cell in notebook["cells"] if cell["cell_type"] == "code")["outputs"].append({"output_type": "error"})
        with self.assertRaisesRegex(ValueError, "error output"):
            self.verify(notebook=notebook)

    def test_partial_suite_rejected(self):
        report = copy.deepcopy(self.report)
        report["transfers"].pop()
        with self.assertRaisesRegex(ValueError, "Incomplete frame records"):
            self.verify(report=report)

    def test_wrong_runtime_rejected(self):
        report = copy.deepcopy(self.report)
        report["pynq"] = "2.2.1"
        with self.assertRaisesRegex(ValueError, "runtime"):
            self.verify(report=report)

    def test_wrong_release_rejected(self):
        report = copy.deepcopy(self.report)
        report["manifest"]["revision"] += "_different"
        with self.assertRaisesRegex(ValueError, "different release"):
            self.verify(report=report)

    def test_incorrect_byte_count_rejected(self):
        report = copy.deepcopy(self.report)
        report["transfers"][0]["recv_bytes"] -= 4
        with self.assertRaisesRegex(ValueError, "byte count"):
            self.verify(report=report)

    def test_dma_error_rejected(self):
        report = copy.deepcopy(self.report)
        report["transfers"][0]["dma_status"]["s2mm"] |= 0x10
        with self.assertRaisesRegex(ValueError, "DMA halted"):
            self.verify(report=report)

    def test_overlapping_buffers_rejected(self):
        report = copy.deepcopy(self.report)
        report["transfers"][0]["rx_address"] = report["transfers"][0]["tx_address"]
        with self.assertRaisesRegex(ValueError, "DDR buffers"):
            self.verify(report=report)

    def test_counter_or_protocol_error_rejected(self):
        report = copy.deepcopy(self.report)
        report["transfers"][0]["frame_status"] |= 1 << 28
        with self.assertRaisesRegex(ValueError, "counters or error"):
            self.verify(report=report)

    def test_unchanged_expected_but_wrong_output_hash_rejected(self):
        report = copy.deepcopy(self.report)
        report["transfers"][0]["output_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.verify(report=report)

    def test_changed_raw_word_rejected_even_if_file_hash_is_updated(self):
        for mode, shift in ((2, 0), (2, 8), (2, 16), (2, 24), (3, 16), (3, 24)):
            with self.subTest(mode=mode, diagnostic_byte=shift // 8):
                report, members = copy.deepcopy(self.report), dict(self.members)
                record = next(item for item in report["transfers"]
                              if "saved_output" in item and item["mode"] == mode)
                name = record["saved_output"]["name"]
                words = np.load(io.BytesIO(members[name]), allow_pickle=False)
                words[128, 128] ^= np.uint32(1 << shift)
                stream = io.BytesIO()
                np.save(stream, words)
                members[name] = stream.getvalue()
                record["saved_output"]["sha256"] = archive.digest(members[name])
                with self.assertRaisesRegex(ValueError, "differs from the M0 golden"):
                    self.verify(report=report, members=members)

    def test_changed_background_preview_rejected_even_if_hash_is_updated(self):
        from PIL import Image
        report, members = copy.deepcopy(self.report), dict(self.members)
        pixels = archive.decoded_png(members["a3_preview.png"])
        pixels[128, 640] ^= np.uint8(1)
        stream = io.BytesIO()
        Image.fromarray(pixels).save(stream, format="PNG")
        members["a3_preview.png"] = stream.getvalue()
        report["preview"]["sha256"] = archive.digest(members["a3_preview.png"])
        with self.assertRaisesRegex(ValueError, "FPGA diagnostic byte"):
            self.verify(report=report, members=members)

    def test_changed_preview_rejected(self):
        members = dict(self.members)
        members["a3_preview.png"] += b"alteration"
        with self.assertRaisesRegex(ValueError, "Preview file hash"):
            self.verify(members=members)


if __name__ == "__main__":
    unittest.main()
