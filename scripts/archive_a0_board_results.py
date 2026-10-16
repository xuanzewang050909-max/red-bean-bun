"""Validate real A0 execution records and archive originals without editing them."""
import argparse
import hashlib
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_transfers(report, cases):
    require(report["status"] == "PASS_ALL_EXACT_WORD_COMPARE", "Suite did not pass")
    require(report["expected_transfers"] == len(cases), "Wrong expected count")
    require(len(report["transfers"]) == len(cases), "Incomplete transfer records")
    rng = np.random.default_rng(20261011)
    for index, ((words, pattern), result) in enumerate(zip(cases, report["transfers"])):
        require((result["index"], result["words"], result["pattern"]) ==
                (index, words, pattern), "Unexpected test case/order")
        require(result["status"] == "PASS_EXACT_WORD_COMPARE", "Failed word compare")
        nbytes = words * 4
        require(all(result[key] == nbytes for key in ("bytes", "send_bytes", "recv_bytes")),
                "Transfer byte count mismatch")
        for status in result["dma_status"].values():
            require(status & 2 and not status & 0x71, "DMA not idle/running or has errors")
        require(set(result["dma_status"]) == {"mm2s", "s2mm"}, "Missing DMA channel")
        addresses = [result[key] for key in ("send_physical_address", "recv_physical_address")]
        require(all(addr % 8 == 0 and 0x100000 <= addr and addr + nbytes <= 0x20000000
                    for addr in addresses), "Misaligned/out-of-range DDR buffer")
        require(abs(addresses[0] - addresses[1]) >= nbytes, "TX/RX buffers overlap")
        require(math.isfinite(result["elapsed_seconds"]) and result["elapsed_seconds"] >= 0,
                "Invalid recorded elapsed time")
        if pattern == "random":
            expected = rng.integers(0, 1 << 32, size=words, dtype=np.uint32)
        else:
            expected = np.arange(words, dtype=np.uint32) ^ np.uint32(index * 0x01010101)
        expected_hash = hashlib.sha256(expected.astype("<u4", copy=False).tobytes()).hexdigest()
        require(result["input_sha256"] == result["output_sha256"] == expected_hash,
                "Recorded hashes differ from independently regenerated test pattern")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("notebook", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    require(not args.destination.exists(), "Refusing to overwrite an archive")
    report = json.loads(args.result.read_text(encoding="utf-8"))
    manifest = json.loads((args.package / "a0_manifest.json").read_text(encoding="utf-8"))
    require(report["manifest"] == manifest, "Result belongs to a different release")
    require(report["pynq"] == "3.0.1", "Unexpected PYNQ runtime")
    require(report["dma_description"]["driver"] == "pynq.lib.dma.DMA", "Unofficial DMA driver")
    require(report["dma_description"]["phys_addr"] == 0x40400000, "Wrong DMA address")
    for name, info in manifest["artifacts"].items():
        require(digest(args.package / name) == info["sha256"], "Changed deployment artifact")
    template = args.package / "a0_dma_loopback.ipynb"
    require(digest(template) == manifest["notebook"]["sha256"], "Changed deployment notebook")
    executed = json.loads(args.notebook.read_text(encoding="utf-8"))
    codes = [cell for cell in executed["cells"] if cell["cell_type"] == "code"]
    original = [cell for cell in json.loads(template.read_text(encoding="utf-8"))["cells"]
                if cell["cell_type"] == "code"]
    require(len(codes) == len(original) == 5, "Unexpected notebook layout")
    require([cell["execution_count"] for cell in codes] == [1, 2, 3, 4, 5],
            "Unexpected execution sequence")
    for actual, reference in zip(codes, original):
        require("".join(actual["source"]) == "".join(reference["source"]), "Test code changed")
        require(all(output["output_type"] != "error" for output in actual["outputs"]),
                "Notebook contains an exception")
    text = "".join("".join(output.get("text", [])) for cell in codes
                   for output in cell["outputs"] if output["output_type"] == "stream")
    for marker in ("PRECHECK_PASS:", "LOAD_PASS:", "SMOKE_PASS:",
                   "A0 DMA PASS: all 70 transfers matched."):
        require(marker in text, "Missing completion marker: " + marker)
    cases = [(n, p) for n in (1, 3, 17, 1023, 1024) for p in ("increment", "random")]
    cases += [(side * side, p) for side in (256, 512)
              for p in ("increment", "random") for _ in range(15)]
    verify_transfers(report, cases)
    verify_transfers(report["smoke"], [(17, "increment")])
    for index, (words, pattern) in enumerate(cases):
        require(f"PASS {index + 1}/70: {words} words, {pattern}" in text,
                "Missing per-transfer notebook output")
    args.destination.mkdir(parents=True)
    files = {}
    for source, name in ((args.notebook, "a0_dma_loopback_executed.ipynb"),
                         (args.result, "a0_dma_result.json")):
        target = args.destination / name
        shutil.copy2(source, target)
        require(target.read_bytes() == source.read_bytes(), "Archive byte mismatch")
        files[name] = {"source_path": str(source.resolve()), "bytes": target.stat().st_size,
                       "sha256": digest(target)}
    summary = {"status": "PASS_BOARD_RECORDS_VERIFIED_AND_ARCHIVED",
               "verified_host_utc": datetime.now(timezone.utc).isoformat(), "files": files,
               "source_commit": manifest["source_commit"], "revision": manifest["revision"],
               "full_transfers": 70, "smoke_transfers": 1, "patterns_recomputed": 71,
               "board_clock_utc_unverified": report["board_clock_utc_unverified"],
               "scope": "A0 r2 DMA/FIFO/DDR exact loopback and official PYNQ 3.0.1 driver only",
               "limits": "Recorded hashes independently checked; raw output buffers were not downloaded. No medical algorithm, final HDMI overlay or real-time FPS proof."}
    (args.destination / "archive_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PASS_BOARD_RECORDS_VERIFIED_AND_ARCHIVED: 70 full transfers + 1 smoke; 71 pattern hashes")


if __name__ == "__main__":
    main()
