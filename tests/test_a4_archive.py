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
import archive_a4_board_results as archive

LOCAL_ARCHIVE = ROOT / "build/board_results/a4_segmentation_2026-10-12"
RAW = LOCAL_ARCHIVE if (LOCAL_ARCHIVE / "a4_results_bundle.zip").is_file() else Path.home() / "Downloads"
NOTEBOOK_NAME = "a4_segmentation_check_executed.ipynb" if RAW == LOCAL_ARCHIVE else "a4_segmentation_check.ipynb"
PACKAGE = ROOT / "build/deploy/a4_segmentation_2017_4_r1"


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
        names[0] = "../a4_segmentation_result.json"
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
                output.writestr(name, b"x" * (500_001 if name == "a4_segmentation_result.json" else 1))
        with self.assertRaisesRegex(ValueError, "member size"):
            archive.read_bundle(path)


@unittest.skipUnless((RAW / "a4_results_bundle.zip").is_file() and (PACKAGE / "a4_manifest.json").is_file(),
                     "Real A4 data are kept in the ignored local archive, not redistributed in Git")
class ActualEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.members = archive.read_bundle(RAW / "a4_results_bundle.zip")
        cls.report = json.loads(cls.members["a4_segmentation_result.json"])
        cls.notebook = json.loads((RAW / NOTEBOOK_NAME).read_bytes())
        cls.manifest = json.loads((PACKAGE / "a4_manifest.json").read_bytes())
        archive.validate_a4_package(PACKAGE, cls.manifest)

    def verify(self, report=None, notebook=None, members=None):
        return archive.verify_records(self.notebook if notebook is None else notebook,
                                      self.report if report is None else report, self.manifest, PACKAGE,
                                      self.members if members is None else members)

    def test_actual_downloaded_records_and_all_raw_arrays_match(self):
        checks = self.verify()
        self.assertEqual(sum(item["words"] for item in checks["frames"]), 9_895_936)
        self.assertEqual(sum(item["words"] for item in checks["raw_arrays"]), 983_040)
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
        for mode, shift in ((mode, shift) for mode in (1, 2, 3) for shift in (0, 8, 16, 24)):
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

    def test_changed_binary_mask_preview_rejected_even_if_hash_is_updated(self):
        from PIL import Image
        report, members = copy.deepcopy(self.report), dict(self.members)
        pixels = archive.decoded_png(members["a4_preview.png"])
        pixels[128, 640] ^= np.uint8(1)
        stream = io.BytesIO()
        Image.fromarray(pixels).save(stream, format="PNG")
        members["a4_preview.png"] = stream.getvalue()
        report["preview"]["sha256"] = archive.digest(members["a4_preview.png"])
        with self.assertRaisesRegex(ValueError, "FPGA diagnostic byte"):
            self.verify(report=report, members=members)

    def test_changed_preview_rejected(self):
        members = dict(self.members)
        members["a4_preview.png"] += b"alteration"
        with self.assertRaisesRegex(ValueError, "Preview file hash"):
            self.verify(members=members)


    def test_changed_frame_order_rejected(self):
        report = copy.deepcopy(self.report)
        report["transfers"][1], report["transfers"][2] = report["transfers"][2], report["transfers"][1]
        with self.assertRaisesRegex(ValueError, "Unexpected frame order"):
            self.verify(report=report)

    def test_only_smoke_status_rejected(self):
        report = copy.deepcopy(self.report)
        report["status"] = "A4_SMOKE_PASS_FULL_PENDING"
        with self.assertRaisesRegex(ValueError, "incomplete or failed"):
            self.verify(report=report)

    def test_duplicate_completion_marker_rejected(self):
        notebook = copy.deepcopy(self.notebook)
        code = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
        code[2]["outputs"].append({"output_type": "stream", "name": "stdout", "text": ["A4_LOAD_PASS: official drivers and reset state checked\n"]})
        with self.assertRaisesRegex(ValueError, "completion marker"):
            self.verify(notebook=notebook)

    def test_changed_embedded_preview_rejected(self):
        import base64
        from PIL import Image
        notebook = copy.deepcopy(self.notebook)
        cell = [c for c in notebook["cells"] if c["cell_type"] == "code"][5]
        output = next(o for o in cell["outputs"] if "image/png" in o.get("data", {}))
        pixels = archive.decoded_png(self.members["a4_preview.png"])
        pixels[128, 640] ^= np.uint8(1)
        stream = io.BytesIO()
        Image.fromarray(pixels).save(stream, format="PNG")
        output["data"]["image/png"] = base64.b64encode(stream.getvalue()).decode()
        with self.assertRaisesRegex(ValueError, "Notebook preview differs"):
            self.verify(notebook=notebook)

    def test_bicubic_binary_mask_rejected_even_if_hash_is_updated(self):
        from PIL import Image
        report, members = copy.deepcopy(self.report), dict(self.members)
        pixels = archive.decoded_png(members["a4_preview.png"])
        words = np.load(io.BytesIO(members["a4_output_stare_512_mode3.npy"]), allow_pickle=False)
        mask = ((words >> 16) & 255).astype(np.uint8)
        wrong = np.asarray(Image.fromarray(mask).resize((256, 256), Image.Resampling.BICUBIC))
        pixels[24:, 512:768] = wrong[:, :, None]
        stream = io.BytesIO()
        Image.fromarray(pixels).save(stream, format="PNG")
        members["a4_preview.png"] = stream.getvalue()
        report["preview"]["sha256"] = archive.digest(members["a4_preview.png"])
        with self.assertRaisesRegex(ValueError, "FPGA diagnostic byte"):
            self.verify(report=report, members=members)

    def test_final_fov_and_binary_values_in_actual_buffers(self):
        checks = self.verify()
        self.assertEqual(len(checks["raw_arrays"]), 6)
        for record in checks["raw_arrays"]:
            self.assertTrue(set(record["mask_byte_values"]).issubset({0, 255}))
            if "mode3" in record["name"]:
                self.assertEqual(record["final_mask_outside_fov_pixels"], 0)


if __name__ == "__main__":
    unittest.main()
