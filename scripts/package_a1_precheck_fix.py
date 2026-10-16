"""Derive a software-only r2 release from verified r1; preserve hardware/history."""
import argparse
import copy
import json
import shutil
import tempfile
from pathlib import Path

from a1_point_board_test import (REVISION, FIXED_ARTIFACTS, NOTEBOOK_NAME,
                                 notebook_code_hash, validate_package)
from a0_dma_board_test import sha256_file

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("patch_destination", type=Path)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    baseline_manifest = args.baseline / "a1_manifest.json"
    original = json.loads(baseline_manifest.read_text(encoding="utf-8"))
    if original["revision"] != "a1_point_r1" or original["host_status"] != "PASS_HOST_BUILD_METADATA_RTL_AND_VENDOR_RESET_SIMULATION":
        raise ValueError("Expected validated r1 host release")
    historical = ROOT / "results/a1_point_2017_4/release_manifest.json"
    if baseline_manifest.read_bytes() != historical.read_bytes():
        raise ValueError("Baseline manifest differs from archived release")
    if set(original["artifacts"]) != FIXED_ARTIFACTS | {NOTEBOOK_NAME}:
        raise ValueError("Incomplete baseline")
    for name, record in original["artifacts"].items():
        if sha256_file(args.baseline / name) != record["sha256"]:
            raise ValueError("Baseline artifact changed: " + name)
    for name, record in original["source_files"].items():
        # The packager changes for r2; all actual hardware/build sources stay exact.
        if Path(name).name != "package_a1.py" and sha256_file(ROOT / name) != record["sha256"]:
            raise ValueError("Hardware source changed: " + name)
    tests = (args.results / "host_regression_tests.log").read_text(encoding="utf-8")
    if "Ran 25 tests" not in tests or "\nOK" not in tests:
        raise ValueError("Current regression suite has not passed")
    if args.destination.exists() or args.patch_destination.exists() or (args.results / "release_manifest.json").exists():
        raise ValueError("Refusing to overwrite a release")
    manifest = copy.deepcopy(original)
    manifest.update(revision=REVISION, board_status="NOT_RUN",
                    host_status="PASS_REUSED_R1_HARDWARE_AND_R2_PACKAGE_REGRESSION")
    manifest["hardware_provenance"] = {
        "baseline_manifest": str(historical.relative_to(ROOT)),
        "baseline_manifest_sha256": sha256_file(baseline_manifest),
        "baseline_git_attestation": "results/a1_point_2017_4/release_git_attestation.json",
        "hardware_rebuilt": False,
        "policy": "Original bit/HWH, HDL, timing, reset simulation and build evidence reused byte-for-byte"}
    manifest["notebook_validation"] = {
        "algorithm": "sha256-code-cells-v1",
        "sha256": notebook_code_hash(json.loads((args.baseline / NOTEBOOK_NAME).read_text(encoding="utf-8")))}
    args.destination.mkdir(parents=True)
    for name in original["artifacts"]:
        shutil.copyfile(args.baseline / name, args.destination / name)
    shutil.copyfile(ROOT / "scripts/a1_point_board_test.py", args.destination / "a1_point_board_test.py")
    runner = args.destination / "a1_point_board_test.py"
    manifest["artifacts"][runner.name] = {"bytes": runner.stat().st_size, "sha256": sha256_file(runner)}
    manifest["software_patch_sources"] = {str(path.relative_to(ROOT)): {
        "bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in (
            ROOT / "scripts/a1_point_board_test.py", Path(__file__), ROOT / "tests/test_a1_package_validation.py")}
    payload = json.dumps(manifest, indent=2) + "\n"
    (args.destination / "a1_manifest.json").write_text(payload, encoding="utf-8")
    validation = {"original_r2_package": validate_package(args.destination, manifest)}
    with tempfile.TemporaryDirectory() as directory:
        saved = Path(directory)
        for name in manifest["artifacts"]:
            shutil.copyfile(args.destination / name, saved / name)
        nb = json.loads((saved / NOTEBOOK_NAME).read_text(encoding="utf-8"))
        nb["metadata"]["language_info"] = {"name": "python", "version": "3.10.4"}
        for i, cell in enumerate(nb["cells"]):
            if cell["cell_type"] == "code":
                cell["execution_count"] = i + 1
                cell["outputs"] = [{"output_type": "stream", "name": "stdout", "text": ["HOST_SAVE_SIMULATION_ONLY\n"]}]
                cell["metadata"]["trusted"] = True
        (saved / NOTEBOOK_NAME).write_text(json.dumps(nb, indent=1), encoding="utf-8")
        result = validate_package(saved, manifest)
        if result["current_notebook_sha256"] == result["original_notebook_sha256"]:
            raise ValueError("Save regression did not change the raw notebook")
        validation["simulated_jupyter_save_on_real_package"] = result
    args.patch_destination.mkdir(parents=True)
    for name in ("a1_point_board_test.py", "a1_manifest.json"):
        shutil.copyfile(args.destination / name, args.patch_destination / name)
    validation.update(host_only=True, board_status="NOT_RUN", patch_files=["a1_point_board_test.py", "a1_manifest.json"],
                      full_package=str(args.destination.resolve()), patch_package=str(args.patch_destination.resolve()),
                      baseline_manifest_sha256=sha256_file(baseline_manifest))
    (args.results / "release_manifest.json").write_text(payload, encoding="utf-8")
    (args.results / "package_validation.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    print("A1_R2_PRECHECK_FIX_PACKAGED_HOST_VERIFIED_BOARD_PENDING", args.patch_destination)


if __name__ == "__main__":
    main()
