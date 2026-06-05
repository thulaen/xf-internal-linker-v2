import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "check-default-on-rule.py"
_spec = importlib.util.spec_from_file_location("check_default_on_rule", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

class CheckDefaultOnRuleTests(unittest.TestCase):
    def test_is_migration_path(self):
        self.assertTrue(mod.is_migration_path(Path("backend/apps/core/migrations/0001_initial.py")))
        self.assertFalse(mod.is_migration_path(Path("backend/apps/core/models.py")))
        self.assertFalse(mod.is_migration_path(Path("frontend/src/app/foo.py")))

    def test_has_valid_exemption_true(self):
        source = """
# DEFAULT-ON-RULE: external-data-gated
# Reason: wait for external API
"""
        self.assertTrue(mod.has_valid_exemption(source))

    def test_has_valid_exemption_false(self):
        source = """
# DEFAULT-ON-RULE: external-data-gated
# No reason provided!
"""
        self.assertFalse(mod.has_valid_exemption(source))

    def test_find_off_seedings(self):
        source = """
AppSetting.objects.get_or_create(key="foo", defaults={"value": "0"})
AppSetting.objects.get_or_create(key="bar", defaults={"value": "1"})
        """
        findings = mod.find_off_seedings(source)
        self.assertEqual(len(findings), 1)
        # Should flag line 2 (value="0")
        self.assertEqual(findings[0][0], 2)

if __name__ == "__main__":
    unittest.main()
