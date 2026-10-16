import unittest

import numpy as np

from software.q1_bilateral import DIRECTIONS
from software.q1_soft_support import candidates, directional_evidence, softened_response
from scripts.evaluate_q1_bilateral import r1_response
from tests.test_q1_bilateral import scalar_evidence
from software.reference import segment


class SoftSupportTests(unittest.TestCase):
    def test_wider_flanks_match_scalar_including_frame_edges(self):
        image = np.random.default_rng(762).integers(0, 256, (8, 9), dtype=np.uint8)
        for length in (5, 9):
            for distance in (4, 5):
                for (dy, dx), (support, count) in zip(DIRECTIONS, directional_evidence(image, length, distance)):
                    for y, x in np.ndindex(image.shape):
                        self.assertEqual((int(support[y, x]), int(count[y, x])),
                                         scalar_evidence(image, y, x, dy, dx, length, distance))

    def test_response_saturates_and_supported_pixels_are_unchanged(self):
        response = np.array([[0, 3, 4, 27, 28, 255]], np.uint8)
        evidence = [(np.array([[0, -1, 0, 1, 0, -1]], np.int16), np.zeros((1, 6), np.uint8))] * 4
        cache = {5: {d: evidence for d in (1, 2, 3)}}
        candidate = next(candidates())
        np.testing.assert_array_equal(softened_response(response, cache, candidate), [[0, 0, 0, 27, 24, 251]])

    def test_grid_count_and_no_majority_or_unregistered_penalty(self):
        grid = list(candidates())
        self.assertEqual(len(grid), 32)
        self.assertEqual(len({v["id"] for v in grid}), 32)
        candidate = {**grid[0], "penalty": 7}
        with self.assertRaises(ValueError):
            softened_response(np.zeros((3, 3), np.uint8), {}, candidate)

    def test_soft_mask_is_between_hard_gate_and_baseline(self):
        rng = np.random.default_rng(72)
        image = rng.integers(0, 256, (31, 31), dtype=np.uint8)
        response = rng.integers(0, 80, image.shape, dtype=np.uint8)
        fov = np.ones(image.shape, bool)
        candidate = next(candidates())
        cache = {5: {d: directional_evidence(image, 5, d) for d in (1, 2, 3)}}
        hard = segment(r1_response(response, cache, candidate), fov, 28)
        soft = segment(softened_response(response, cache, candidate), fov, 28)
        original = segment(response, fov, 28)
        self.assertFalse((hard & ~soft).any())
        self.assertFalse((soft & ~original).any())


if __name__ == "__main__":
    unittest.main()
