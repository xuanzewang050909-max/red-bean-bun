import unittest
import numpy as np
from software.q4d_features import integer_features, scalar_features
from software.q4d_forest import export_forest, predict_integer


class Q4dFeatureTests(unittest.TestCase):
    def test_random_edges_extremes_and_small_images_against_scalar(self):
        rng = np.random.default_rng(17)
        for shape in [(1, 1), (2, 5), (23, 29)]:
            g = rng.integers(0, 256, shape, dtype=np.uint8)
            g[0, 0] = 0; g[-1, -1] = 255
            names, f = integer_features(g)
            self.assertEqual(len(names), 36)
            for y, x in [(0, 0), (shape[0] - 1, shape[1] - 1), (shape[0] // 2, shape[1] // 2)]:
                np.testing.assert_array_equal(f[y, x], scalar_features(g, y, x))

    def test_flat_and_dark_line_vs_step(self):
        for level in [0, 127, 255]:
            names, f = integer_features(np.full((25, 25), level, np.uint8))
            self.assertTrue((f[..., 0] == level).all()); self.assertTrue((f[..., 1:] == 0).all())
        line = np.full((25, 25), 120, np.uint8); line[12, :] = 80
        step = np.full((25, 25), 120, np.uint8); step[12:, :] = 80
        names, lf = integer_features(line); _, sf = integer_features(step)
        k = names.index('bilateral9_d1_minimum')
        self.assertEqual(lf[12, 12, k], 40); self.assertEqual(sf[12, 12, k], 0)

    def test_integer_tree_export_matches_quantized_leaf_oracle(self):
        from sklearn.ensemble import RandomForestClassifier
        rng = np.random.default_rng(29)
        x = rng.integers(-30, 60, (1000, 3), dtype=np.int16)
        y = (x[:, 0] > 8) & (x[:, 1] < 21)
        rf = RandomForestClassifier(n_estimators=8, max_depth=6, min_samples_leaf=4, random_state=8).fit(x, y)
        model = export_forest(rf, ['a', 'b', 'c'])
        expected = sum(np.floor(t.predict_proba(x)[:, 1] * 255 + 0.5).astype(np.uint32) for t in rf.estimators_)
        expected = ((expected + 4) // 8).astype(np.uint8)
        np.testing.assert_array_equal(predict_integer(x, model), expected)


if __name__ == '__main__': unittest.main()
