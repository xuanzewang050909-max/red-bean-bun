"""Capture or replay explicit A3-to-A4 diffs; never edit immutable baselines.

The recorded base bytes must also match the board-verified A3 Git commit.
Verification applies patches in memory and compares every reproduced byte.
"""
import argparse
import difflib
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "cd0ad6a"
PAIRS = [
    ("hls/retina_background_hls.cpp", "hls/retina_segmentation_hls.cpp"),
    ("hls/retina_background_hls.hpp", "hls/retina_segmentation_hls.hpp"),
    ("tests/retina_background_hls_tb.cpp", "tests/retina_segmentation_hls_tb.cpp"),
    ("tests/retina_background_axis_tb.sv", "tests/retina_segmentation_axis_tb.sv"),
    ("scripts/a3_background_board_test.py", "scripts/a4_segmentation_board_test.py"),
    ("scripts/prepare_a3_vectors.py", "scripts/prepare_a4_vectors.py"),
    ("scripts/run_background_simulation.ps1", "scripts/run_segmentation_simulation.ps1"),
    ("scripts/repack_a3_ip.py", "scripts/repack_a4_ip.py"),
    ("vivado/scripts/build_a3_hls.tcl", "vivado/scripts/build_a4_hls.tcl"),
    ("vivado/scripts/build_a3_background.tcl", "vivado/scripts/build_a4_segmentation.tcl"),
    ("vivado/scripts/simulate_a3_reset.tcl", "vivado/scripts/simulate_a4_reset.tcl"),
    ("scripts/build_a3_notebook.py", "scripts/build_a4_notebook.py"),
    ("scripts/package_a3.py", "scripts/package_a4.py"),
    ("scripts/verify_a3_release.py", "scripts/verify_a4_release.py"),
    ("scripts/attest_a3_sources.py", "scripts/attest_a4_sources.py"),
    ("tests/test_a3_board_runner.py", "tests/test_a4_board_runner.py"),
    ("docs/a3_background_validation_steps.md", "docs/a4_segmentation_validation_steps.md"),
]


def info(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def apply_unified(before, patch):
    source = before.splitlines(keepends=True)
    changes = patch.splitlines(keepends=True)
    output, position, cursor = [], 0, 2
    if not changes[0].startswith("--- ") or not changes[1].startswith("+++ "):
        raise ValueError("Invalid diff header")
    while cursor < len(changes):
        header = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\n", changes[cursor])
        if not header:
            raise ValueError("Invalid hunk header")
        old_start, old_count, new_start, new_count = [int(value) if value is not None else 1 for value in header.groups()]
        target = old_start - 1 if old_count else old_start
        if target < position:
            raise ValueError("Overlapping hunks")
        output.extend(source[position:target])
        position, old_seen, new_seen = target, 0, 0
        if len(output) != (new_start - 1 if new_count else new_start):
            raise ValueError("Wrong new hunk location")
        cursor += 1
        while cursor < len(changes) and not changes[cursor].startswith("@@ "):
            line = changes[cursor]
            kind, value = line[:1], line[1:]
            if kind in (" ", "-"):
                if position >= len(source) or source[position] != value:
                    raise ValueError("Patch context mismatch")
                position += 1
                old_seen += 1
            if kind in (" ", "+"):
                output.append(value)
                new_seen += 1
            if kind not in (" ", "+", "-"):
                raise ValueError("Unsupported diff record")
            cursor += 1
        if (old_seen, new_seen) != (old_count, new_count):
            raise ValueError("Wrong hunk length")
    output.extend(source[position:])
    return "".join(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    evidence = args.evidence
    if args.capture:
        if evidence.exists():
            raise ValueError("Preserve earlier derivation evidence")
        records = []
        for index, (base, derived) in enumerate(PAIRS, start=1):
            before, after = (ROOT / base).read_bytes(), (ROOT / derived).read_bytes()
            pinned = subprocess.check_output(["git", "show", BASE_COMMIT + ":" + base], cwd=ROOT)
            if before != pinned:
                raise ValueError("A3 baseline changed: " + base)
            patch = "".join(difflib.unified_diff(before.decode("utf-8").splitlines(keepends=True),
                after.decode("utf-8").splitlines(keepends=True), fromfile="a/" + base, tofile="b/" + derived))
            name = f"derivation_{index:02d}_{Path(derived).name}.diff"
            destination = evidence.parent / name
            if destination.exists():
                raise ValueError("Preserve earlier diff: " + name)
            destination.write_bytes(patch.encode("utf-8"))
            records.append({"base": base, "file": derived, "base_info": info(before),
                            "derived_info": info(after), "diff": name, "diff_info": info(destination.read_bytes())})
        evidence.write_text(json.dumps({"base_commit": BASE_COMMIT, "pairs": records}, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
        print("A4_DERIVATION_DIFFS_CAPTURED", len(records))
        return
    if args.output is None or args.output.exists():
        raise ValueError("Specify a new verification output")
    metadata = json.loads(evidence.read_text(encoding="utf-8"))
    if metadata["base_commit"] != BASE_COMMIT or [(r["base"], r["file"]) for r in metadata["pairs"]] != PAIRS:
        raise ValueError("Wrong derivation specification")
    checks = []
    for record in metadata["pairs"]:
        before, after = (ROOT / record["base"]).read_bytes(), (ROOT / record["file"]).read_bytes()
        patch = (evidence.parent / record["diff"]).read_bytes()
        pinned = subprocess.check_output(["git", "show", BASE_COMMIT + ":" + record["base"]], cwd=ROOT)
        if before != pinned or info(before) != record["base_info"] or info(after) != record["derived_info"] or info(patch) != record["diff_info"]:
            raise ValueError("Changed derivation bytes: " + record["file"])
        reproduced = apply_unified(before.decode("utf-8"), patch.decode("utf-8")).encode("utf-8")
        if reproduced != after:
            raise ValueError("Derivation does not reproduce exact bytes: " + record["file"])
        checks.append({"file": record["file"], **info(after), "base_unchanged": True, "diff_reproduces_exact_bytes": True})
    args.output.write_text(json.dumps({"status": "PASS_A4_DERIVATION_REPRODUCTION", "base_commit": BASE_COMMIT,
                           "checks": checks}, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("A4_DERIVATION_REPRODUCTION_PASS", len(checks), "files")


if __name__ == "__main__":
    main()
