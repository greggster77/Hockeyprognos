import math
import random
import unittest
from ai_model import evaluate, features, fit, metrics, predict_proba

class AITest(unittest.TestCase):
    def setUp(self):
        rng = random.Random(7)
        self.samples = []
        for n in range(160):
            a = 0.25 + .35 * rng.random()
            b = .12 + .22 * rng.random()
            c = 1 - a - b
            u = rng.random()
            actual = 0 if u < a else 1 if u < a + b else 2
            self.samples.append({'date': f'2025-{1 + n // 28:02d}-{1 + n % 28:02d}',
                'current': [a, b, c], 'h2h': [a + 0.02, b - 0.01, c - 0.01], 'actual': actual})

    def test_feature_count(self):
        self.assertEqual(len(features(self.samples[0])), 7)

    def test_predictions_sum_to_one(self):
        weights = fit(self.samples[:110], epochs=5)
        p = predict_proba(weights, self.samples[120])
        self.assertAlmostEqual(sum(p), 1.0)
        self.assertTrue(all(0 < x < 1 for x in p))

    def test_training_does_not_activate(self):
        report = evaluate(self.samples, 'SHL')
        self.assertEqual(report['status'], 'evaluated')
        self.assertFalse(report['live_model_changed'])
        self.assertEqual(report['training_matches'] + report['validation_matches'], 160)

    def test_untrained_small_data(self):
        report = evaluate(self.samples[:50], 'SHL')
        self.assertEqual(report['status'], 'insufficient_data')

    def test_deterministic_training(self):
        a = fit(self.samples[:110], epochs=10)
        b = fit(self.samples[:110], epochs=10)
        self.assertEqual(a, b)

if __name__ == '__main__':
    unittest.main()
