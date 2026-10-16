"""Execute only preregistered Q1-r1 training/AH experiments, never board tests."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import platform
import re
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from software.preprocessing import prepare_sample, pack_input
from software.reference import features, segment, correlate
from software.metrics import evaluate
from software.q1_bilateral import candidates, directional_evidence, support_mask, candidate_mask

PROTOCOL = "docs/q1_bilateral_protocol_r1.json"
BASELINE = "M0_A28"
SCOPES = ("fov", "full_image", "bright_core", "bright_band", "thin_label_proxy", "fov_edge")


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def read_training_archive(path, suffix, train, all_ids):
    """Enumerate every member name, but decode training images/labels only."""
    decoded, seen = {}, set()
    with tarfile.open(path, "r:*") as archive:
        for member in archive:
            match = re.fullmatch(r"(im\d{4})" + re.escape(suffix) + r"\.ppm\.gz", member.name)
            require(member.isfile() and match is not None, "Unexpected STARE entry")
            image_id = match[1]
            require(image_id not in seen, "Duplicate STARE entry")
            seen.add(image_id)
            if image_id not in train:
                continue
            compressed = archive.extractfile(member).read()
            pixels = np.array(Image.open(io.BytesIO(gzip.decompress(compressed))))
            decoded[image_id] = {"pixels": pixels, "member": member.name,
                                 "sha256": hashlib.sha256(compressed).hexdigest()}
    require(seen == set(all_ids) and set(decoded) == set(train), "Dataset/split changed")
    return decoded


def diagnostic_regions(feat, fov, truth):
    core = (feat["filtered"] >= 192) & fov
    square = np.ones((15, 15), np.uint8)
    band = cv2.dilate(core.astype(np.uint8), square,
                      borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool) & ~core & fov
    thin = (truth & fov & (correlate(truth.astype(np.uint8), np.ones((5, 5), np.int32)) <= 10)
            & (correlate(truth.astype(np.uint8), np.ones((3, 3), np.int32)) <= 6))
    edge = fov & ~cv2.erode(fov.astype(np.uint8), square,
                            borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    return {"fov": fov, "full_image": np.ones_like(fov), "bright_core": core,
            "bright_band": band, "thin_label_proxy": thin, "fov_edge": edge}


def score_mask(prediction, truth, region):
    value = evaluate(prediction, truth, region)
    value["region_pixels"] = int(region.sum())
    if value["tp"] + value["fn"] == 0:
        value["recall"] = None
    return value


def summarize(per_image):
    macro = {key: float(np.mean([entry["fov"][key] for entry in per_image.values()]))
             for key in ("dice", "iou", "precision", "recall")}
    pooled = {}
    for scope in SCOPES:
        counts = {key: sum(entry[scope][key] for entry in per_image.values())
                  for key in ("tp", "fp", "fn", "tn", "region_pixels")}
        tp, fp, fn = (counts[key] for key in ("tp", "fp", "fn"))
        pooled[scope] = {**counts, "recall": tp / (tp + fn) if tp + fn else None,
                         "dice": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                         "iou": tp / (tp + fp + fn) if tp + fp + fn else None}
    return {"macro_fov": macro, "pooled": pooled,
            "worst_dice_image": min(per_image, key=lambda name: per_image[name]["fov"]["dice"])}


def assess_candidate(candidate, baseline, gates):
    failures, deltas = [], {}

    def limit(value, minimum, name):
        if value is None or value < minimum - 1e-12:
            failures.append(name)

    for side in ("256", "512"):
        c, b = candidate[side], baseline[side]
        cm, bm = c["summary"]["macro_fov"], b["summary"]["macro_fov"]
        delta = {key: cm[key] - bm[key] for key in cm}
        delta["per_image_recall"] = {name: c["per_image"][name]["fov"]["recall"] -
                                    value["fov"]["recall"] for name, value in b["per_image"].items()}
        limit(delta["dice"], gates["512_macro_dice_gain_min"] if side == "512" else
              -gates["256_macro_dice_loss_max"], side + ":macro_dice")
        limit(delta["recall"], -gates["each_size_macro_recall_loss_max"], side + ":macro_recall")
        for name, value in delta["per_image_recall"].items():
            limit(value, -gates["each_image_each_size_recall_loss_max"], side + ":recall:" + name)
        for scope, key in (("thin_label_proxy", "each_size_thin_proxy_pooled_recall_loss_max"),
                           ("bright_band", "each_size_bright_band_pooled_recall_loss_max")):
            bc, cc = b["summary"]["pooled"][scope], c["summary"]["pooled"][scope]
            value = None if bc["recall"] is None else cc["recall"] - bc["recall"]
            delta[scope + "_recall"] = value
            limit(value, -gates[key], side + ":" + scope + "_recall")
        bfp = b["summary"]["pooled"]["bright_band"]["fp"]
        cfp = c["summary"]["pooled"]["bright_band"]["fp"]
        delta["bright_band_fp_reduction"] = (bfp - cfp) / bfp if bfp else None
        if side == "512":
            limit(delta["bright_band_fp_reduction"], gates["512_bright_band_pooled_fp_reduction_min"],
                  "512:bright_band_fp_reduction")
        deltas[side] = delta
    return {"eligible_for_Q2_feasibility": not failures, "failed_gates": failures, "deltas": deltas}


def preserved_files():
    # Original released code/binaries remain byte-identical; drafts elsewhere
    # in this shared workspace are neither executed nor included in this run.
    files = []
    for directory in ("pynq_app", "ui", "build/deploy/a4_segmentation_2017_4_r1",
                      "build/deploy/browser_a4_w1_r1"):
        files.extend(p for p in (ROOT / directory).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts)
    files.extend(ROOT / name for name in ("build/deploy/browser_a4_w1_r1.zip",
                                          "build/deploy/browser_start.ipynb"))
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(files))}


def r1_response(response, cache, candidate):
    support = support_mask(cache[candidate["length"]], candidate["length"], candidate["distances"],
                           candidate["margin"], candidate["persistence"])
    return np.where(support, response, np.uint8(0))


def main(protocol_name=PROTOCOL, candidate_factory=candidates, evidence_factory=directional_evidence,
         response_factory=r1_response, extra_source_names=()):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Use a new output directory; preserve all earlier attempts")
    protocol = json.loads((ROOT / protocol_name).read_text(encoding="utf-8"))
    source_names = [protocol_name, "software/q1_bilateral.py", "scripts/evaluate_q1_bilateral.py",
                    "tests/test_q1_bilateral.py", "software/reference.py", "software/preprocessing.py",
                    "software/metrics.py", *extra_source_names]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    for name in source_names:
        blob = subprocess.check_output(["git", "show", commit + ":" + name], cwd=ROOT)
        require(blob == (ROOT / name).read_bytes(), "Commit exact source bytes before experiment: " + name)
    source_hashes = {name: sha(ROOT / name) for name in source_names}
    for name, expected in protocol["frozen_source_sha256"].items():
        require(sha(ROOT / name) == expected, "Frozen input changed: " + name)
    original = json.loads((ROOT / "results/m0_stare_2026-10-11/evaluation.json").read_text(encoding="utf-8"))
    train, heldout = protocol["train_ids"], protocol["heldout_ids_not_decoded"]
    require(train == original["split"]["train"] and heldout == original["split"]["heldout"], "Original split changed")
    grid = list(candidate_factory())
    require(len(grid) == protocol["grid"]["candidate_count"], "Wrong grid size")
    require(sorted(set(v["length"] for v in grid)) == protocol["grid"]["lengths"] and
            sorted({tuple(v["distances"]) for v in grid}) == sorted(map(tuple, protocol["grid"]["distance_sets"])) and
            sorted(set(v["margin"] for v in grid)) == protocol["grid"]["minimum_mean_contrast"] and
            set(v["persistence"] for v in grid) == set(protocol["grid"]["persistence"]), "Grid differs from protocol")
    if "unsupported_penalties" in protocol["grid"]:
        require(sorted(set(v["penalty"] for v in grid)) == protocol["grid"]["unsupported_penalties"],
                "Penalty grid differs from protocol")
    lengths = sorted({v["length"] for v in grid})
    distances = sorted({d for v in grid for d in v["distances"]})
    before = preserved_files()
    args.output.mkdir(parents=True)
    provenance = {"protocol": protocol, "source_commit": commit, "source_sha256": source_hashes,
                  "client_date": "2026-10-14", "started_utc": datetime.now(timezone.utc).isoformat(),
                  "preserved_files_before": before, "decoded_train_ids": train,
                  "decoded_heldout_ids": [], "vk_opened": False,
                  "environment": {"python": platform.python_version(), "numpy": np.__version__, "opencv": cv2.__version__},
                  "location": "WINDOWS_CPU_OFFLINE_ONLY_NOT_FPGA"}
    write_json(args.output / "protocol_snapshot.json", provenance)
    raw = ROOT / "data/raw/stare"
    images = read_training_archive(raw / "stare-images.tar", "", train, train + heldout)
    ah = read_training_archive(raw / "labels-ah.tar", ".ah", train, train + heldout)
    all_scores = {name: {str(side): {"per_image": {}} for side in (256, 512)}
                  for name in [BASELINE] + [v["id"] for v in grid]}
    array_records, csv_rows = [], []
    for image_id in train:
        for side in (256, 512):
            rgb, labels, geometry = prepare_sample(images[image_id]["pixels"],
                                                   {"AH": ah[image_id]["pixels"] != 0}, side)
            truth, fov = labels["AH"], labels["fov"]
            require(truth.ndim == 2, "Expected original grayscale AH label")
            feat = features(rgb, fov, "A")
            regions = diagnostic_regions(feat, fov, truth)
            cache = {length: {d: evidence_factory(feat["enhanced"], length, d) for d in distances}
                     for length in lengths}
            masks = {BASELINE: segment(feat["response"], fov, 28)}
            initials = {BASELINE: (feat["response"] >= 28) & fov}
            for candidate in grid:
                response = response_factory(feat["response"], cache, candidate)
                require(response.dtype == np.uint8 and response.shape == fov.shape and
                        (response <= feat["response"]).all(), "Invalid candidate response")
                name = candidate["id"]
                masks[name] = segment(response, fov, 28)
                initials[name] = (response >= 28) & fov
                require(not (masks[name] & ~masks[BASELINE]).any(), "Unexpected non-subset result")
            for name, mask in masks.items():
                scores = {scope: score_mask(mask, truth, region) for scope, region in regions.items()}
                scores["initial_fov"] = score_mask(initials[name], truth, fov)
                all_scores[name][str(side)]["per_image"][image_id] = scores
                for scope, score in scores.items():
                    csv_rows.append({"candidate": name, "image_id": image_id, "side": side,
                                     "annotation": "AH_TRAIN", "scope": scope, **score})
            npz = args.output / f"{image_id}_{side}_offline_masks.npz"
            np.savez_compressed(npz, rgb=rgb, truth_AH=truth, fov=fov, enhanced=feat["enhanced"],
                                response=feat["response"], filtered=feat["filtered"],
                                **{name: np.packbits(mask, axis=None) for name, mask in masks.items()})
            array_records.append({"file": npz.name, "sha256": sha(npz), "geometry": geometry,
                                  "image_member_sha256": images[image_id]["sha256"], "AH_member_sha256": ah[image_id]["sha256"],
                                  "input_word_sha256": hashlib.sha256(pack_input(rgb, fov).astype("<u4").tobytes()).hexdigest(),
                                  "mask_sha256": {name: hashlib.sha256(mask.astype(np.uint8).tobytes()).hexdigest()
                                                  for name, mask in masks.items()}})
            print("Q1_TRAIN_CASE_COMPLETE", image_id, side, f"{len(grid)} candidates plus M0", flush=True)
    for name, values in all_scores.items():
        for side, entry in values.items():
            entry["summary"] = summarize(entry["per_image"])
    # Recompute original training baseline without reading new heldout predictions.
    for side in (256, 512):
        m0 = next(v for v in original["summary"] if (v["size"], v["algorithm"], v["split"], v["observer"])
                  == (side, "A", "train", "ah"))
        for metric, value in all_scores[BASELINE][str(side)]["summary"]["macro_fov"].items():
            require(abs(value - m0["macro_" + metric]) < 1e-12, "M0 baseline reproduction failed")
    assessments = {v["id"]: assess_candidate(all_scores[v["id"]], all_scores[BASELINE], protocol["selection_gates"])
                   for v in grid}
    eligible = [v for v in grid if assessments[v["id"]]["eligible_for_Q2_feasibility"]]
    eligible.sort(key=lambda v: (-all_scores[v["id"]]["512"]["summary"]["macro_fov"]["dice"],
                                 len(v["distances"]), v["length"], v["margin"],
                                 v["persistence"] != "none", v.get("penalty", 0), v["id"]))
    chosen = eligible[0] if eligible else None
    require(preserved_files() == before, "Production or original release bytes changed during research")
    with (args.output / "metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    report = {"status": "CPU_TRAINING_SCREEN_COMPLETE_NOT_PL", "protocol_sha256": source_hashes[protocol_name],
              "source_commit": commit, "candidate_count": len(grid), "training_cases": len(train) * 2,
              "candidates": grid, "scores": all_scores, "assessments": assessments,
              "selected_candidate": chosen, "eligible_count": len(eligible),
              "decision": "SELECT_FOR_Q2_FEASIBILITY_ONLY" if chosen else "REJECT_" + protocol["protocol"] + "_FOR_PL",
              "preserved_files_unchanged": True, "preserved_file_count": len(before),
              "M0_training_metrics_reproduced": True, "heldout_evaluated": False, "VK_evaluated": False,
              "new_hardware_status": "NOT_IMPLEMENTED_NOT_SIMULATED_NOT_BOARD_TESTED",
              "board_performance": None, "array_records": array_records,
              "finished_utc": datetime.now(timezone.utc).isoformat()}
    write_json(args.output / "training_report.json", report)
    print(json.dumps({"status": report["status"], "decision": report["decision"],
                      "selected_candidate": chosen, "eligible_count": len(eligible)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
