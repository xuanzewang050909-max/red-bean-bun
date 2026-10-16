import copy
import gzip
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from software.q1_bilateral import (DIRECTIONS, candidates, candidate_mask,
                                  directional_evidence, support_mask)
from software.reference import segment
from scripts.evaluate_q1_bilateral import assess_candidate, read_training_archive, score_mask, summarize


def scalar_evidence(image, y, x, dy, dx, length, distance):
    """Independent direct-coordinate oracle: no kernels, padding or array shift."""
    h, w = image.shape
    sample = lambda yy, xx: int(image[min(max(yy, 0), h - 1), min(max(xx, 0), w - 1)])
    center_sum = left_sum = right_sum = count = 0
    for step in range(-(length // 2), length // 2 + 1):
        yy, xx = y + step * dy, x + step * dx
        center = sample(yy, xx)
        left = sample(yy - distance * dx, xx + distance * dy)
        right = sample(yy + distance * dx, xx - distance * dy)
        center_sum += center
        left_sum += left
        right_sum += right
        count += int(left > center and right > center)
    return min(left_sum - center_sum, right_sum - center_sum), count


def gate(image, length=5, distances=(1, 2, 3), margin=1, persistence="majority"):
    cache = {d: directional_evidence(image, length, d) for d in distances}
    return support_mask(cache, length, distances, margin, persistence)


class BilateralTests(unittest.TestCase):
    def test_all_offsets_and_replicated_edges_match_scalar(self):
        image = np.random.default_rng(621).integers(0, 256, (8, 9), dtype=np.uint8)
        for length in (5, 9):
            for distance in (1, 2, 3):
                for (dy, dx), (sums, counts) in zip(DIRECTIONS, directional_evidence(image, length, distance)):
                    for y, x in np.ndindex(image.shape):
                        self.assertEqual((int(sums[y, x]), int(counts[y, x])),
                                         scalar_evidence(image, y, x, dy, dx, length, distance))

    def test_constant_has_no_support_including_margin_zero(self):
        for value in (0, 1, 128, 255):
            self.assertFalse(gate(np.full((15, 16), value, np.uint8), margin=0).any())

    def test_horizontal_vertical_and_diagonal_steps_rejected(self):
        y, x = np.indices((31, 31))
        for halfplane in (x >= 15, y >= 15, x + y >= 30, x - y >= 0):
            image = np.where(halfplane, 240, 40).astype(np.uint8)
            self.assertFalse(gate(image, margin=0, persistence="none")[8:-8, 8:-8].any())

    def test_thin_lines_in_four_directions_preserved(self):
        for dy, dx in DIRECTIONS:
            image = np.full((41, 41), 180, np.uint8)
            for t in range(-20, 21):
                image[20 + t * dy, 20 + t * dx] = 40
            self.assertTrue(gate(image, length=9, margin=4)[20, 20])

    def test_dark_line_crossing_bright_region_preserved(self):
        image = np.full((41, 60), 120, np.uint8)
        image[:, 30:] = 240
        image[20, :] = 35
        self.assertTrue(gate(image, length=9)[20, 8:-8].all())

    def test_majority_does_not_accept_single_dark_dot(self):
        image = np.full((31, 31), 100, np.uint8)
        image[15, 15] = 0
        self.assertTrue(gate(image, persistence="none")[15, 15])
        self.assertFalse(gate(image, persistence="majority")[15, 15])

    def test_signed_extremes_and_exact_threshold(self):
        image = np.full((31, 31), 255, np.uint8)
        image[15, :] = 0
        support, count = directional_evidence(image, 9, 1)[0]
        self.assertEqual(int(support[15, 15]), 2295)
        self.assertEqual(int(count[15, 15]), 9)
        opposite = directional_evidence(255 - image, 9, 1)[0][0]
        self.assertEqual(int(opposite[15, 15]), -2295)
        fake = {1: [(np.array([[4, 5, 19, 20, 0, -1]], np.int16),
                     np.full((1, 6), 5, np.uint8))] * 4}
        np.testing.assert_array_equal(support_mask(fake, 5, (1,), 1, "none"),
                                      [[False, True, True, True, False, False]])
        np.testing.assert_array_equal(support_mask(fake, 5, (1,), 4, "none"),
                                      [[False, False, False, True, False, False]])

    def test_direction_and_width_union_rotation_reflection(self):
        image = np.random.default_rng(981).integers(0, 256, (25, 25), dtype=np.uint8)
        result = gate(image)
        np.testing.assert_array_equal(gate(np.rot90(image)), np.rot90(result))
        np.testing.assert_array_equal(gate(image[:, ::-1]), result[:, ::-1])
        single = [gate(image, distances=(d,)) for d in (1, 2, 3)]
        np.testing.assert_array_equal(result, np.logical_or.reduce(single))

    def test_original_postprocessing_fov_and_subset(self):
        rng = np.random.default_rng(182)
        response = rng.integers(0, 80, (31, 31), dtype=np.uint8)
        fov = np.zeros((31, 31), bool)
        fov[3:-3, 3:-3] = True
        baseline = segment(response, fov, 28)
        np.testing.assert_array_equal(candidate_mask(response, fov, np.ones_like(fov)), baseline)
        result = candidate_mask(response, fov, rng.integers(0, 2, fov.shape).astype(bool))
        self.assertFalse((result & ~baseline).any())
        self.assertFalse((result & ~fov).any())
        self.assertFalse(candidate_mask(response, fov, np.zeros_like(fov)).any())

    def test_preregistered_grid_and_bad_inputs(self):
        grid = list(candidates())
        self.assertEqual(len(grid), 64)
        self.assertEqual(len({v["id"] for v in grid}), 64)
        for image, length, distance in ((np.zeros((4, 4), float), 5, 1),
                                         (np.zeros((4, 4), np.uint8), 7, 1),
                                         (np.zeros((4, 4), np.uint8), 5, 4)):
            with self.assertRaises(ValueError):
                directional_evidence(image, length, distance)
        with self.assertRaises(ValueError):
            candidate_mask(np.zeros((4, 4), np.uint8), np.ones((4, 4)), np.ones((4, 4), bool))

    def test_reader_never_decodes_heldout_members(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.tar"
            pixels = io.BytesIO()
            Image.fromarray(np.zeros((3, 3), np.uint8)).save(pixels, format="PPM")
            with tarfile.open(path, "w") as archive:
                # Heldout member is deliberately not even a valid gzip stream.
                for name, data in (("im0001.ah.ppm.gz", gzip.compress(pixels.getvalue())),
                                   ("im0002.ah.ppm.gz", b"MUST NOT DECODE HELDOUT")):
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))
            decoded = read_training_archive(path, ".ah", ["im0001"], ["im0001", "im0002"])
            self.assertEqual(list(decoded), ["im0001"])

    def test_quality_gate_rejects_recall_damage_despite_dice_gain(self):
        gates = json.loads((Path(__file__).resolve().parents[1] /
                            "docs/q1_bilateral_protocol_r1.json").read_text())["selection_gates"]
        baseline = {side: {"summary": {"macro_fov": {"dice": .60, "iou": .44, "precision": .54, "recall": .70},
                           "pooled": {"thin_label_proxy": {"recall": .60}, "bright_band": {"recall": .60, "fp": 100}}},
                           "per_image": {"train1": {"fov": {"recall": .70}}}} for side in ("256", "512")}
        candidate = copy.deepcopy(baseline)
        for side in candidate.values():
            side["summary"]["macro_fov"]["dice"] = .62
            side["summary"]["pooled"]["bright_band"]["fp"] = 80
        self.assertTrue(assess_candidate(candidate, baseline, gates)["eligible_for_Q2_feasibility"])
        candidate["512"]["per_image"]["train1"]["fov"]["recall"] = .60
        result = assess_candidate(candidate, baseline, gates)
        self.assertFalse(result["eligible_for_Q2_feasibility"])
        self.assertIn("512:recall:train1", result["failed_gates"])
        candidate["512"]["per_image"]["train1"]["fov"]["recall"] = .70
        candidate["512"]["summary"]["pooled"]["thin_label_proxy"]["recall"] = .56
        self.assertIn("512:thin_label_proxy_recall", assess_candidate(candidate, baseline, gates)["failed_gates"])

    def test_empty_diagnostics_are_null_not_perfect_recall(self):
        empty = np.zeros((3, 3), bool)
        self.assertIsNone(score_mask(empty, empty, ~empty)["recall"])
        from scripts.evaluate_q1_bilateral import SCOPES
        scores = {scope: score_mask(empty, empty, ~empty) for scope in SCOPES}
        # FOV has a positive truth for a valid whole-image training average.
        scores["fov"] = {**scores["fov"], "recall": .5}
        result = summarize({"train": scores})
        self.assertIsNone(result["pooled"]["bright_band"]["recall"])


if __name__ == "__main__":
    unittest.main()
