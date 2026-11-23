"""Experimental, standard-library-only 1X2 multiclass logistic model.

Inputs are chronological, pre-game probability vectors; the module does NOT
modify live predictions or look at final scores when constructing features.
With this interface it learns calibration patterns, not independent team form.
"""
import math
from datetime import datetime, timezone

LABELS = ('1', 'X', '2')
FEATURE_NAMES = ('bias', 'log_p_home', 'log_p_draw', 'log_p_away',
                 'h2h_home_delta', 'h2h_draw_delta', 'h2h_away_delta')


def _validate_probabilities(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError('Probability vector must contain 3 numbers')
    v = [float(x) for x in value]
    if any(not math.isfinite(x) or x < 0 for x in v) or sum(v) <= 0:
        raise ValueError('Invalid probabilities')
    total = sum(v)
    return [max(1e-8, x / total) for x in v]


def features(sample):
    current = _validate_probabilities(sample['current'])
    h2h = _validate_probabilities(sample['h2h'])
    return [1.0, *(math.log(p) for p in current),
            *((b - a) for a, b in zip(current, h2h))]


def _softmax(values):
    high = max(values)
    exps = [math.exp(x - high) for x in values]
    s = sum(exps)
    return [e / s for e in exps]


def predict_proba(weights, sample):
    x = features(sample)
    if len(weights) != 3 or any(len(row) != len(x) for row in weights):
        raise ValueError('Invalid model weights')
    return _softmax([sum(w * v for w, v in zip(row, x)) for row in weights])


def fit(samples, *, epochs=350, learning_rate=0.03, l2=0.5):
    """Deterministic, regularized batch-gradient optimizer; no test-set fitting."""
    if len(samples) < 40:
        raise ValueError('At least 40 chronological training examples required')
    xs = [features(s) for s in samples]
    ys = [int(s['actual']) for s in samples]
    if any(y not in (0, 1, 2) for y in ys):
        raise ValueError('actual must be an integer 0, 1 or 2')
    n_features = len(xs[0])
    weights = [[0.0] * n_features for _ in range(3)]
    # Starting from the current model's log-probabilities makes it easier to
    # regularize toward 'do not change anything' with sparse data.
    for label in range(3):
        weights[label][label + 1] = 1.0
    prior = [row[:] for row in weights]
    n = len(xs)
    for _ in range(epochs):
        grad = [[0.0] * n_features for _ in range(3)]
        for x, actual in zip(xs, ys):
            probs = _softmax([sum(w * a for w, a in zip(row, x)) for row in weights])
            for k in range(3):
                error = probs[k] - (k == actual)
                for j in range(n_features):
                    grad[k][j] += error * x[j]
        for k in range(3):
            for j in range(n_features):
                penalty = 0.0 if j == 0 else l2 * (weights[k][j] - prior[k][j])
                weights[k][j] -= learning_rate * (grad[k][j] / n + penalty)
    return weights


def metrics(samples, predictor):
    if not samples:
        return None
    brier = log_loss = correct = 0.0
    for s in samples:
        p = predictor(s)
        y = int(s['actual'])
        log_loss -= math.log(max(1e-12, p[y]))
        brier += sum((p[k] - (k == y)) ** 2 for k in range(3))
        correct += int(max(range(3), key=p.__getitem__) == y)
    n = len(samples)
    return {'matches': n, 'accuracy_pct': round(100 * correct / n, 2),
            'mean_brier': round(brier / n, 5),
            'mean_log_loss': round(log_loss / n, 5)}


def evaluate(samples, league, minimum=100):
    """Chronological 70/30 split. Evaluation does not enable production model."""
    if len(samples) < minimum:
        return {'league': league, 'status': 'insufficient_data',
                'available_samples': len(samples), 'minimum_samples': minimum,
                'live_model_changed': False}
    ordered = sorted(samples, key=lambda s: (str(s['date']), str(s.get('id', ''))))
    cut = int(len(ordered) * .7)
    training, validation = ordered[:cut], ordered[cut:]
    # Avoid splitting matches with the exact same kickoff timestamp across
    # train and validation, as their pre-match information overlaps.
    boundary = str(validation[0]['date'])
    while training and str(training[-1]['date']) == boundary:
        validation.insert(0, training.pop())
    if len(training) < 40 or len(validation) < 20:
        return {'league': league, 'status': 'insufficient_data',
                'available_samples': len(samples), 'minimum_samples': minimum,
                'live_model_changed': False}
    weights = fit(training)
    base = metrics(validation, lambda s: _validate_probabilities(s['current']))
    candidate = metrics(validation, lambda s: predict_proba(weights, s))
    return {
        'league': league, 'status': 'evaluated',
        'trained_at': datetime.now(timezone.utc).isoformat(),
        'model_type': 'regularized_multinomial_logistic',
        'features': list(FEATURE_NAMES),
        'training_matches': len(training), 'validation_matches': len(validation),
        'first_validation_match': validation[0]['date'],
        'baseline': base, 'candidate': candidate,
        'validation_log_loss_improvement': round(base['mean_log_loss'] - candidate['mean_log_loss'], 5),
        'candidate_better_on_holdout': candidate['mean_log_loss'] < base['mean_log_loss'],
        'live_model_changed': False,
        'warning': 'Experimentell modell. En holdout räcker inte för aktivering; pröva flera tidsperioder.'
    }
