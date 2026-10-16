"""Offline audit of a real PL output; never deployed or used to segment online.

The central rectangle and saturated-core band are illustrative diagnostic
regions, not lesion annotations or replacement evaluation masks.
"""
import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from software.metrics import evaluate
from software.preprocessing import pack_input, prepare_sample, read_archive
from software.reference import analyze, segment

RUN_ID = "28c603df754f4f9988485e53fd149fa8"
OUTPUT_SHA = "067e9b68c3543145ff8506c5dd81f75d31b61cfb8e5056e6eaee048cc4850caa"
ROI = (180, 145, 340, 385)  # x0, y0, x1, y1; half-open, 512 letterbox.


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def info(path):
    data = path.read_bytes()
    return {"path": path.relative_to(ROOT).as_posix(),
            "bytes": len(data), "sha256": sha(data)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Use a new output directory; preserve earlier evidence")

    package = ROOT / "build/deploy/browser_a4_w1_r1"
    manifest_path = package / "browser_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest["images"]["im0001"]["512"]
    bundle = ROOT / "build/board_results/browser_w1_2026-10-13/browser_session_bundle.zip"
    with zipfile.ZipFile(bundle) as archive:
        caps = json.loads(archive.read("capabilities.json"))
        require(not caps.get("host_test", False), "Host fixture is not real board evidence")
        prefix = RUN_ID + "/"
        record = json.loads(archive.read(prefix + "record.json"))
        require(record["status"] == "COMPLETED", "Screenshot task did not complete")
        expected_request = {"image_id": "im0001", "side": 512, "mode_code": 3,
                            "threshold": 28, "algorithm": "A"}
        require(all(record["request"][key] == value for key, value in expected_request.items()),
                "Wrong sample, mode, threshold or algorithm")
        arrays = {}
        for name in ("input_packed.npy", "output_packed.npy"):
            data = archive.read(prefix + name)
            require(record["files"][name] == {"bytes": len(data), "sha256": sha(data)},
                    "Recorded NPY file hash mismatch: " + name)
            arrays[name] = np.load(io.BytesIO(data), allow_pickle=False)
    source, output = arrays["input_packed.npy"], arrays["output_packed.npy"]
    require(source.dtype == output.dtype == np.uint32 and source.shape == output.shape == (512, 512),
            "Wrong array shape or dtype")
    require(sha(output.astype("<u4", copy=False).tobytes()) == OUTPUT_SHA == record["output"]["sha256"],
            "Output is not the array identified in the user's screenshot")
    require(sha(source.astype("<u4", copy=False).tobytes()) ==
            entry["input_word_sha256"] == record["input"]["sha256"], "Input hash mismatch")
    require(np.array_equal(source, np.load(package / entry["input"], allow_pickle=False)),
            "Input differs from immutable W1 input")
    rgb = np.stack(((source >> 16) & 255, (source >> 8) & 255, source & 255), axis=2).astype(np.uint8)
    fov = (source >> 24) != 0
    labels = {}
    label_paths = []
    for name, metadata in entry["evaluation_only"].items():
        path = package / metadata["path"]
        require(info(path)["sha256"] == metadata["file"]["sha256"], "GT artifact hash mismatch")
        labels[name] = np.load(path, allow_pickle=False).astype(bool)
        label_paths.append(path)
    # Independently repeat original RGB/GT alignment; GT never enters pack_input.
    raw = ROOT / "data/raw/stare"
    images = read_archive(raw / "stare-images.tar", "")
    raw_labels = {name: read_archive(raw / filename, suffix)["im0001"]["pixels"]
                  for name, filename, suffix in
                  (("AH", "labels-ah.tar", ".ah"), ("VK", "labels-vk.tar", ".vk"))}
    raw_labels = {name: np.any(value != 0, axis=2) if value.ndim == 3 else value != 0
                  for name, value in raw_labels.items()}
    original_rgb, aligned, _ = prepare_sample(images["im0001"]["pixels"], raw_labels, 512)
    require(np.array_equal(original_rgb, rgb) and
            np.array_equal(pack_input(original_rgb, aligned["fov"]), source), "Original RGB/FOV mismatch")
    require(all(np.array_equal(aligned[name], truth) for name, truth in labels.items()),
            "Original AH/VK annotation alignment mismatch")

    reference = analyze(rgb, fov, "A", 28)
    require(np.array_equal(reference["packed"], output), "Real PL words differ from frozen M0")
    historical = ROOT / "build/board_results/a4_segmentation_2026-10-12/a4_output_stare_512_mode3.npy"
    require(np.array_equal(output, np.load(historical, allow_pickle=False)),
            "Same-input historical verified A4 differs")
    mask = ((output >> 16) & 255) != 0
    response = (output >> 24).astype(np.uint8)
    x0, y0, x1, y1 = ROI
    roi = np.zeros(fov.shape, dtype=bool)
    roi[y0:y1, x0:x1] = True
    roi &= fov
    # LUT first saturates at filtered green 192. Use that exact existing boundary,
    # rather than a GT-derived bright-region detector or a new algorithm threshold.
    core = roi & (reference["filtered"] >= 192)
    band = cv2.dilate(core.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    band &= ~core & roi
    both_negative = ~labels["AH"] & ~labels["VK"]
    scopes = {"whole_original_fov": fov, "illustrative_central_rectangle": roi,
              "saturated_core": core, "seven_pixel_square_band": band}
    metrics = {}
    for name, region in scopes.items():
        metrics[name] = {"region_pixels": int(region.sum()),
                         "predicted_pixels": int((region & mask).sum()),
                         "predicted_negative_in_both_annotations":
                             int((region & mask & both_negative).sum()),
                         "response_at_least_28_pixels": int((region & (response >= 28)).sum()),
                         "by_annotation": {key: evaluate(mask, truth, region)
                                           for key, truth in labels.items()}}
    probes = {}
    for threshold in (28, 48, 80):
        prediction = segment(response, fov, threshold)
        probes[str(threshold)] = {"AH_whole_fov": evaluate(prediction, labels["AH"], fov),
                                 "band_predicted": int((prediction & band).sum()),
                                 "band_negative_in_both_annotations":
                                     int((prediction & band & both_negative).sum())}
    # Color classification is evaluation only, never an altered PL result.
    backdrop = (rgb.astype(np.uint16) // 4).astype(np.uint8)
    ah_view, vk_view, pl_view = [backdrop.copy() for _ in range(3)]
    ah_view[labels["AH"]] = (245, 245, 245)
    vk_view[labels["VK"]] = (245, 245, 245)
    pl_view[mask] = (245, 245, 245)
    error = backdrop.copy()
    error[mask & labels["AH"] & fov] = (40, 220, 80)
    error[mask & ~labels["AH"] & fov] = (255, 45, 45)
    error[~mask & labels["AH"] & fov] = (50, 190, 255)
    band_view = backdrop.copy()
    band_view[core] = (255, 210, 0)
    band_view[band] = (60, 70, 85)
    band_view[band & mask & both_negative] = (255, 45, 45)
    panels = [("Input RGB: central example", rgb), ("AH manual vessels", ah_view),
              ("VK manual vessels", vk_view), ("Actual PL mask: unchanged", pl_view),
              ("AH: green=TP, red=FP, blue=FN", error),
              ("Yellow=bright core; red=band FP*", band_view)]
    width, height, margin, heading = 320, 480, 16, 40
    figure = Image.new("RGB", (3 * (width + margin) + margin,
                              2 * (height + heading + margin) + margin + 74), "white")
    draw = ImageDraw.Draw(figure)
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 17) if font_path.exists() else ImageFont.load_default()
    for index, (title, pixels) in enumerate(panels):
        x, y = margin + (index % 3) * (width + margin), margin + (index // 3) * (height + heading + margin)
        draw.text((x, y + 7), title, fill="black", font=font)
        tile = Image.fromarray(pixels[y0:y1, x0:x1]).resize((width, height), Image.Resampling.NEAREST)
        figure.paste(tile, (x, y + heading))
    bottom = figure.height - 69
    draw.text((margin, bottom), "*Band FP: predicted, but neither AH nor VK marks a vessel.", fill="black", font=font)
    draw.text((margin, bottom + 23), "im0001 / real PL / 512 / mode 3 / T=28; illustrative crop, not a lesion label.", fill="black", font=font)
    args.output.mkdir(parents=True)
    figure_path = args.output / "comparison.png"
    figure.save(figure_path)
    sources = [bundle, manifest_path, package / entry["input"], historical, *label_paths,
               raw / "stare-images.tar", raw / "labels-ah.tar", raw / "labels-vk.tar",
               ROOT / "software/reference.py", ROOT / "software/preprocessing.py",
               ROOT / "software/metrics.py", Path(__file__).resolve()]
    report = {"status": "OFFLINE_AUDIT_OF_REAL_PL_OUTPUT_COMPLETE",
              "scope": "One training image; not full W1/performance/clinical acceptance",
              "run_id": RUN_ID, "request": expected_request, "input_word_sha256": record["input"]["sha256"],
              "output_word_sha256": OUTPUT_SHA, "mismatched_words_vs_frozen_M0": 0,
              "mismatched_words_vs_historical_A4": 0,
              "original_gt_and_geometry_recomputed": True, "sources": [info(path) for path in sources],
              "diagnostic_regions": {"central_rectangle_xyxy_half_open": list(ROI),
                                     "core_rule": "in rectangle and Gaussian3(raw G)>=192",
                                     "band_rule": "15x15 square dilation(core), minus core, within rectangle and original FOV",
                                     "limitations": "Illustrative RGB-defined regions, not clinical lesion labels; not algorithm gates"},
              "metrics": metrics, "threshold_probes": probes,
              "threshold_probe_status": "OFFLINE_SINGLE_TRAIN_IMAGE_ILLUSTRATION_NOT_PARAMETER_SELECTION",
              "runtime": {"numpy": np.__version__, "opencv": cv2.__version__},
              "figure": {"path": str(figure_path.resolve()), "sha256": sha(figure_path.read_bytes()),
                         "data_use": "Local research only; not committed or externally published"},
              "board_or_production_changes": False, "new_quality_algorithm_status": "DESIGN_ONLY_NOT_IMPLEMENTED"}
    (args.output / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    print(json.dumps({"status": report["status"], "band": metrics["seven_pixel_square_band"],
                      "saturated_core": metrics["saturated_core"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
