import unittest
import numpy as np
from scripts.audit_q4_profiles import histograms, metrics, bounds
from scripts.verify_q4_profile_features import independent_statistics, independent_bounds


class ProfileStatisticsTests(unittest.TestCase):
    def test_auc_and_ap_ties_match_pairwise_definition(self):
        scores = np.array([1, 1, 2, 2, 3, 8], np.uint16)
        labels = np.array([0, 1, 0, 1, 1, 0], bool)
        h = histograms(scores, labels, np.ones_like(labels))
        result = metrics(h)
        pos, neg = scores[labels], scores[~labels]
        brute = sum(float(p > n)+.5*float(p == n) for p in pos for n in neg)/(len(pos)*len(neg))
        self.assertEqual(result['auc'], brute)
        self.assertAlmostEqual(result['average_precision'], (1/2+2/4+3/6)/3)
        self.assertEqual(result, independent_statistics(h))

    def test_one_class_and_empty_do_not_claim_auc(self):
        for labels in (np.zeros(3, bool), np.ones(3, bool), np.zeros(0, bool)):
            h = histograms(np.zeros(len(labels), np.uint16), labels, np.ones_like(labels))
            self.assertIsNone(metrics(h)['auc'])
            self.assertIsNone(metrics(h)['average_precision'])

    def test_threshold_bounds_preserve_ties_and_exact_eighty_percent(self):
        h = np.zeros((2, 65536), np.int64)
        h[:, 30] = [4, 1]; h[:, 20] = [4, 2]; h[:, 10] = [10, 100]
        a = bounds(h)
        self.assertEqual(a['threshold_q8'], 30); self.assertEqual(a['precision'], .8)
        self.assertEqual(a, independent_bounds(h))
        b = bounds(h, 4)
        self.assertEqual(b['threshold_q8'], 10)  # Cannot split the ten tied positives at 10.
        self.assertEqual(b, independent_bounds(h, 4))

    def test_random_histogram_oracle_and_no_high_precision_claim(self):
        rng = np.random.default_rng(92)
        h = np.zeros((2, 65536), np.int64); h[:, :201] = rng.integers(0, 200, (2, 201))
        a, b = metrics(h), independent_statistics(h)
        for key in ('auc', 'average_precision'): self.assertAlmostEqual(a[key], b[key], places=14)
        self.assertIsNone(bounds(h))
        self.assertEqual(bounds(h, 50), independent_bounds(h, 50))


if __name__ == '__main__': unittest.main()
