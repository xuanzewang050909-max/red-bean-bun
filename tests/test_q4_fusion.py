import unittest
import numpy as np

from software.q1_bilateral import DIRECTIONS
from software.q4_fusion import candidates, evidence, scale_support, fusion_mask


class FusionTests(unittest.TestCase):
    def test_finite_grid_and_noadd_ablations(self):
        grid = list(candidates())
        self.assertEqual(len(grid), 40)
        self.assertEqual(len({c['id'] for c in grid}), 40)
        self.assertEqual(sum(c['gap'] == 0 for c in grid), 8)

    def test_scalar_oracle_including_diagonal_edges_and_extremes(self):
        rng = np.random.default_rng(307)
        image = rng.integers(0, 256, (7, 8), dtype=np.uint8)
        image[0, 0] = 255; image[-1, -1] = 0
        h, w = image.shape
        def get(y, x):
            return int(image[min(max(y, 0), h-1), min(max(x, 0), w-1)])
        for length in (5, 9, 15):
            result = evidence(image, length)
            for index, (dy, dx) in enumerate(DIRECTIONS):
                for d in range(1, 6):
                    small, large, count, center = result[index][d-1]
                    for y, x in ((0, 0), (0, 7), (6, 0), (6, 7), (3, 4)):
                        l = []; r = []
                        for t in range(-length//2+1, length//2+1):
                            c = get(y+t*dy, x+t*dx)
                            l.append(get(y+t*dy-d*dx, x+t*dx+d*dy)-c)
                            r.append(get(y+t*dy+d*dx, x+t*dx-d*dy)-c)
                        self.assertEqual(int(small[y, x]), min(sum(l), sum(r)))
                        self.assertEqual(int(large[y, x]), max(sum(l), sum(r)))
                        self.assertEqual(int(count[y, x]), sum(a > 0 and b > 0 for a, b in zip(l, r)))
                        self.assertEqual(bool(center[y, x]), l[length//2] > 0 and r[length//2] > 0)

    def test_constant_and_step_are_not_supported(self):
        constant = np.full((41, 41), 230, np.uint8)
        step = constant.copy(); step[:20] = 100
        for im in (constant, step):
            for length in (5, 9, 15):
                self.assertFalse(np.any(scale_support(evidence(im, length), length, 8, 0, False)))

    def test_dark_line_in_bright_field_survives_and_short_gap_is_recovered(self):
        im = np.full((41, 41), 230, np.uint8); im[20] = 224
        c2 = np.zeros_like(im, bool); c2[20, 10:31] = True; c2[20, 20] = False
        c = next(c for c in candidates() if c['lengths'] == [5, 9, 15] and c['add_margin'] == 4 and c['gap'] == 1)
        final, seed, links = fusion_mask({'filtered': im}, np.ones_like(c2), c2, {}, c)
        self.assertTrue(final[20, 10:31].all()); self.assertFalse(seed[20, 20])
        self.assertEqual(int((final & ~seed).sum()), 1)
        self.assertTrue(links)

    def test_unseeded_lines_and_long_gaps_do_not_grow(self):
        im = np.full((41, 41), 230, np.uint8); im[20] = 224
        c2 = np.zeros_like(im, bool); c2[20, 10] = True; c2[20, 16] = True
        c = next(c for c in candidates() if c['gap'] == 3)
        final, seed, _ = fusion_mask({'filtered': im}, np.ones_like(c2), c2, {}, c)
        np.testing.assert_array_equal(final, seed)
        final, _, _ = fusion_mask({'filtered': im}, np.ones_like(c2), np.zeros_like(c2), {}, c)
        self.assertFalse(final.any())

    def test_fov_hole_prevents_connection_and_noadd_is_subset(self):
        im = np.full((41, 41), 230, np.uint8); im[20] = 224
        c2 = np.zeros_like(im, bool); c2[20, 10:31] = True; c2[20, 20] = False
        fov = np.ones_like(c2); fov[20, 20] = False
        for c in list(candidates())[:5]:
            final, seed, _ = fusion_mask({'filtered': im}, fov, c2, {}, c)
            self.assertFalse((final & ~fov).any()); self.assertFalse((final & ~c2).any())

    def test_local_center_and_persistence_are_required_for_addition(self):
        shape = (3, 3)
        small = np.full(shape, 50, np.int16); large = small.copy()
        central = np.ones(shape, bool); central[0, 0] = False
        count = np.full(shape, 9, np.uint8); count[1, 1] = 5
        ev = [[(small, large, count, central)] * 5] * 4
        keep = scale_support(ev, 9, 4, 2, False)[0]
        add = scale_support(ev, 9, 4, 2, True)[0]
        self.assertTrue(keep.all()); self.assertFalse(add[0, 0]); self.assertFalse(add[1, 1])
        self.assertTrue(add[2, 2])

    def test_full_fusion_matches_separate_dense_oracle(self):
        from scripts.verify_q4_fusion import oracle
        rng = np.random.default_rng(83)
        image = rng.integers(0, 256, (23, 27), dtype=np.uint8)
        c2 = rng.random(image.shape) > .5
        fov = rng.random(image.shape) > .1
        c2 &= fov
        actual_cache = {}; independent_cache = {}
        for c in candidates():
            final, seed, _ = fusion_mask({'filtered': image}, fov, c2, actual_cache, c)
            independent, other_seed = oracle({'filtered': image}, fov, c2, independent_cache, c)
            np.testing.assert_array_equal(final, independent, err_msg=c['id'])
            np.testing.assert_array_equal(seed, other_seed, err_msg=c['id'])


if __name__ == '__main__':
    unittest.main()
