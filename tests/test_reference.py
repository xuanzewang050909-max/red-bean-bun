import unittest
import numpy as np
from software.preprocessing import letterbox, pack_input, fov_from_rgb, prepare_sample
from software.reference import gaussian3, box_mean15, sparse_line_response, LUT, analyze
from software.metrics import evaluate


class ReferenceTests(unittest.TestCase):
    def test_gaussian_hand_calculated_corner_and_constant(self):
        ramp = np.arange(16, dtype=np.uint8).reshape(4, 4)
        self.assertEqual(int(gaussian3(ramp)[0, 0]), (0 * 9 + 1 * 3 + 4 * 3 + 5 + 8) // 16)
        for level in (0, 1, 127, 255):
            np.testing.assert_array_equal(gaussian3(np.full((8, 8), level, np.uint8)), level)

    def test_box_matches_scalar_replicate_and_rounding(self):
        image = np.random.default_rng(123).integers(0, 256, (4, 4), dtype=np.uint8)
        actual = box_mean15(image)
        for y in range(4):
            for x in range(4):
                total = sum(int(image[min(3, max(0, y + dy)), min(3, max(0, x + dx))])
                            for dy in range(-7, 8) for dx in range(-7, 8))
                self.assertEqual(int(actual[y, x]), (total + 112) // 225)

    def test_direction_constant_and_dark_line(self):
        np.testing.assert_array_equal(sparse_line_response(np.full((16, 16), 255, np.uint8)), 0)
        image = np.full((16, 16), 180, np.uint8); image[:, 8] = 20
        self.assertEqual(int(sparse_line_response(image)[8, 8]), 255)

    def test_lut_exhaustive_integer_formula_and_saturation(self):
        for value in range(256):
            self.assertEqual(int(LUT[value]), min(255, (255 * value + 96) // 192))

    def test_letterbox_alignment_and_binary_labels(self):
        rgb = np.full((10, 20, 3), 70, np.uint8)
        rgb[:, :10] = [255, 0, 0]
        label = np.zeros((10, 20), bool); label[:, :10] = True
        for size in (256, 512):
            out, masks, geometry = letterbox(rgb, {"gt": label}, size)
            top = size // 4
            self.assertEqual(geometry["pad_top"], top)
            self.assertFalse(masks["gt"][:top].any())
            self.assertTrue(masks["gt"][top:top + size // 2, :size // 2].all())
            self.assertFalse(masks["gt"][:, size // 2:].any())
            self.assertTrue((out[:top] == 0).all())
            self.assertEqual(masks["gt"].dtype, bool)

    def test_fov_rgb_only_fills_hole(self):
        rgb = np.zeros((16, 16, 3), np.uint8); rgb[2:14, 2:14] = 100; rgb[7:9, 7:9] = 0
        fov = fov_from_rgb(rgb)
        self.assertTrue(fov[7:9, 7:9].all()); self.assertFalse(fov[0].any())
        np.testing.assert_array_equal(fov_from_rgb(np.zeros_like(rgb)), False)

    def test_channel_pack_no_ground_truth_and_fov_filter(self):
        rgb = np.zeros((8, 8, 3), np.uint8); rgb[:] = [12, 34, 56]
        fov = np.zeros((8, 8), bool); fov[2:6, 2:6] = True
        packed = pack_input(rgb, fov)
        self.assertEqual(int(packed[3, 3]), 0x010C2238)
        for alg in ("A", "B"):
            result = analyze(rgb, fov, alg, 1)
            self.assertFalse(result["mask"].any())
            np.testing.assert_array_equal(result["packed"] & 255, 34)
            self.assertEqual(result["fov_pixels"], 16)

    def test_metrics_hand_calculated_and_shape_failure(self):
        pred = np.array([[1, 1], [0, 0]], bool); truth = np.array([[1, 0], [1, 0]], bool)
        scores = evaluate(pred, truth, np.ones((2, 2), bool))
        self.assertEqual(scores["dice"], 0.5); self.assertEqual(scores["iou"], 1 / 3)
        with self.assertRaises(ValueError): evaluate(pred, truth[:1], truth)

    def test_labels_cannot_override_fov_or_enter_pixel_packet(self):
        rgb = np.zeros((8, 8, 3), np.uint8)
        with self.assertRaises(ValueError):
            prepare_sample(rgb, {"fov": np.ones((8, 8), bool)}, 256)
        with self.assertRaises(ValueError):
            pack_input(rgb, np.full((8, 8), 255, np.uint8))


if __name__ == "__main__":
    unittest.main()
