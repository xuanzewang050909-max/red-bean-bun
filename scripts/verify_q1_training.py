"""Independent stored-mask/metric audit and chosen-candidate convolution oracle.

This verifies CPU research, not FPGA quality or timing. Raw medical NPZs stay
in build. A report may pass this audit and still reject every candidate.
"""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from software.preprocessing import prepare_sample, pack_input
from software.reference import features, correlate, segment
from scripts.evaluate_q1_bilateral import read_training_archive, assess_candidate


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def independent_selected_response(enhanced, response, chosen):
    """Dense integer correlation oracle; no r1/r2 vector-evidence functions."""
    length = chosen["length"]
    h = length // 2
    radius = h + max(chosen["distances"])
    accepted = np.zeros(enhanced.shape, bool)
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        for distance in chosen["distances"]:
            kernels = [np.zeros((2 * radius + 1, 2 * radius + 1), np.int32) for _ in range(3)]
            for index, shift in enumerate((0, -distance, distance)):
                for t in range(-h, h + 1):
                    kernels[index][radius + t * dy - shift * dx, radius + t * dx + shift * dy] += 1
            c, left, right = [correlate(enhanced, k) for k in kernels]
            boundary = length * chosen["margin"]
            if boundary:
                accepted |= (left - c >= boundary) & (right - c >= boundary)
            else:
                accepted |= (left > c) & (right > c)
    return np.clip(response.astype(np.int32) - (~accepted) * chosen["penalty"], 0, 255).astype(np.uint8)


def independent_regions(feat, truth, fov):
    core = (feat["filtered"] >= 192) & fov
    band = cv2.dilate(core.astype(np.uint8), np.ones((15, 15), np.uint8),
                      borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool) & ~core & fov
    local5 = cv2.boxFilter(truth.astype(np.uint8), cv2.CV_32S, (5, 5), normalize=False,
                          borderType=cv2.BORDER_REPLICATE)
    local3 = cv2.boxFilter(truth.astype(np.uint8), cv2.CV_32S, (3, 3), normalize=False,
                          borderType=cv2.BORDER_REPLICATE)
    edge = fov & ~cv2.erode(fov.astype(np.uint8), np.ones((15, 15), np.uint8),
                            borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    return {"fov": fov, "full_image": np.ones_like(fov), "bright_core": core,
            "bright_band": band, "thin_label_proxy": truth & fov & (local5 <= 10) & (local3 <= 6),
            "fov_edge": edge}


def independent_metrics(mask, truth, region):
    tn, fp, fn, tp = map(int, np.bincount((truth.astype(np.uint8) * 2 + mask)[region], minlength=4))
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "region_pixels": tp + fp + fn + tn,
            "dice": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.0,
            "iou": tp / (tp + fp + fn) if tp + fp + fn else 1.0,
            "recall": tp / (tp + fn) if tp + fn else None,
            "precision": tp / (tp + fp) if tp + fp else (0.0 if fn else 1.0)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), "Preserve previous verification")
    report = json.loads((args.directory / "training_report.json").read_text(encoding="utf-8"))
    provenance = json.loads((args.directory / "protocol_snapshot.json").read_text(encoding="utf-8"))
    protocol = provenance["protocol"]
    train = protocol["train_ids"]
    require(not report["heldout_evaluated"] and not report["VK_evaluated"] and
            provenance["decoded_heldout_ids"] == [] and not provenance["vk_opened"], "Wrong research scope")
    for name, expected in provenance["source_sha256"].items():
        data = subprocess.check_output(["git", "show", report["source_commit"] + ":" + name], cwd=ROOT)
        require(digest(data) == expected, "Historical source mismatch: " + name)
    for name, expected in provenance["preserved_files_before"].items():
        require(digest((ROOT / name).read_bytes()) == expected, "Preserved original changed: " + name)
    for name, expected in protocol["frozen_source_sha256"].items():
        require(digest((ROOT / name).read_bytes()) == expected, "Frozen M0/data changed")
    raw = ROOT / "data/raw/stare"
    ids = train + protocol["heldout_ids_not_decoded"]
    images = read_training_archive(raw / "stare-images.tar", "", train, ids)
    ah = read_training_archive(raw / "labels-ah.tar", ".ah", train, ids)
    selected = report["selected_candidate"]
    require(len(report["array_records"]) == 20 and report["training_cases"] == 20, "Missing training cases")
    mask_pixels = mask_count = selected_pixels = metric_sets = 0
    seen = set()
    for artifact in report["array_records"]:
        path = args.directory / artifact["file"]
        require(digest(path.read_bytes()) == artifact["sha256"], "NPZ hash mismatch")
        image_id, side, *_ = path.stem.split("_")
        require(image_id in train and side in ("256", "512") and (image_id, side) not in seen, "Wrong/duplicate case")
        seen.add((image_id, side))
        rgb, labels, geometry = prepare_sample(images[image_id]["pixels"], {"AH": ah[image_id]["pixels"] != 0}, int(side))
        truth, fov = labels["AH"], labels["fov"]
        feat = features(rgb, fov, "A")
        require(geometry == artifact["geometry"], "Original geometry changed")
        require(digest(pack_input(rgb, fov).astype("<u4").tobytes()) == artifact["input_word_sha256"], "Input mismatch")
        regions = independent_regions(feat, truth, fov)
        with np.load(path, allow_pickle=False) as arrays:
            for key, expected in {"rgb": rgb, "truth_AH": truth, "fov": fov, "filtered": feat["filtered"],
                                  "enhanced": feat["enhanced"], "response": feat["response"]}.items():
                require(np.array_equal(arrays[key], expected), "Saved raw/feature mismatch")
            for name in report["scores"]:
                mask = np.unpackbits(arrays[name], count=int(side)**2).reshape(fov.shape).astype(bool)
                require(digest(mask.astype(np.uint8).tobytes()) == artifact["mask_sha256"][name], "Mask hash mismatch")
                require(not (mask & ~fov).any(), "Candidate outside original FOV")
                if name == "M0_A28":
                    require(np.array_equal(mask, segment(feat["response"], fov, 28)), "M0 mask changed")
                for scope, region in regions.items():
                    actual = independent_metrics(mask, truth, region)
                    require(actual == report["scores"][name][side]["per_image"][image_id][scope],
                            f"Independent count/metric mismatch {name}/{image_id}/{side}/{scope}")
                    metric_sets += 1
                if selected and name == selected["id"]:
                    response = independent_selected_response(feat["enhanced"], feat["response"], selected)
                    require(np.array_equal(mask, segment(response, fov, 28)), "Selected convolution oracle differs")
                    initial = independent_metrics((response >= 28) & fov, truth, fov)
                    require(initial == report["scores"][name][side]["per_image"][image_id]["initial_fov"],
                            "Selected initial counts differ")
                    selected_pixels += mask.size
                mask_count += 1
                mask_pixels += mask.size
        print("Q1_AUDIT_CASE", image_id, side, flush=True)
    # Summaries recomputed from independently verified integer counts.
    for name, sizes in report["scores"].items():
        for side, entry in sizes.items():
            for metric in ("dice", "iou", "precision", "recall"):
                mean = sum(v["fov"][metric] for v in entry["per_image"].values()) / 10
                require(abs(mean - entry["summary"]["macro_fov"][metric]) < 1e-12, "Macro mismatch")
            for scope in regions:
                pooled = entry["summary"]["pooled"][scope]
                for count in ("tp", "fp", "fn", "tn", "region_pixels"):
                    require(pooled[count] == sum(v[scope][count] for v in entry["per_image"].values()), "Pooled mismatch")
                require(pooled["recall"] == (pooled["tp"] / (pooled["tp"] + pooled["fn"])
                                             if pooled["tp"] + pooled["fn"] else None), "Pooled recall mismatch")
    eligible = []
    for candidate in report["candidates"]:
        name = candidate["id"]
        assessment = assess_candidate(report["scores"][name], report["scores"]["M0_A28"], protocol["selection_gates"])
        require(assessment == report["assessments"][name], "Quality gate decision mismatch")
        if assessment["eligible_for_Q2_feasibility"]:
            eligible.append(candidate)
    eligible.sort(key=lambda v: (-report["scores"][v["id"]]["512"]["summary"]["macro_fov"]["dice"],
                                 len(v["distances"]), v["length"], v["margin"], v["persistence"] != "none",
                                 v.get("penalty", 0), v["id"]))
    require(len(eligible) == report["eligible_count"] and selected == (eligible[0] if eligible else None), "Selection mismatch")
    row_count = 0
    with (args.directory / "metrics.csv").open(newline="", encoding="utf-8") as handle:
        csv_seen = set()
        for row in csv.DictReader(handle):
            key = (row["candidate"], row["image_id"], row["side"], row["scope"])
            require(key not in csv_seen and row["annotation"] == "AH_TRAIN", "Duplicate/wrong CSV row")
            csv_seen.add(key)
            record = report["scores"][key[0]][key[2]]["per_image"][key[1]][key[3]]
            for field, value in record.items():
                require((row[field] == "" if value is None else abs(float(row[field]) - value) < 1e-12), "CSV mismatch")
            row_count += 1
    require(row_count == 20 * len(report["scores"]) * 7, "CSV missing rows")
    output = {"status": "VERIFIED_OFFLINE_TRAINING_EVIDENCE_NOT_FPGA", "report_sha256": digest((args.directory / "training_report.json").read_bytes()),
              "verifier_sha256": digest(Path(__file__).read_bytes()), "candidate_masks_verified": mask_count,
              "mask_pixels_verified": mask_pixels, "independent_final_metric_sets": metric_sets,
              "chosen_candidate_pixels_vs_convolution_oracle": selected_pixels, "csv_rows_checked": row_count,
              "selected_candidate": selected, "eligible_count": len(eligible), "production_files_unchanged": len(provenance["preserved_files_before"]),
              "new_PL_evidence": False, "heldout_or_VK_decoded": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(output), flush=True)


if __name__ == "__main__":
    main()
