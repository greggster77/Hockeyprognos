"""Conservative, dependency-free, self-training probability calibrator.

Uses walk-forward pregame forecasts; chooses parameters on a chronological
training partition and reports performance on a later untouched partition.
Never changes production predictions.
"""
import math
from datetime import datetime, timezone

OUTCOMES = ('1', 'X', '2')


def calibrate(current, h2h, blend, temperature):
    """Blend independent forecast variants and calibrate confidence."""
    mixed = [(1 - blend) * a + blend * b for a, b in zip(current, h2h)]
    weights = [max(1e-8, p) ** (1 / temperature) for p in mixed]
    total = sum(weights)
    return [p / total for p in weights]


def score(samples, blend, temperature):
    total_loss = total_brier = correct = 0.0
    for sample in samples:
        probabilities = calibrate(sample['current'], sample['h2h'], blend, temperature)
        actual = sample['actual']
        total_loss -= math.log(max(1e-12, probabilities[actual]))
        total_brier += sum((p - (i == actual)) ** 2 for i, p in enumerate(probabilities))
        correct += probabilities.index(max(probabilities)) == actual
    n = len(samples)
    return {'matches': n, 'accuracy_pct': round(correct * 100 / n, 2),
            'mean_brier': round(total_brier / n, 5),
            'mean_log_loss': round(total_loss / n, 5)} if n else None


def train(samples, league):
    """Chronological holdout; no hyperparameter choice on validation results."""
    if len(samples) < 80:
        return {'league': league, 'status': 'insufficient_data',
                'available_samples': len(samples), 'minimum_samples': 80,
                'live_model_changed': False}
    cut = int(len(samples) * 0.7)
    training, validation = samples[:cut], samples[cut:]
    choices = [(blend, temperature) for blend in (0, .1, .25, .5, .75, 1)
               for temperature in (.7, .85, 1., 1.15, 1.3, 1.5)]
    blend, temperature = min(choices, key=lambda p: score(training, *p)['mean_log_loss'])
    baseline = score(validation, 0., 1.)
    candidate = score(validation, blend, temperature)
    improvement = baseline['mean_log_loss'] - candidate['mean_log_loss']
    return {'league': league, 'status': 'evaluated', 'trained_at': datetime.now(timezone.utc).isoformat(),
            'training_matches': len(training), 'validation_matches': len(validation),
            'first_validation_match': validation[0]['date'],
            'parameters': {'h2h_blend': blend, 'temperature': temperature},
            'baseline': baseline, 'candidate': candidate,
            'validation_log_loss_improvement': round(improvement, 5),
            'candidate_better_on_holdout': improvement > 0,
            'live_model_changed': False,
            'warning': 'Explorativ modell: kronologisk holdout, inte oberoende framtida verifiering. Ingen automatisk aktivering.'}
