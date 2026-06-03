import importlib.util
import unittest
from pathlib import Path

# Note: this module imports from backend.apps... which might fail if not fully setup.
# We will mock sys.modules to prevent the import from actually running, since we only want to test pure functions.
import sys
from unittest.mock import MagicMock
sys.modules['apps.auto_issues.services.multi_lang_picker'] = MagicMock()

_MOD_PATH = Path(__file__).resolve().parent / "run-multi-lang-observability-picker.py"
_spec = importlib.util.spec_from_file_location("run-multi-lang-observability-picker", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class RunMultiLangObservabilityPickerTests(unittest.TestCase):
    def test_service_from_path(self):
        path = Path("/repo/observability/perfetto/my-service.trace.json")
        self.assertEqual(mod._service_from_path(path), "my-service")

    def test_service_from_path_no_extensions(self):
        path = Path("/repo/observability/perfetto/my-service")
        self.assertEqual(mod._service_from_path(path), "my-service")

    def test_prometheus_queries_constant(self):
        self.assertTrue(hasattr(mod, "PROMETHEUS_QUERIES"))
        self.assertGreater(len(mod.PROMETHEUS_QUERIES), 0)

if __name__ == "__main__":
    unittest.main()
