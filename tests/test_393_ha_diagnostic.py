import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from swedish_sources import _ha_response_shape
class TestHADiagnostics(unittest.TestCase):
    def test_redacts_values(self):
        data = {'secret': 'private-data', 'games': [{'home': 'AIK'}]}
        shape = str(_ha_response_shape(data))
        self.assertIn('secret', shape)
        self.assertNotIn('private-data', shape)
        self.assertNotIn('AIK', shape)
        self.assertIn('count', shape)
if __name__ == '__main__': unittest.main()
