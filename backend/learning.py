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
            'baseline': baseline, 'candidate': candidate, 'diagnostics': diagnose(validation, blend, temperature),
            'validation_log_loss_improvement': round(improvement, 5),
            'candidate_better_on_holdout': improvement > 0,
            'live_model_changed': False,
            'warning': 'Explorativ modell: kronologisk holdout, inte oberoende framtida verifiering. Ingen automatisk aktivering.'}


def diagnose(validation, blend, temperature):
    """Out-of-sample diagnostic counts; never influences fitted parameters."""
    labels = ('1', 'X', '2')
    confusion = {label: {pred: 0 for pred in labels} for label in labels}
    groups = {name: {'matches': 0, 'baseline_correct': 0, 'ai_correct': 0} for name in
              ('hemmafavorit', 'bortafavorit', 'oavgjort_favorit', 'jämn_match', 'tydlig_favorit')}
    outcomes = {label: {'actual': 0, 'predicted': 0, 'correct': 0} for label in labels}
    confidence = {name: {'matches': 0, 'correct': 0, 'confidence_sum': 0.0} for name in
                  ('under_40', '40_50', '50_60', '60_70', '70_plus')}
    corrected = worsened = both_wrong = both_right = 0
    errors = []
    for s in validation:
        base, ai = s['current'], calibrate(s['current'], s['h2h'], blend, temperature)
        actual = s['actual']; bpred = max(range(3), key=lambda i: base[i]); apred = max(range(3), key=lambda i: ai[i])
        bc, ac = bpred == actual, apred == actual
        both_right += int(bc and ac); both_wrong += int(not bc and not ac)
        corrected += int(not bc and ac); worsened += int(bc and not ac)
        confusion[labels[actual]][labels[apred]] += 1
        outcomes[labels[actual]]['actual'] += 1
        outcomes[labels[apred]]['predicted'] += 1
        outcomes[labels[actual]]['correct'] += int(ac)
        categories = ['hemmafavorit' if bpred == 0 else ('bortafavorit' if bpred == 2 else 'oavgjort_favorit')]
        spread = sorted(base, reverse=True)[0] - sorted(base, reverse=True)[1]
        categories.append('jämn_match' if spread < .10 else 'tydlig_favorit')
        for category in categories:
            g = groups[category]; g['matches'] += 1; g['baseline_correct'] += int(bc); g['ai_correct'] += int(ac)
        confidence_max = max(ai)
        bucket = ('under_40' if confidence_max < .4 else '40_50' if confidence_max < .5 else
                  '50_60' if confidence_max < .6 else '60_70' if confidence_max < .7 else '70_plus')
        c = confidence[bucket]; c['matches'] += 1; c['correct'] += int(ac); c['confidence_sum'] += confidence_max
        if not ac:
            errors.append({'date': s['date'], 'actual': labels[actual], 'baseline_pick': labels[bpred],
                           'ai_pick': labels[apred], 'ai_confidence_pct': round(confidence_max * 100, 1)})
    for label, o in outcomes.items():
        o['recall_pct'] = round(o['correct'] * 100 / o['actual'], 1) if o['actual'] else None
        o['precision_pct'] = round(o['correct'] * 100 / o['predicted'], 1) if o['predicted'] else None
    for g in groups.values():
        g['baseline_accuracy_pct'] = round(g['baseline_correct'] * 100 / g['matches'], 1) if g['matches'] else None
        g['ai_accuracy_pct'] = round(g['ai_correct'] * 100 / g['matches'], 1) if g['matches'] else None
    for c in confidence.values():
        c['accuracy_pct'] = round(c['correct'] * 100 / c['matches'], 1) if c['matches'] else None
        c['average_confidence_pct'] = round(c['confidence_sum'] * 100 / c['matches'], 1) if c['matches'] else None
        del c['confidence_sum']
    return {'confusion_actual_rows_ai_predictions': confusion, 'outcomes': outcomes, 'match_types': groups,
            'confidence_bins': confidence, 'baseline_and_ai_both_right': both_right,
            'baseline_and_ai_both_wrong': both_wrong, 'ai_corrected_baseline_errors': corrected,
            'ai_introduced_errors': worsened, 'recent_ai_misses': errors[-12:][::-1],
            'note': 'Enbart senare testmatcher. Små grupper ger osäkra procentsatser.'}
