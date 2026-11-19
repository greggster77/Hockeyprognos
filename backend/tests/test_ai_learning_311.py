from learning import calibrate, score, train


def test_probabilities_sum_to_one():
    p = calibrate([.5, .2, .3], [.4, .3, .3], .25, 1.15)
    assert abs(sum(p) - 1) < 1e-10
    assert all(0 < x < 1 for x in p)


def test_small_sample_does_not_activate():
    report = train([], 'SHL')
    assert report['status'] == 'insufficient_data'
    assert report['live_model_changed'] is False


def test_holdout_and_no_auto_activation():
    samples = [{'date': str(i), 'current': [.6, .2, .2], 'h2h': [.5, .25, .25], 'actual': i % 3}
               for i in range(100)]
    result = train(samples, 'NHL')
    assert result['training_matches'] == 70
    assert result['validation_matches'] == 30
    assert result['live_model_changed'] is False
