"""Exercise assembled A2 release validation without touching real package files."""
import argparse
import copy
import json
import shutil
import tempfile
from pathlib import Path
from a2_gaussian_board_test import validate_a2_package, NOTEBOOK
from package_a2 import check_hardware

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Preserve earlier validation; choose a new output")
    manifest = json.loads((args.package / "a2_manifest.json").read_text(encoding="utf-8"))
    checks = []
    validate_a2_package(args.package, manifest)
    checks.append({"case": "actual_ten_file_package", "result": "PASS_VALID"})
    with tempfile.TemporaryDirectory(dir=ROOT / "build", prefix="a2_release_check_") as temporary:
        staged = Path(temporary)
        assert staged.resolve().is_relative_to((ROOT / "build").resolve())
        for file in args.package.iterdir():
            shutil.copyfile(file, staged / file.name)
        nb = json.loads((staged / NOTEBOOK).read_text(encoding="utf-8"))
        original = copy.deepcopy(nb)
        def save():
            (staged / NOTEBOOK).write_text(json.dumps(nb), encoding="utf-8")
        def rejected(name, action):
            try:
                action()
            except ValueError as error:
                checks.append({"case": name, "result": "PASS_REJECTED", "error": str(error)})
            else:
                raise AssertionError("Mismatch accepted: " + name)
        for cell in nb["cells"]:
            if cell["cell_type"] == "code":
                cell.update(execution_count=7, outputs=[{"output_type": "stream", "name": "stdout", "text": "save probe, not board result"}])
        nb["metadata"]["save_probe"] = True
        save()
        validate_a2_package(staged, manifest)
        checks.append({"case": "saved_execution_metadata_outputs", "result": "PASS_VALID"})
        next(c for c in nb["cells"] if c["cell_type"] == "markdown")["source"] = ["Changed explanation only"]
        save()
        validate_a2_package(staged, manifest)
        checks.append({"case": "markdown_only_change", "result": "PASS_VALID_BY_CODE_CONTRACT"})
        next(c for c in nb["cells"] if c["cell_type"] == "code")["source"] = ['print("changed code")\n']
        save()
        rejected("changed_executable_code", lambda: validate_a2_package(staged, manifest))
        nb = original
        save()
        for name in ("a2_gaussian.bit", "a2_gaussian.hwh", "a2_gaussian_board_test.py", "stare_im0001_512.npy"):
            file = staged / name
            raw = file.read_bytes()
            file.write_bytes(raw + b"altered")
            rejected("altered_" + name, lambda: validate_a2_package(staged, manifest))
            file.write_bytes(raw)
        rejected("withdrawn_first_hardware_build", lambda: check_hardware(ROOT / "build/a2_gaussian_01", ROOT / "results/a2_gaussian_2017_4"))
        validate_a2_package(staged, manifest)
    args.output.write_text(json.dumps({"status": "PASS_HOST_ASSEMBLED_PACKAGE_VALIDATION", "board_status": "NOT_RUN", "checks": checks}, indent=2) + "\n", encoding="utf-8")
    print("A2_ASSEMBLED_PACKAGE_VALIDATION_PASS", len(checks), "checks; board NOT_RUN")


if __name__ == "__main__":
    main()
