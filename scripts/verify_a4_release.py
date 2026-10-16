"""Host gates on the assembled A4 package, always leaving the release untouched."""
import argparse
import copy
import json
import shutil
import tempfile
from pathlib import Path
from a4_segmentation_board_test import validate_a4_package, FIXED, NOTEBOOK

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Preserve earlier verification output")
    manifest = json.loads((args.package / "a4_manifest.json").read_text(encoding="utf-8"))
    checks = []
    if set(p.name for p in args.package.iterdir()) != FIXED | {NOTEBOOK, "a4_manifest.json"}:
        raise ValueError("Unexpected release contents")
    if manifest["board_status"] != "NOT_RUN" or manifest["board_suite_frames"] != 61:
        raise ValueError("Release status or suite incorrect")
    validate_a4_package(args.package, manifest)
    checks.append({"case": "actual_twelve_file_package", "result": "PASS_VALID"})
    with tempfile.TemporaryDirectory(dir=ROOT / "build", prefix="a4_release_check_") as temporary:
        staged = Path(temporary)
        for file in args.package.iterdir():
            shutil.copyfile(file, staged / file.name)
        nb = json.loads((staged / NOTEBOOK).read_text(encoding="utf-8"))
        original = copy.deepcopy(nb)
        def save():
            (staged / NOTEBOOK).write_text(json.dumps(nb), encoding="utf-8")
        def rejected(name, changed_manifest=manifest):
            try:
                validate_a4_package(staged, changed_manifest)
            except ValueError as error:
                checks.append({"case": name, "result": "PASS_REJECTED", "error": str(error)})
            else:
                raise AssertionError("Mismatch accepted: " + name)
        for cell in nb["cells"]:
            if cell["cell_type"] == "code":
                cell.update(execution_count=7, outputs=[{"output_type": "stream", "name": "stdout", "text": "host save probe only"}])
        nb["metadata"]["save_probe"] = True
        save()
        validate_a4_package(staged, manifest)
        checks.append({"case": "saved_execution_metadata_outputs", "result": "PASS_VALID"})
        next(c for c in nb["cells"] if c["cell_type"] == "markdown")["source"] = ["Changed explanation only"]
        save()
        validate_a4_package(staged, manifest)
        checks.append({"case": "markdown_change", "result": "PASS_VALID_BY_CODE_CONTRACT"})
        next(c for c in nb["cells"] if c["cell_type"] == "code")["source"] = ['print("changed executable code")\n']
        save()
        rejected("changed_notebook_code")
        nb = original
        save()
        for name in sorted(FIXED):
            file = staged / name
            raw = file.read_bytes()
            file.write_bytes(raw + b"altered")
            rejected("altered_" + name)
            file.write_bytes(raw)
        changed = copy.deepcopy(manifest)
        changed["revision"] = "a3_background_r1_vendor_box"
        rejected("wrong_stage_revision", changed)
        changed = copy.deepcopy(manifest)
        changed["artifacts"].pop("a4_segmentation.hwh")
        rejected("missing_hwh_manifest_entry", changed)
        validate_a4_package(staged, manifest)
    args.output.write_text(json.dumps({"status": "PASS_HOST_ASSEMBLED_PACKAGE_VALIDATION", "board_status": "NOT_RUN",
        "checks": checks}, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("A4_ASSEMBLED_PACKAGE_VALIDATION_PASS", len(checks), "checks; board NOT_RUN")


if __name__ == "__main__":
    main()
