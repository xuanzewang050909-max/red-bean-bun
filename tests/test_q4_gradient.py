import unittest
import numpy as np

from software.q1_bilateral import DIRECTIONS
from software.q4_gradient import (candidates, gradient_evidence, gradient_support,
                                  context_bridges, gradient_mask)


class GradientTests(unittest.TestCase):
    def test_finite_grid_with_four_noadd_ablations(self):
        grid = list(candidates())
        self.assertEqual(len(grid), 28)
        self.assertEqual(len({c['id'] for c in grid}), 28)
        self.assertEqual(sum(c['gap'] == 0 for c in grid), 4)

    def test_scalar_edges_extremes_and_signed_sums(self):
        im = np.random.default_rng(91).integers(0, 256, (7, 8), dtype=np.uint8)
        im[0, 0] = 255; im[-1, -1] = 0
        def read(y, x):
            return int(im[min(max(y, 0), 6), min(max(x, 0), 7)])
        for n in (5, 9):
            ev = gradient_evidence(im, n)
            for i, (dy, dx) in enumerate(DIRECTIONS):
                for d in range(1, 6):
                    small, large, count, central = ev[i][d-1]
                    for y, x in ((0, 0), (0, 7), (6, 0), (6, 7), (3, 4)):
                        left = []; right = []
                        for t in range(-(n//2), n//2+1):
                            yy, xx = y+t*dy, x+t*dx
                            c = read(yy, xx)
                            tilt = read(yy+2*d*dx, xx-2*d*dy)-read(yy-2*d*dx, xx+2*d*dy)
                            left.append(4*(read(yy-d*dx, xx+d*dy)-c)+tilt)
                            right.append(4*(read(yy+d*dx, xx-d*dy)-c)-tilt)
                        self.assertEqual(int(small[y, x]), min(sum(left), sum(right)))
                        self.assertEqual(int(large[y, x]), max(sum(left), sum(right)))
                        self.assertEqual(int(count[y, x]), sum(l > 0 and r > 0 for l, r in zip(left, right)))
                        self.assertEqual(bool(central[y, x]), left[n//2] > 0 and right[n//2] > 0)
                        self.assertLessEqual(abs(int(small[y, x])), 1275*n)
                        self.assertLessEqual(abs(int(large[y, x])), 1275*n)

    def test_affine_ramp_cancels_exactly_in_unclipped_interior(self):
        y, x = np.indices((45, 47))
        base = np.random.default_rng(902).integers(80, 121, y.shape, dtype=np.uint8)
        tilted = (base.astype(np.int16)+x-y).astype(np.uint8)
        region = np.s_[14:-14, 14:-14]
        for n in (5, 9):
            a, b = gradient_evidence(base, n), gradient_evidence(tilted, n)
            for aa, bb in zip(a, b):
                for aaa, bbb in zip(aa, bb):
                    for actual, expected in zip(aaa, bbb):
                        np.testing.assert_array_equal(actual[region], expected[region])
            ramp = (100+x-y).astype(np.uint8)
            for row in gradient_evidence(ramp, n):
                for small, large, count, central in row:
                    self.assertFalse(small[region].any()); self.assertFalse(large[region].any())
                    self.assertFalse(count[region].any()); self.assertFalse(central[region].any())

    def test_dark_line_on_ramp_is_preserved_without_lut_saturation(self):
        y, x = np.indices((45, 45)); im = (180+y).astype(np.uint8)
        im[22] -= 6
        c2 = np.zeros_like(im, bool); c2[22, 10:35] = True; c2[22, 22] = False
        c = next(c for c in candidates() if c['ratio'] == 2 and c['context'] == 5 and c['gap'] == 1)
        final, seed, _ = gradient_mask({'filtered': im}, np.ones_like(c2), c2, {}, c)
        self.assertTrue(final[22, 10:35].all())
        self.assertEqual(int((final & ~seed).sum()), 1)
        self.assertFalse(seed[22, 22])

    def test_straight_step_has_no_horizontal_support_at_strict_ratio(self):
        im = np.full((45, 45), 220, np.uint8); im[:22] = 100
        for n in (5, 9):
            planes = gradient_support(gradient_evidence(im, n), n, 2, 1, False)
            self.assertFalse(planes[0].any())

    def test_endpoint_context_rejects_isolated_seeds_and_keeps_supported_runs(self):
        seed = np.zeros((15, 25), bool); seed[7, [8, 12]] = True
        weak = [np.ones_like(seed)] + [np.zeros_like(seed)]*3
        fov = np.ones_like(seed)
        low, _ = context_bridges(seed, weak, fov, 3, 1)
        strong, _ = context_bridges(seed, weak, fov, 3, 3)
        self.assertTrue(low[7, 9:12].all()); np.testing.assert_array_equal(strong, seed)
        seed[7, 6:9] = True; seed[7, 12:15] = True
        strong, _ = context_bridges(seed, weak, fov, 3, 3)
        self.assertTrue(strong[7, 6:15].all())
        weak[0][7, 6] = False
        blocked, _ = context_bridges(seed, weak, fov, 3, 3)
        np.testing.assert_array_equal(blocked, seed)

    def test_fov_long_gap_and_absent_seed_prevent_growth(self):
        seed = np.zeros((15, 25), bool); seed[7, 4:9] = True; seed[7, 14:19] = True
        weak = [np.ones_like(seed)]*4; fov = np.ones_like(seed)
        final, _ = context_bridges(seed, weak, fov, 3, 3)
        np.testing.assert_array_equal(final, seed)
        empty, _ = context_bridges(np.zeros_like(seed), weak, fov, 3, 3)
        self.assertFalse(empty.any())
        seed[7, 10:14] = True; fov[7, 9] = False
        final, _ = context_bridges(seed, weak, fov, 3, 3)
        np.testing.assert_array_equal(final, seed & fov)

    def test_single_pass_does_not_use_new_context_to_bridge_again(self):
        seed = np.zeros((15, 25), bool); seed[7, 4:8] = True
        seed[7, 9:12] = True; seed[7, 13:17] = True
        weak = [np.ones_like(seed)]+[np.zeros_like(seed)]*3
        final, _ = context_bridges(seed, weak, np.ones_like(seed), 1, 5)
        # Neither endpoint has five consecutive original contextual seeds.
        np.testing.assert_array_equal(final, seed)

    def test_all_candidates_match_independent_dense_oracle(self):
        from scripts.verify_q4_gradient import oracle
        rng = np.random.default_rng(627)
        im = rng.integers(0, 256, (23, 27), dtype=np.uint8)
        fov = rng.random(im.shape) > .1; c2 = (rng.random(im.shape) > .5) & fov
        actual_cache = {}; independent_cache = {}
        for c in candidates():
            final, seed, _ = gradient_mask({'filtered': im}, fov, c2, actual_cache, c)
            expected, other_seed = oracle({'filtered': im}, fov, c2, independent_cache, c)
            np.testing.assert_array_equal(final, expected, err_msg=c['id'])
            np.testing.assert_array_equal(seed, other_seed, err_msg=c['id'])
            self.assertFalse((seed & ~c2).any())
            if not c['gap']:
                np.testing.assert_array_equal(final, seed)


if __name__ == '__main__':
    unittest.main()
