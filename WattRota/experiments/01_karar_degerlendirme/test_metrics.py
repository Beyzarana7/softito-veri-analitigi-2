"""Metrik sınır durumları ve eşleştirilmiş örnekleme testleri."""
import unittest
import numpy as np
from metrics import cheap_hour_recall, information_capture, paired_bootstrap, rank_correlation, weighted_mae


class MetricsTests(unittest.TestCase):
    def test_weighted_error(self):
        self.assertAlmostEqual(weighted_mae([0, 10], [10, 10], [9, 1]), 9)
        self.assertTrue(np.isnan(weighted_mae([1], [2], [0])))

    def test_ranks_and_constant(self):
        self.assertAlmostEqual(rank_correlation([1, 2, 3], [3, 2, 1]), -1)
        self.assertTrue(np.isnan(rank_correlation([1, 1], [2, 3])))

    def test_cheap_hours_and_ties(self):
        self.assertEqual(cheap_hour_recall([1, 2, 3], [3, 2, 1], 1)[0], 0)
        self.assertEqual(cheap_hour_recall([1, 1, 1, 1], [1, 2, 3, 4], 2)[0], 0.5)
        self.assertEqual(cheap_hour_recall([1, 2, 3], [1, 2, 3], 2)[0], 1)

    def test_information_value(self):
        self.assertAlmostEqual(information_capture(100, 90, 80), 0.5)
        self.assertEqual(information_capture(100, 110, 80), -0.5)
        self.assertTrue(np.isnan(information_capture(100, 100, 100)))
        with self.assertRaises(ValueError):
            information_capture(100, 100, 110)

    def test_paired_resampling(self):
        for length in (1, 4):
            self.assertEqual(paired_bootstrap([7]*12, 1000, .95, 42, length), (7, 7, 7))
            a = paired_bootstrap(np.arange(12), 1000, .95, 42, length)
            self.assertEqual(a, paired_bootstrap(np.arange(12), 1000, .95, 42, length))


if __name__ == '__main__':
    unittest.main()
