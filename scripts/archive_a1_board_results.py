"""Verify actual A1 records and deterministic frame hashes before archiving."""
import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from a1_point_board_test import notebook_code_hash, validate_package

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_records(notebook, report, manifest):
    require(report["manifest"] == manifest, "Result belongs to a different release")
    require(report["status"] == "A1_PASS_17_POINT_FRAMES_NOT_FULL_MEDICAL_ALGORITHM", "Suite did not complete")
    require(report["pynq"] == "3.0.1", "Unexpected PYNQ runtime")
    require("active_case" not in report and "error" not in report, "Unfinished or failed case remains")
    contract = manifest["notebook_validation"]
    require(notebook_code_hash(notebook) == contract["sha256"], "Executed notebook code changed")
    codes = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    require([cell["execution_count"] for cell in codes] == [1, 2, 3, 4, 5], "Unexpected execution sequence")
    require(all(output["output_type"] != "error" for cell in codes for output in cell["outputs"]), "Notebook contains errors")
    text = "".join("".join(output.get("text", [])) for cell in codes for output in cell["outputs"]
                   if output["output_type"] == "stream")
    for marker in ("A1_PRECHECK_PASS:", "A1_LOAD_PASS:", "A1_SMOKE_PASS:",
                   "A1 POINT PASS: 17 complete frames matched; no segmentation/HDMI PASS"):
        require(text.count(marker) == 1, "Missing or duplicate completion marker: " + marker)
    validation = report["package_validation"]
    require(validation["fixed_artifacts"] == "PASS_EXACT_SHA256" and
            validation["notebook_code"] == "PASS_CANONICAL_CODE_SHA256" and
            validation["notebook_code_sha256"] == contract["sha256"] and
            validation["original_notebook_sha256"] == manifest["artifacts"]["a1_point_check.ipynb"]["sha256"],
            "Board package precheck did not pass")
    require(re.fullmatch(r"[0-9a-f]{64}", validation["current_notebook_sha256"]) is not None,
            "Invalid raw notebook hash recorded at board precheck")
    cases = [(256, 1, "ramp")]
    cases += [(side, mode, pattern) for side in (256, 512) for mode in (0, 1, 2)
              for pattern in ("ramp", "random")]
    cases += [(side, 2, pattern) for side in (256, 512) for pattern in ("black", "white")]
    require(len(report["transfers"]) == len(cases) == 17, "Incomplete frame records")
    expected_lines = []
    # Independent LUT array, without using the runner's point_expected function.
    lut = np.array([min(255, (value * 255 + 96) // 192) for value in range(256)], dtype=np.uint32)
    verified = []
    for index, ((side, mode, pattern), record) in enumerate(zip(cases, report["transfers"])):
        require((record["side"], record["mode"], record["pattern"]) == (side, mode, pattern), "Unexpected frame order")
        count, nbytes = side * side, side * side * 4
        require(record["status"] == "PASS_EXACT_POINT_STAGE_WORDS", "Frame did not pass")
        require((record["words"], record["send_bytes"], record["recv_bytes"]) == (count, nbytes, nbytes), "Frame length mismatch")
        require(set(record["dma_status"]) == {"mm2s", "s2mm"}, "Missing DMA status")
        require(all(value & 2 and not value & 0x771 for value in record["dma_status"].values()), "DMA halted, busy or has errors")
        addresses = [record["tx_address"], record["rx_address"]]
        require(all(addr % 8 == 0 and addr >= 0x100000 and addr + nbytes <= 0x20000000 for addr in addresses), "Invalid DDR buffer")
        require(abs(addresses[0] - addresses[1]) >= nbytes, "TX/RX buffers overlap")
        require(record["frame_status"] == ((index + 1) << 14) | (index + 1), "FPGA frame counts or error flags differ")
        if pattern == "random":
            rng = np.random.default_rng(20261011 + index)
            source = rng.integers(0, 1 << 24, count, dtype=np.uint32)
            source |= rng.integers(0, 2, count, dtype=np.uint32) << 24
        elif pattern == "ramp":
            position = np.arange(count, dtype=np.uint32)
            source = ((position & 1) << 24) | (((position * 11) & 255) << 16) | ((position & 255) << 8) | ((position * 7) & 255)
        else:
            source = np.full(count, 0x01000000 if pattern == "black" else 0x01FFFFFF, dtype=np.uint32)
        if mode == 0:
            expected = source
        else:
            green = (source >> 8) & 255
            upper = green if mode == 1 else lut[green]
            expected = green | (upper << 8)
        input_hash = hashlib.sha256(source.astype("<u4", copy=False).tobytes()).hexdigest()
        expected_hash = hashlib.sha256(expected.astype("<u4", copy=False).tobytes()).hexdigest()
        require(record["input_sha256"] == input_hash and record["expected_sha256"] == record["output_sha256"] == expected_hash,
                "Frame hashes differ from independently regenerated input/golden data")
        expected_lines.append(f"POINT_FRAME_PASS: {side} mode {mode} {pattern}")
        verified.append({"index": index, "side": side, "mode": mode, "pattern": pattern,
                         "input_sha256": input_hash, "expected_output_sha256": expected_hash,
                         "status": "PASS_INDEPENDENT_RECOMPUTE"})
    require([line.strip() for line in text.splitlines() if line.startswith("POINT_FRAME_PASS:")] == expected_lines,
            "Notebook frame completion lines differ from JSON")
    return verified


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("notebook", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    require(not args.destination.exists(), "Refusing to overwrite an archive")
    manifest_path = args.package / "a1_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_package(args.package, manifest)
    archived_release = ROOT / "results/a1_point_2017_4_r2/release_manifest.json"
    require(manifest_path.read_bytes() == archived_release.read_bytes(), "Package differs from archived r2 release")
    report = json.loads(args.result.read_text(encoding="utf-8"))
    notebook = json.loads(args.notebook.read_text(encoding="utf-8"))
    verified = verify_records(notebook, report, manifest)
    args.destination.mkdir(parents=True)
    files = {}
    for source, name in ((args.notebook, "a1_point_check_executed.ipynb"), (args.result, "a1_point_result.json")):
        target = args.destination / name
        shutil.copy2(source, target)
        require(target.read_bytes() == source.read_bytes(), "Archive byte mismatch")
        files[name] = {"source_path": str(source.resolve()), "bytes": target.stat().st_size, "sha256": digest(target)}
    summary = {"status": "PASS_BOARD_RECORDS_VERIFIED_AND_ARCHIVED", "verified_host_utc": datetime.now(timezone.utc).isoformat(),
               "files": files, "revision": manifest["revision"], "release_manifest_sha256": digest(manifest_path),
               "hardware_source_commit": "1d206a483e75c2b425e790d6718f6fe52892dd09",
               "runner_fix_source_commit": "2c845bfe16096ee346dd7555cdf1c70cabf3bd2e",
               "board_clock_utc_unverified": report["board_clock_utc_unverified"], "frames_verified": 17,
               "input_words_verified": sum(item["words"] for item in report["transfers"]),
               "scope": "A1 point-stage only: bypass/green/direct LUT(G), standard DMA/GPIO/DDR and PYNQ 3.0.1",
               "limits": "Board runner performed full word comparisons; host checks deterministic hashes and metadata, not raw output buffers. No Gaussian, segmentation, final HDMI integration, FPS or clinical proof."}
    for name, payload in (("archive_manifest.json", summary), ("independent_frame_verification.json", verified)):
        (args.destination / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("A1_PASS_BOARD_RECORDS_VERIFIED_AND_ARCHIVED: 17 frames, independent input/golden/output hashes")


if __name__ == "__main__":
    main()
