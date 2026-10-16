"""M0 independent background/response vectors, RGB/FOV only, no GT input."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from software.preprocessing import read_archive, prepare_sample, pack_input
from software.reference import gaussian3, LUT, box_mean15
from a2_gaussian_board_test import make_pattern

CASES = [(256, 0, "gradient"), (256, 1, "random"), (256, 2, "gradient"),
         (512, 3, "random"), (256, 2, "impulse"), (256, 3, "checker"),
         (256, 2, "white"), (256, 3, "black"), (512, 3, "vessel_stripes"),
         (256, 2, "stare"), (512, 3, "stare"), (256, 3, "impulse"),
         (256, 3, "random"), (256, 3, "black")]


def diagnostic_pattern(side, pattern, index, directory=None):
    if pattern not in ("vessel_stripes", "rounding"):
        return make_pattern(side, pattern, index, directory)
    y, x = np.indices((side, side), dtype=np.uint32)
    green = np.where((x % 31 < 5) | (y % 43 < 3), 12, 190).astype(np.uint32) if pattern == "vessel_stripes" else (x * 13 + y * 7 + 9) % 80
    position = y * side + x
    return (((x + y) & 1) << 24) | (((position * 7) & 255) << 16) | (green << 8) | ((position * 13) & 255)


def expected_words(source, mode):
    if mode == 0:
        return source.copy()
    raw = ((source >> 8) & 255).astype(np.uint8)
    enhanced = LUT[gaussian3(raw)]
    background = box_mean15(enhanced)
    response = np.clip((background.astype(np.int16) - enhanced.astype(np.int16)) * 4, 0, 255).astype(np.uint8)
    return (raw.astype(np.uint32) | (enhanced.astype(np.uint32) << 8)
            | (np.uint32(0) if mode == 1 else background.astype(np.uint32) << 16)
            | (response.astype(np.uint32) << 24 if mode == 3 else source & np.uint32(0xff000000)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    if (args.destination / "vector_manifest.json").exists():
        raise ValueError("Preserve earlier vector evidence")
    rgb = read_archive(ROOT / "data/raw/stare/stare-images.tar", "")["im0001"]
    geometry = {}
    for side in (256, 512):
        prepared, aligned, geometry[side] = prepare_sample(rgb["pixels"], {}, side)
        np.save(args.destination / f"stare_im0001_{side}.npy", pack_input(prepared, aligned["fov"]))
    records = []
    for index, (side, mode, pattern) in enumerate(CASES, start=1):
        source = diagnostic_pattern(side, pattern, index, args.destination)
        expected = expected_words(source, mode)
        np.savetxt(args.destination / f"case_{index:02d}_input.hex", source.reshape(-1), fmt="%08x")
        np.savetxt(args.destination / f"case_{index:02d}_expected.hex", expected.reshape(-1), fmt="%08x")
        record = {"case": index, "side": side, "mode": mode, "pattern": pattern,
                  "input_sha256": hashlib.sha256(source.astype("<u4").tobytes()).hexdigest(),
                  "expected_sha256": hashlib.sha256(expected.astype("<u4").tobytes()).hexdigest(), "labels_used": False}
        if pattern == "stare":
            record.update(geometry=geometry[side], raw_rgb_member=rgb["member"], raw_rgb_member_sha256=rgb["member_sha256"])
        records.append(record)
    (args.destination / "vector_manifest.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("A3_M0_RGB_ONLY_VECTORS_PREPARED: 14 cases including reset-interrupted frame")


if __name__ == "__main__":
    main()
