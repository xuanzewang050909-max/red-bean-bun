import unittest

import numpy as np

from software.q1_bilateral import DIRECTIONS
from software.q4_refinement import (balanced_support, bridge_gaps, candidates,
                                    flank_features, sample)
from software.continuity_metrics import continuity, bridge_audit


class RefinementTests(unittest.TestCase):
    def test_frozen_grid(self):
        grid = list(candidates())
        self.assertEqual(len(grid), 26)
        self.assertEqual(len({c['id'] for c in grid}), 26)

    def test_flanks_independent_scalar_borders_extremes(self):
        rng = np.random.default_rng(13891)
        for im in (rng.integers(0, 256, (11, 13), dtype=np.uint8),
                   np.array([[0, 255], [255, 0]], dtype=np.uint8)):
            h, w = im.shape
            actual = flank_features(im)
            for i, (dy, dx) in enumerate(DIRECTIONS):
                for d in range(1, 6):
                    for y, x in ((0, 0), (h - 1, w - 1), (h // 2, w // 2)):
                        def value(oy, ox):
                            return int(im[min(h-1, max(0, y+oy)), min(w-1, max(0, x+ox))])
                        c = sum(value(t*dy, t*dx) for t in range(-4, 5))
                        a = sum(value(t*dy-d*dx, t*dx+d*dy) for t in range(-4, 5)) - c
                        b = sum(value(t*dy+d*dx, t*dx-d*dy) for t in range(-4, 5)) - c
                        self.assertEqual(int(actual[i][d-1][0][y,x]), min(a,b))
                        self.assertEqual(int(actual[i][d-1][1][y,x]), max(a,b))

    def test_constant_and_step_rejected_dark_line_accepted(self):
        flat = np.full((31, 31), 180, np.uint8)
        self.assertFalse(np.any(balanced_support(flank_features(flat), 2, 1)))
        step = flat.copy(); step[15:] = 220
        supported = np.logical_or.reduce(balanced_support(flank_features(step), 2, 1))
        self.assertFalse(supported[10:21, 10:21].any())
        line = flat.copy(); line[15] = 170
        self.assertTrue(balanced_support(flank_features(line), 2, 1)[0][15, 15])

    def test_balance_rejects_one_bright_flank(self):
        im = np.full((31, 31), 100, np.uint8); im[15] = 99; im[16:] = 220
        result = balanced_support(flank_features(im), 4, 1)
        self.assertFalse(result[0][15, 15])

    def test_unsaturated_branch_can_preserve_bright_line(self):
        from software.reference import LUT
        im = np.full((31, 31), 230, np.uint8); im[15] = 220
        self.assertTrue(balanced_support(flank_features(im), 4, 1)[0][15, 15])
        self.assertFalse(np.any(balanced_support(flank_features(LUT[im]), 4, 1)))

    def test_supported_short_gaps_all_directions(self):
        for direction, (dy, dx) in enumerate(DIRECTIONS):
            for gap in (1, 2, 3):
                mask = np.zeros((17, 17), bool); fov = np.ones_like(mask)
                weak = [np.zeros_like(mask) for _ in DIRECTIONS]
                expected = mask.copy()
                for t in range(gap + 2):
                    weak[direction][8+t*dy, 8+t*dx] = True
                    expected[8+t*dy, 8+t*dx] = True
                mask[8, 8] = mask[8+(gap+1)*dy, 8+(gap+1)*dx] = True
                actual, _ = bridge_gaps(mask, weak, fov, 3)
                np.testing.assert_array_equal(actual, expected)

    def test_no_photometric_support_no_connection(self):
        mask = np.zeros((9,9), bool); mask[4,2] = mask[4,4] = True
        actual, _ = bridge_gaps(mask, [np.zeros_like(mask)]*4, np.ones_like(mask), 3)
        np.testing.assert_array_equal(actual, mask)

    def test_gap_limit_fov_and_non_recursive(self):
        mask = np.zeros((13,13), bool); mask[6,2] = mask[6,7] = True
        weak = [np.ones_like(mask)]*4; fov = np.ones_like(mask)
        actual, _ = bridge_gaps(mask, weak, fov, 3)
        np.testing.assert_array_equal(actual, mask)
        mask[6,4] = True; fov[6,5] = False
        actual, _ = bridge_gaps(mask, weak, fov, 3)
        self.assertTrue(actual[6,3]); self.assertFalse(actual[6,5:7].any())
        # An added horizontal midpoint cannot seed a diagonal second bridge.
        mask = np.zeros((13,13), bool); mask[6,4] = mask[6,6] = mask[8,7] = True
        w = [np.zeros_like(mask) for _ in DIRECTIONS]; w[0][6,4:7] = True
        w[2][6,5] = w[2][7,6] = w[2][8,7] = True
        actual, _ = bridge_gaps(mask, w, np.ones_like(mask), 1)
        self.assertTrue(actual[6,5]); self.assertFalse(actual[7,6])

    def test_border_does_not_wrap(self):
        mask = np.zeros((7,7), bool); mask[3,0] = mask[3,6] = True
        actual, _ = bridge_gaps(mask, [np.ones_like(mask)]*4, np.ones_like(mask), 3)
        np.testing.assert_array_equal(actual, mask)

    def test_continuity_distinguishes_gap_and_spurious_line(self):
        t = np.zeros((17,17), bool); t[8,3:14] = True; f = np.ones_like(t)
        exact = continuity(t,t,f); self.assertEqual(exact['cldice'], 1)
        broken = t.copy(); broken[8,8] = False
        g = continuity(broken,t,f)
        self.assertLess(g['cldice'], 1); self.assertLess(g['adjacent_edge_coverage'], 1)
        extra = t.copy(); extra[3,3:14] = True
        self.assertLess(continuity(extra,t,f)['topology_precision'], 1)
        self.assertIsNone(continuity(t, np.zeros_like(t),f)['cldice'])

    def test_bridge_audit_reports_false_connections(self):
        seed = np.zeros((9,9), bool); seed[4,2] = seed[4,4] = True
        result, links = bridge_gaps(seed,[np.ones_like(seed)]*4,np.ones_like(seed),1)
        a = bridge_audit(result,seed,links,seed,np.ones_like(seed))
        self.assertEqual(a['added_fp'],1); self.assertEqual(a['added_tp'],0)
        self.assertEqual(a['unsupported_interior_between_labeled_ends'],1)


if __name__ == '__main__':
    unittest.main()
