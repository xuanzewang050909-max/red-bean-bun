import unittest
import numpy as np

from software.q4_profile_features import kernels, profile_features, normalized_response, signed_mean
from scripts.verify_q4_profile_features import oracle


class ProfileFeatureTests(unittest.TestCase):
    def test_kernels_zero_dc_and_symmetry(self):
        bank = kernels()
        self.assertEqual(len(bank), 16)
        for item in bank:
            for name in ('mf', 'dog'):
                k = item[name]
                self.assertEqual(int(k.sum()), 0)
                self.assertLess(int(k.min()), 0); self.assertGreater(int(k.max()), 0)
                self.assertLessEqual(int(np.abs(k).sum())*255, 2**31-1)
                np.testing.assert_array_equal(k, (1 if name == 'mf' else -1)*k[::-1, ::-1])

    def test_constant_has_no_line_edge_or_coherence(self):
        for value in (0, 127, 255):
            result = profile_features(np.full((17, 19), value, np.uint8))
            self.assertTrue(all(not a.any() for a in result.values()))

    def test_integer_features_match_independent_spatial_sum_oracle(self):
        im = np.random.default_rng(501).integers(0, 256, (23, 29), dtype=np.uint8)
        im[0, 0] = 255; im[-1, -1] = 0
        expected = oracle(im, kernels()); actual = profile_features(im)
        for name in actual:
            np.testing.assert_array_equal(actual[name], expected[name], err_msg=name)

    def test_dark_line_and_step_have_different_paired_edge_costs(self):
        # Horizontal dark trough; the center of its odd derivative averages to 0.
        y = np.arange(81)-40
        line = np.repeat(np.rint(220-30*np.exp(-y*y/2))[:, None], 81, axis=1).astype(np.uint8)
        step = np.full_like(line, 220); step[:40] = 160
        horizontal = kernels()[0]
        a = normalized_response(line, horizontal['mf'])
        b = normalized_response(step, horizontal['mf'])
        dl = np.abs(signed_mean(normalized_response(line, horizontal['dog']), 31))
        ds = np.abs(signed_mean(normalized_response(step, horizontal['dog']), 31))
        self.assertGreater(a[40, 40], 0)
        self.assertGreater(b[34:46, 40].max(), 0)  # A matched filter alone responds to a step.
        self.assertEqual(int(dl[40, 40]), 0)
        self.assertGreater(ds[40, 40], 0)

    def test_invalid_input_and_non_square_tiny_images(self):
        for im in (np.zeros((0, 5), np.uint8), np.zeros((5, 5), np.float32), np.zeros((3, 3, 3), np.uint8)):
            with self.assertRaises(ValueError): profile_features(im)
        im = np.array([[0, 255, 3]], np.uint8)
        for name, a in profile_features(im).items():
            np.testing.assert_array_equal(a, oracle(im, kernels())[name])


if __name__ == '__main__': unittest.main()
