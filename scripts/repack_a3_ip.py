"""Reuse the A2 date-metadata workaround on A3 generated packaging Tcl only."""
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
    patched = original.with_name("run_ippack_a3meta.tcl")
    if count != 1 or before == after or patched.exists():
        raise ValueError("Unexpected or previously patched packaging metadata")
    patched.write_text(after, encoding="utf-8", newline="\n")
    for source in (original, patched):
        target = args.evidence / source.name
        if target.exists():
            raise ValueError("Preserve earlier packaging evidence")
        shutil.copyfile(source, target)
    (args.evidence / "packaging_revision.patch").write_text("".join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), fromfile=original.name, tofile=patched.name)),
        encoding="utf-8", newline="\n")
    headers = []
    for base in ("include", "common/technology/autopilot"):
        for name in ("hls_video.h", "hls/hls_video_imgproc.h", "hls/hls_video_mem.h", "hls/hls_video_types.h"):
            path = Path("E:/vivado/Vivado/2017.4") / base / name
            headers.append({"path": str(path), "bytes": path.stat().st_size,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    evidence = {"installed_vivado_hls": "2017.4", "vendor_headers_not_redistributed": True,
                "headers": headers, "library_modified": False,
                "reuse": "Unmodified Filter2D and BoxFilter<15,15,false,BORDER_REPLICATE>, SepFilter2D, Mat/LineBuffer/Window and AXIS generation",
                "numeric_scope": "A2 Gaussian/LUT retained; uint16 225-sample box sum then (sum+112)//225; signed saturated 4*(background-enhanced)",
                "patch_scope": "Only one generated Revision string changed to 1; installed library/RTL/clock/PS/DMA unchanged"}
    (args.evidence / "reuse_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("A3_GENERATED_METADATA_ONLY_PATCH", patched)


if __name__ == "__main__":
    main()
