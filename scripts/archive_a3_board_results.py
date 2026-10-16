"""Check downloaded A3 evidence against the release and independent M0 model.

Never run notebook code or extract arbitrary ZIP paths. Keep raw retinal images
in the ignored local archive; track the original JSON and verification metadata.
"""
import argparse
import base64
import hashlib
import io
import json
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from software.reference import LUT, box_mean15, gaussian3
from a1_point_board_test import notebook_code_hash
from a3_background_board_test import validate_a3_package

STATUS = "A3_PASS_45_BACKGROUND_FRAMES_NOT_FULL_SEGMENTATION"
RELEASE = ROOT / "results/a3_background_2017_4/release_manifest.json"
SOURCE_COMMIT = "3d203d55e09d483dcb2638e53fa869f89c206d7e"
ARRAY_NAMES = {f"a3_output_stare_{side}_mode{mode}.npy"
               for side in (256, 512) for mode in (2, 3)}
BUNDLE_NAMES = ARRAY_NAMES | {"a3_background_result.json", "a3_preview.png"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def word_digest(words):
    return digest(words.astype("<u4", copy=False).tobytes())


def read_bundle(path):
    require(path.stat().st_size <= 8_000_000, "Result ZIP is unexpectedly large")
    with ZipFile(path) as archive:
        entries = archive.infolist()
        require(len(entries) == len(BUNDLE_NAMES) and
                {item.filename for item in entries} == BUNDLE_NAMES,
                "Missing, duplicate or unexpected ZIP member")
        require(sum(item.file_size for item in entries) <= 4_000_000,
                "Uncompressed ZIP exceeds the A3 evidence limit")
        for item in entries:
            require(not item.is_dir() and not item.flag_bits & 1 and
                    stat.S_IFMT(item.external_attr >> 16) != stat.S_IFLNK and
                    item.compress_type in (ZIP_STORED, ZIP_DEFLATED),
                    "Unsupported ZIP member: " + item.filename)
            limit = 1_100_000 if item.filename in ARRAY_NAMES else 500_000
            require(0 < item.file_size <= limit, "Unexpected member size: " + item.filename)
        # Fixed flat names only; ZipFile.read also validates each member CRC.
        return {item.filename: archive.read(item) for item in entries}


def recorded_cases():
    return ([(256, 3, "vessel_stripes")]
            + [(side, mode, pattern) for side in (256, 512) for mode in range(4)
               for pattern in ("gradient", "random")]
            + [(side, mode, pattern) for side in (256, 512) for mode in (2, 3)
               for pattern in ("checker", "impulse", "black", "white", "stare")]
            + [(side, mode, pattern) for side in (256, 512) for mode in (2, 3)
               for pattern in ("vessel_stripes", "rounding")])


def regenerate_input(side, pattern, index, package):
    if pattern == "stare":
        source = np.load(package / f"stare_im0001_{side}.npy", allow_pickle=False)
        require(source.dtype == np.dtype("<u4") and source.shape == (side, side) and
                np.all((source >> 24) <= 1), "Invalid released RGB/FOV input")
        return source
    # Regenerate the input contract without invoking the board runner.
    y, x = np.indices((side, side), dtype=np.uint32)
    if pattern == "gradient":
        green = (11 * x + 17 * y) % 256
    elif pattern == "random":
        green = np.random.default_rng(20261012 + index).integers(0, 256, (side, side), dtype=np.uint32)
    elif pattern == "checker":
        green = ((x + y) % 2) * 255
    elif pattern == "impulse":
        green = np.zeros((side, side), dtype=np.uint32)
        positions = [0, side // 2, side - 1]
        green[np.ix_(positions, positions)] = 255
    elif pattern == "vessel_stripes":
        green = np.where((x % 31 < 5) | (y % 43 < 3), 12, 190).astype(np.uint32)
    elif pattern == "rounding":
        green = (x * 13 + y * 7 + 9) % 80
    else:
        require(pattern in ("black", "white"), "Unknown input pattern")
        green = np.full((side, side), 255 if pattern == "white" else 0, dtype=np.uint32)
    position = y * side + x
    return (((x + y) % 2) << 24) | (((position * 7) % 256) << 16) | (green << 8) | ((position * 13) % 256)


def independent_expected(source, mode):
    if mode == 0:
        return source.copy()
    green = ((source >> 8) & 255).astype(np.uint8)
    # M0 uses int32 nine-tap Gaussian and int64 integral box sums independently
    # of the board runner's separable Gaussian and vendor HLS stream filters.
    enhanced = LUT[gaussian3(green)]
    words = green.astype(np.uint32) | (enhanced.astype(np.uint32) << 8)
    if mode == 1:
        return words | (source & np.uint32(0xff000000))
    require(mode in (2, 3), "Unknown diagnostic mode")
    background = box_mean15(enhanced)
    words |= background.astype(np.uint32) << 16
    if mode == 2:
        return words | (source & np.uint32(0xff000000))
    response = np.clip((background.astype(np.int16) - enhanced.astype(np.int16)) * 4, 0, 255)
    return words | (response.astype(np.uint32) << 24)


def verify_notebook(notebook, report, manifest):
    contract = manifest["notebook_validation"]
    require(notebook_code_hash(notebook) == contract["sha256"], "Executed notebook code changed")
    cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    require([cell["execution_count"] for cell in cells] == list(range(1, 7)), "Unexpected execution sequence")
    require(all(out["output_type"] != "error" for cell in cells for out in cell["outputs"]),
            "Notebook contains an error output")
    streams = ["".join("".join(out.get("text", [])) for out in cell["outputs"]
                       if out["output_type"] == "stream") for cell in cells]
    markers = ["A3_PRECHECK_PASS: hashes/metadata; FPGA unchanged",
               "A3_LOAD_PASS: official drivers and reset state checked",
               "A3_SMOKE_PASS: full 256x256 background/response frame matched",
               "A3 BACKGROUND PASS: 45 complete frames matched; no full segmentation/HDMI/FPS PASS",
               "A3_RESULTS_READY: download a3_results_bundle.zip and executed notebook"]
    for index, marker in enumerate(markers, start=1):
        require(streams[index].count(marker) == 1 and "".join(streams).count(marker) == 1,
                "Missing, duplicate or misplaced completion marker: " + marker)
    expected_lines = [f"BACKGROUND_FRAME_PASS: {index + 1}/45 {side} mode {mode} {pattern}"
                      for index, (side, mode, pattern) in enumerate(recorded_cases())]
    actual_lines = [line.strip() for stream in streams for line in stream.splitlines()
                    if line.startswith("BACKGROUND_FRAME_PASS:")]
    require(actual_lines == expected_lines, "Notebook frame lines differ from the 45-case contract")
    require(expected_lines[0] in streams[3] and all(line in streams[4] for line in expected_lines[1:]),
            "Frame results appear in the wrong notebook phase")
    validation = report["package_validation"]
    require(validation["fixed_artifacts"] == "PASS_EXACT_SHA256" and
            validation["notebook_code"] == "PASS_CANONICAL_CODE_SHA256" and
            validation["notebook_code_sha256"] == contract["sha256"] and
            validation["original_notebook_sha256"] == manifest["artifacts"]["a3_background_check.ipynb"]["sha256"] and
            re.fullmatch(r"[0-9a-f]{64}", validation["current_notebook_sha256"]) is not None,
            "Board package precheck did not pass")
    return cells


def verify_records(notebook, report, manifest, package, members):
    require(report["manifest"] == manifest, "Result belongs to a different release")
    require(report["status"] == STATUS and "error" not in report and "active_case" not in report,
            "Suite is incomplete or failed")
    require((report["pynq"], report["python"], report["kernel"]) ==
            ("3.0.1", "3.10.4", "5.15.19-xilinx-v2022.1"), "Unexpected board runtime")
    require(report["drivers"] == {"dma": "pynq.lib.dma.DMA", "gpio": "pynq.lib.axigpio.AxiGPIO"},
            "Official DMA/GPIO drivers did not bind")
    cells = verify_notebook(notebook, report, manifest)
    cases = recorded_cases()
    require(len(report["transfers"]) == len(cases) == 45, "Incomplete frame records")
    verified, arrays, output_arrays = [], [], {}
    for index, ((side, mode, pattern), record) in enumerate(zip(cases, report["transfers"])):
        require((record["side"], record["mode"], record["pattern"]) == (side, mode, pattern), "Unexpected frame order")
        count, nbytes = side * side, side * side * 4
        require(record["status"] == "PASS_EXACT_BACKGROUND_WORDS" and
                (record["words"], record["send_bytes"], record["recv_bytes"]) == (count, nbytes, nbytes),
                "Frame comparison or byte count failed")
        require(set(record["dma_status"]) == {"mm2s", "s2mm"} and
                all(value & 2 and not value & 0x771 for value in record["dma_status"].values()),
                "DMA halted, busy or has an error")
        addresses = [record["tx_address"], record["rx_address"]]
        require(all(addr % 8 == 0 and 0x100000 <= addr <= 0x20000000 - nbytes for addr in addresses) and
                abs(addresses[0] - addresses[1]) >= nbytes, "Invalid or overlapping DDR buffers")
        require(record["frame_status"] == ((index + 1) << 14) | (index + 1),
                "FPGA input/output counters or error flags differ")
        source = regenerate_input(side, pattern, index, package)
        expected = independent_expected(source, mode)
        input_hash, expected_hash = word_digest(source), word_digest(expected)
        require(record["input_sha256"] == input_hash and
                record["expected_sha256"] == record["output_sha256"] == expected_hash,
                f"Independent input/golden/output hash mismatch at frame {index + 1}")
        verified.append({"frame": index + 1, "side": side, "mode": mode, "pattern": pattern,
                         "words": count, "input_sha256": input_hash, "expected_output_sha256": expected_hash,
                         "frame_status": record["frame_status"], "status": "PASS_INDEPENDENT_RECOMPUTE"})
        if pattern != "stare":
            require("saved_output" not in record, "Unexpected saved output entry")
            continue
        name = f"a3_output_stare_{side}_mode{mode}.npy"
        require(record["saved_output"] == {"name": name, "sha256": digest(members[name])},
                "Raw output file SHA256 mismatch: " + name)
        raw = np.load(io.BytesIO(members[name]), allow_pickle=False)
        require(raw.dtype == np.dtype("<u4") and raw.shape == (side, side), "Wrong raw array type or shape")
        require(np.array_equal(raw, expected) and word_digest(raw) == record["output_sha256"],
                "Downloaded FPGA array differs from the M0 golden model: " + name)
        arrays.append({"name": name, "shape": list(raw.shape), "dtype": str(raw.dtype), "words": count,
                       "file_sha256": digest(members[name]), "word_sha256": word_digest(raw),
                       "mismatched_words": 0, "status": "PASS_EVERY_RAW_WORD"})
        output_arrays[(side, mode)] = raw
    require({item["name"] for item in arrays} == ARRAY_NAMES, "Missing one of four raw outputs")
    preview = verify_preview(cells, report, package, members, output_arrays)
    return {"frames": verified, "raw_arrays": arrays, "preview": preview}


def decoded_png(data):
    with Image.open(io.BytesIO(data)) as image:
        require(image.format == "PNG" and image.size == (1024, 280) and image.mode == "RGB",
                "Unexpected result preview format")
        return np.asarray(image).copy()


def verify_preview(cells, report, package, members, output_arrays):
    data = members["a3_preview.png"]
    require(report["preview"] == {"file": "a3_preview.png", "sha256": digest(data)}, "Preview file hash differs")
    pixels = decoded_png(data)
    # The four panes are the actual mode-3 DMA bytes: raw G, enhancement,
    # 15x15 background and response; the last byte is not the FOV bit.
    words = output_arrays[(512, 3)]
    for index, shift in enumerate((0, 8, 16, 24)):
        channel = ((words >> shift) & 255).astype(np.uint8)
        pane = np.asarray(Image.fromarray(channel).resize((256, 256), Image.Resampling.BICUBIC))
        require(np.array_equal(pixels[24:, index * 256:(index + 1) * 256], np.repeat(pane[:, :, None], 3, axis=2)),
                "Preview pane differs from the FPGA diagnostic byte")
    embedded = [out["data"]["image/png"] for out in cells[5]["outputs"]
                if out["output_type"] == "display_data" and "image/png" in out.get("data", {})]
    require(len(embedded) == 1, "Notebook is missing its unique FPGA result preview")
    # Jupyter wraps base64 text with whitespace; this is not a code/file change.
    encoded = "".join("".join(embedded[0]).split())
    require(np.array_equal(decoded_png(base64.b64decode(encoded, validate=True)), pixels),
            "Notebook preview differs from the archived result PNG")
    return {"status": "PASS_ARRAY_PANES_AND_NOTEBOOK_PIXELS", "sha256": digest(data),
            "size": [1024, 280], "panes": 4, "pane_resampling": "BICUBIC",
            "limits": "Numerical checks use full uint32 arrays, not this resized preview."}


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("notebook", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--raw-destination", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    require(not args.destination.exists() and not args.raw_destination.exists(), "Refusing to overwrite an archive")
    manifest_data = (args.package / "a3_manifest.json").read_bytes()
    require(manifest_data == RELEASE.read_bytes(), "Package differs from the archived release")
    manifest = json.loads(manifest_data)
    validate_a3_package(args.package, manifest)
    require(args.notebook.stat().st_size <= 4_000_000, "Notebook exceeds the A3 evidence limit")
    notebook_data = args.notebook.read_bytes()
    members = read_bundle(args.bundle)
    report = json.loads(members["a3_background_result.json"])
    checks = verify_records(json.loads(notebook_data), report, manifest, args.package, members)
    bundle_data = args.bundle.read_bytes()
    require(read_bundle(args.bundle) == members and bundle_data == args.bundle.read_bytes(),
            "Downloaded ZIP changed during verification")
    # All validation precedes writes. Raw downloaded bytes are preserved unchanged.
    args.raw_destination.mkdir(parents=True)
    args.destination.mkdir(parents=True)
    raw_files = {"a3_background_check_executed.ipynb": notebook_data, "a3_results_bundle.zip": bundle_data, **members}
    if args.screenshot:
        raw_files["user_result_screenshot.png"] = args.screenshot.read_bytes()
    file_records = {}
    for name, data in raw_files.items():
        target = args.raw_destination / name
        target.write_bytes(data)
        require(target.read_bytes() == data, "Raw archive byte mismatch: " + name)
        file_records[name] = {"path": str(target.resolve()), "bytes": len(data), "sha256": digest(data)}
    target = args.destination / "a3_background_result.json"
    target.write_bytes(members["a3_background_result.json"])
    require(target.read_bytes() == members["a3_background_result.json"], "Original JSON bytes changed")
    write_json(args.destination / "independent_frame_verification.json", checks["frames"])
    write_json(args.destination / "raw_array_verification.json", checks["raw_arrays"])
    write_json(args.destination / "preview_verification.json", checks["preview"])
    summary = {"status": "PASS_BOARD_RECORDS_AND_RAW_ARRAYS_VERIFIED_AND_ARCHIVED",
               "verified_host_utc": datetime.now(timezone.utc).isoformat(), "revision": manifest["revision"],
               "hardware_source_commit": SOURCE_COMMIT, "release_manifest_sha256": digest(manifest_data),
               "board_clock_utc_unverified": report["board_clock_utc_unverified"], "frames_verified": 45,
               "input_words_verified": sum(item["words"] for item in checks["frames"]),
               "raw_output_words_verified": sum(item["words"] for item in checks["raw_arrays"]),
               "notebook_code_sha256": notebook_code_hash(json.loads(notebook_data)),
               "source_paths": {"notebook": str(args.notebook.resolve()), "bundle": str(args.bundle.resolve())},
               "raw_files": file_records,
               "local_archive_policy": "Retinal arrays, PNG and output-bearing Notebook stay in ignored build/board_results. Original JSON and hashes are tracked; no dataset redistribution.",
               "scope": "Actual PYNQ-Z2 A3: 45 bypass/enhanced/background/response frames, standard DMA/GPIO/DDR, original G and center FOV alignment in modes 0-2.",
               "limits": "All 45 board output hashes recomputed independently; all 4 saved STARE buffers compared word by word on the host. Other 41 raw buffers are not downloaded. No full vessel segmentation, final HDMI integration, FPS or clinical validation."}
    write_json(args.destination / "archive_manifest.json", summary)
    print("A3_PASS_BOARD_RECORDS_AND_RAW_ARRAYS_VERIFIED_AND_ARCHIVED: 45 frames, 7274496 words; 4 raw arrays, 655360 words")


if __name__ == "__main__":
    main()
