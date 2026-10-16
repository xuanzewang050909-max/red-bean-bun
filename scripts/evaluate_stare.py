"""Reproducible M0 A/B evaluation; training labels select threshold, held-out labels score only."""
import argparse
import csv
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
from PIL import Image, ImageDraw
from software.preprocessing import read_archive, prepare_sample, pack_input
from software.reference import features, segment
from software.metrics import evaluate


def main():
    argp = argparse.ArgumentParser()
    argp.add_argument("--raw", type=Path, default=ROOT / "data/raw/stare")
    argp.add_argument("--output", type=Path, required=True)
    args = argp.parse_args()
    if args.output.exists():
        raise ValueError("Choose a new evaluation output directory")
    args.output.mkdir(parents=True)
    images = read_archive(args.raw / "stare-images.tar", "")
    ah = read_archive(args.raw / "labels-ah.tar", ".ah")
    vk = read_archive(args.raw / "labels-vk.tar", ".vk")
    ids = sorted(images)
    assert len(ids) == 20 and set(images) == set(ah) == set(vk)
    # Fixed alternating IDs; defined before inspecting any segmentation result.
    train, heldout = ids[::2], ids[1::2]
    samples, mappings, timings = {}, {}, {}
    for sample in ids:
        rgb = images[sample]["pixels"]
        assert rgb.shape == (605, 700, 3)
        for size in (256, 512):
            image, labels, geometry = prepare_sample(rgb, {
                "ah": ah[sample]["pixels"] > 0, "vk": vk[sample]["pixels"] > 0}, size)
            fov = labels["fov"]
            mappings[f"{sample}_{size}"] = {"geometry": geometry,
                "source_members": {"image": images[sample]["member"], "ah": ah[sample]["member"], "vk": vk[sample]["member"]},
                "source_hashes": {"image": images[sample]["member_sha256"], "ah": ah[sample]["member_sha256"], "vk": vk[sample]["member_sha256"]},
                "fov_pixels": int(np.count_nonzero(fov)),
                "ah_pixels_outside_fov": int(np.count_nonzero(labels["ah"] & ~fov)),
                "vk_pixels_outside_fov": int(np.count_nonzero(labels["vk"] & ~fov))}
            packed = pack_input(image, fov)
            np.savez_compressed(args.output / f"{sample}_{size}.npz", rgb=image, fov=fov,
                                gt_ah=labels["ah"], gt_vk=labels["vk"], packed_input=packed)
            start = time.perf_counter()
            fa = features(image, fov, "A")
            duration_a = time.perf_counter() - start
            start = time.perf_counter()
            fb = features(image, fov, "B")
            duration_b = time.perf_counter() - start
            samples[(sample, size)] = (image, labels, fa, fb)
            timings[f"{sample}_{size}"] = {"A_feature_cpu_seconds": duration_a,
                                           "B_feature_cpu_seconds": duration_b}
            print("FEATURES_READY", sample, size, flush=True)
    thresholds, tuning = {}, []
    for size in (256, 512):
        for alg, position in (("A", 2), ("B", 3)):
            scores = []
            for threshold in range(4, 129, 4):
                dice = []
                for sample in train:
                    _, labels, *unused = samples[(sample, size)]
                    response = samples[(sample, size)][position]["response"]
                    prediction = segment(response, labels["fov"], threshold)
                    dice.append(evaluate(prediction, labels["ah"], labels["fov"])["dice"])
                scores.append((float(np.mean(dice)), threshold))
                tuning.append({"size": size, "algorithm": alg, "threshold": threshold,
                               "training_ah_macro_dice": scores[-1][0]})
            # First threshold wins ties. All selection uses training AH only.
            best = max(scores, key=lambda score: score[0])
            thresholds[f"{alg}_{size}"] = best[1]
    rows = []
    for (sample, size), (rgb, labels, fa, fb) in samples.items():
        for alg, feat in (("A", fa), ("B", fb)):
            threshold = thresholds[f"{alg}_{size}"]
            prediction = segment(feat["response"], labels["fov"], threshold)
            Image.fromarray((prediction * 255).astype(np.uint8)).save(args.output / f"{sample}_{size}_{alg}_mask.png")
            for observer in ("ah", "vk"):
                for scope, region in (("fov", labels["fov"]), ("full_image", np.ones_like(labels["fov"]))):
                    rows.append({"sample": sample, "size": size, "algorithm": alg,
                                 "split": "train" if sample in train else "heldout",
                                 "observer": observer, "region": scope, "threshold": threshold,
                                 **evaluate(prediction, labels[observer], region)})
    with (args.output / "metrics.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    summary = []
    for size in (256, 512):
        for alg in ("A", "B"):
            for split in ("train", "heldout"):
                for observer in ("ah", "vk"):
                    group = [r for r in rows if (r["size"], r["algorithm"], r["split"], r["observer"], r["region"])
                             == (size, alg, split, observer, "fov")]
                    summary.append({"size": size, "algorithm": alg, "split": split,
                        "observer": observer, "threshold": thresholds[f"{alg}_{size}"],
                        **{f"macro_{key}": float(np.mean([r[key] for r in group]))
                           for key in ("dice", "iou", "precision", "recall")},
                        "worst_sample": min(group, key=lambda r: r["dice"])["sample"]})
    scores = {s["algorithm"]: s["macro_dice"] for s in summary
              if (s["size"], s["split"], s["observer"]) == (512, "train", "ah")}
    chosen = "B" if scores["B"] - scores["A"] > 0.01 else "A"
    report = {"status": "PASS_CPU_REFERENCE_EVALUATION_ONLY_NOT_FPGA",
              "source": "https://cecas.clemson.edu/~ahoover/stare/probing/index.html",
              "versions": {"python": platform.python_version(), "numpy": np.__version__,
                           "opencv": cv2.__version__},
              "split": {"train": train, "heldout": heldout},
              "selection_rule": "B only if 512 training AH macro Dice exceeds A by >0.01; otherwise prefer cheaper A; heldout never selects parameters",
              "chosen_algorithm": chosen, "thresholds": thresholds, "summary": summary,
              "timings": timings, "mappings": mappings,
              "gt_boundary": "GT used only for offline training threshold selection and final evaluation; not accepted by features/segment/pack_input",
              "source_files": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in [ROOT / "software/preprocessing.py", ROOT / "software/reference.py",
                            ROOT / "software/metrics.py", Path(__file__)]}}
    for name, value in (("evaluation.json", report), ("training_thresholds.json", tuning)):
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # A real sample contact sheet, with CPU provenance embedded in the figure.
    sample = heldout[0]; rgb, labels, fa, fb = samples[(sample, 512)]
    panel = Image.new("RGB", (1024, 560), "#152030")
    draw = ImageDraw.Draw(panel)
    draw.text((12, 8), f"CPU fixed-point reference | {sample} heldout | NOT FPGA OUTPUT", fill="white")
    original = Image.fromarray(rgb)
    mask = segment((fa if chosen == "A" else fb)["response"], labels["fov"], thresholds[f"{chosen}_512"])
    overlay = rgb.copy(); overlay[mask] = ((rgb[mask].astype(np.uint16) + [0, 255, 0]) // 2).astype(np.uint8)
    panel.paste(original, (0, 40)); panel.paste(Image.fromarray(overlay), (512, 40))
    panel.save(args.output / "cpu_reference_preview.png")
    print(json.dumps({"chosen": chosen, "thresholds": thresholds, "summary": summary}, indent=2), flush=True)


if __name__ == "__main__":
    main()
