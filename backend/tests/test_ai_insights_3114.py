from learning import train

def test_recommendations_do_not_activate_model():
    samples = [{'date': str(i), 'current': [.6, .2, .2], 'h2h': [.5, .25, .25], 'actual': i % 3} for i in range(100)]
    result = train(samples, 'SHL')
    assert result['status'] == 'evaluated'
    assert result['live_model_changed'] is False
    assert result['insights']['recommendations']
    assert result['insights']['recommendations'][0]['kind'] == 'comparison'

def test_insufficient_data_remains_safe():
    result = train([], 'HA')
    assert result['status'] == 'insufficient_data'
    assert result['live_model_changed'] is False
