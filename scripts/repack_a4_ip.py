"""Fix only the known 2017.4 generated IP date-revision overflow."""
import argparse
import difflib
import hashlib
import json
import re
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("hls_build", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    original = args.hls_build / "solution1/impl/ip/run_ippack.tcl"
    before = original.read_text(encoding="utf-8")
    after, count = re.subn(r'^set Revision\s+"\d+"', 'set Revision "1"', before, flags=re.M)
    patched = original.with_name("run_ippack_a4meta.tcl")
    if count != 1 or before == after or patched.exists():
        raise ValueError("Unexpected or already patched generated date revision")
    for name in (original.name, patched.name, "packaging_revision.patch", "packaging_metadata_fix.json"):
        if (args.evidence / name).exists():
            raise ValueError("Preserve earlier packaging evidence: " + name)
    patched.write_text(after, encoding="utf-8", newline="\n")
    for source in (original, patched):
        shutil.copyfile(source, args.evidence / source.name)
    (args.evidence / "packaging_revision.patch").write_text("".join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), fromfile=original.name, tofile=patched.name)),
        encoding="utf-8", newline="\n")
    (args.evidence / "packaging_metadata_fix.json").write_text(json.dumps({
        "status": "GENERATED_DATE_REVISION_ONLY_PATCH_PREPARED_NOT_EXPORT_PASS",
        "original_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
        "patched_sha256": hashlib.sha256(patched.read_bytes()).hexdigest(),
        "scope": "One generated Revision string set to 1. Installed libraries, HDL and interface mappings unchanged. Run patched Tcl from actual impl/ip directory and verify its log."}, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print("A4_GENERATED_DATE_METADATA_ONLY_PATCH", patched)


if __name__ == "__main__":
    main()
