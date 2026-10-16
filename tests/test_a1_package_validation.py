"""Regression: normal Jupyter saves must not reject intact hardware or test code."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import a1_point_board_test as runner


class PackageValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.notebook = {"nbformat": 4, "nbformat_minor": 4, "metadata": {}, "cells": [
            {"cell_type": "markdown", "source": ["Instructions\n"], "metadata": {}},
            {"cell_type": "code", "source": ["x = 1\n", "print(x)\n"], "execution_count": None,
             "outputs": [], "metadata": {}}]}
        for name in runner.FIXED_ARTIFACTS:
            (self.directory / name).write_bytes(("original:" + name).encode())
        self.save_notebook(self.notebook)
        self.manifest = {"revision": runner.REVISION, "artifacts": {
            p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in self.directory.iterdir()}, "notebook_validation": {
                "algorithm": "sha256-code-cells-v1", "sha256": runner.notebook_code_hash(self.notebook)}}

    def save_notebook(self, notebook):
        (self.directory / runner.NOTEBOOK_NAME).write_text(json.dumps(notebook, indent=4), encoding="utf-8")

    def test_unexecuted_package_passes(self):
        result = runner.validate_package(self.directory, self.manifest)
        self.assertEqual(result["fixed_artifacts"], "PASS_EXACT_SHA256")

    def test_saved_execution_metadata_and_output_pass_but_raw_hash_changes(self):
        nb = copy.deepcopy(self.notebook)
        nb["metadata"] = {"trusted": True, "language_info": {"version": "3.10.4"}}
        nb["cells"][0]["source"] = "Updated display instructions"
        nb["cells"][1].update(execution_count=2, outputs=[{"output_type": "stream", "name": "stdout", "text": ["1\n"]}],
                              metadata={"execution": {"iopub.status.idle": "board-clock"}}, id="generated-cell-id")
        nb["cells"][1]["source"] = "x = 1\r\nprint(x)\r\n"
        self.save_notebook(nb)
        result = runner.validate_package(self.directory, self.manifest)
        self.assertEqual(result["notebook_code"], "PASS_CANONICAL_CODE_SHA256")
        self.assertNotEqual(result["current_notebook_sha256"], result["original_notebook_sha256"])

    def test_changed_executable_code_is_rejected(self):
        nb = copy.deepcopy(self.notebook)
        nb["cells"][1]["source"] = "x = 2\nprint(x)\n"
        self.save_notebook(nb)
        with self.assertRaisesRegex(ValueError, "Notebook code mismatch"):
            runner.validate_package(self.directory, self.manifest)

    def test_corrupted_fixed_files_are_all_rejected(self):
        for name in runner.FIXED_ARTIFACTS:
            with self.subTest(name=name):
                path = self.directory / name
                original = path.read_bytes()
                path.write_bytes(original + b"corrupted")
                with self.assertRaisesRegex(ValueError, "Package mismatch"):
                    runner.validate_package(self.directory, self.manifest)
                path.write_bytes(original)

    def test_missing_contract_or_artifact_cannot_disable_verification(self):
        manifest = copy.deepcopy(self.manifest)
        manifest.pop("notebook_validation")
        with self.assertRaises(ValueError): runner.validate_package(self.directory, manifest)
        manifest = copy.deepcopy(self.manifest)
        manifest["artifacts"].pop("a1_point.bit")
        with self.assertRaises(ValueError): runner.validate_package(self.directory, manifest)

    def test_old_revision_and_empty_code_are_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["revision"] = "a1_point_r1"
        with self.assertRaises(ValueError): runner.validate_package(self.directory, manifest)
        with self.assertRaises(ValueError): runner.notebook_code_hash({"nbformat": 4, "cells": []})


if __name__ == "__main__":
    unittest.main()
