"""2017.4 date revision overflow: modify only a generated packaging Tcl copy."""
import argparse
import difflib
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("hls_build", type=Path)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    original = args.hls_build / "solution1/impl/ip/run_ippack.tcl"
    before = original.read_text()
    after, count = re.subn(r'^set Revision\s+"\d+"', 'set Revision "1"', before, flags=re.M)
    if count != 1 or before == after:
        raise ValueError("Unexpected packaging source; no patch applied")
    patched = original.with_name("run_ippack_r2meta.tcl")
    if patched.exists():
        raise ValueError("Refusing to overwrite patch history")
    patched.write_text(after, encoding="utf-8")
    shutil.copyfile(original, args.evidence / "run_ippack_original.tcl")
    shutil.copyfile(patched, args.evidence / patched.name)
    (args.evidence / "packaging_revision.patch").write_text("".join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), fromfile=original.name, tofile=patched.name)), encoding="utf-8")
    install = Path("E:/vivado/Vivado/2017.4/include")
    sources = [install / name for name in ("hls_video.h", "hls/hls_video_imgproc.h", "hls/hls_video_types.h", "hls/hls_video_mem.h")]
    report = {"installed_vivado_hls": "2017.4", "vendor_headers_not_redistributed": True,
              "headers": [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in sources],
              "reuse": "Unmodified hls::Filter2D<BORDER_REPLICATE>, hls::Mat, LineBuffer and AXIS interface generation",
              "kernel": "Integer [1 2 1; 2 4 2; 1 2 1], uint16 full sum then (sum+8)>>4",
              "xfopencv_not_selected": "Pinned Gaussian computes sigma-based quantized weights; not this exact fixed kernel",
              "patch_scope": "One generated packaging Revision string changed to 1; installed library/RTL/clock/data path unchanged"}
    (args.evidence / "reuse_evidence.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("A2_GENERATED_METADATA_ONLY_PATCH", patched)


if __name__ == "__main__":
    main()
