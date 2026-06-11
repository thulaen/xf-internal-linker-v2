import unittest
import re
from apps.auto_issues.services.loki_picker import _NOISE_FILTER

class LokiPickerNoiseFilterTests(unittest.TestCase):
    def test_noise_filter_excludes_known_noise(self):
        self.assertTrue('database \\"test_xf_linker\\" already exists' in _NOISE_FILTER)
        self.assertTrue("timestamp too old" in _NOISE_FILTER)
        self.assertTrue('database \\"test_xf_linker\\" is being accessed' in _NOISE_FILTER)
        self.assertTrue("current transaction is aborted" in _NOISE_FILTER)

if __name__ == "__main__":
    unittest.main()

