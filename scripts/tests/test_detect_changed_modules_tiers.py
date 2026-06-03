"""Convention tests for scripts/detect_changed_modules.py tier helpers.

BDD:
  Given a module config (injected, no filesystem read)
  When tier_for_path / tier_thresholds / tier_line_floor / tier_mutation_floor run
  Then the strictest matching tier wins, excludes drop matches, the default tier
       is used as fallback, a missing config returns None, and the line/mutation
       floors are read exactly — killing mutation survivors on the new tier code.

_load_module_config is monkeypatched so no YAML file is read.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    path = _SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dcm = _load("detect_changed_modules", "detect_changed_modules.py")


_FAKE_CFG = {
    "default_tier": "tier3",
    "modules": {
        "loose": {"tier": "tier3", "globs": ["backend/**"]},
        "strict": {"tier": "tier1", "globs": ["backend/apps/audit/**"],
                   "exclude": ["backend/apps/audit/migrations/**"]},
    },
    "tiers": {
        "tier1": {"line": 95, "branch": 90, "mutation": 80},
        "tier3": {"line": 60, "branch": 50, "mutation": 30},
    },
}


class _Patched(TestCase):
    def setUp(self):
        self._orig = dcm._load_module_config
        dcm._load_module_config = lambda: _FAKE_CFG

    def tearDown(self):
        dcm._load_module_config = self._orig


class TestTierForPath(_Patched):
    def test_strictest_tier_wins(self):
        self.assertEqual(dcm.tier_for_path("backend/apps/audit/models.py"), "tier1")

    def test_loose_only_match(self):
        self.assertEqual(dcm.tier_for_path("backend/other/x.py"), "tier3")

    def test_exclude_drops_strict_match(self):
        self.assertEqual(
            dcm.tier_for_path("backend/apps/audit/migrations/0001.py"), "tier3")

    def test_no_match_uses_default_tier(self):
        self.assertEqual(dcm.tier_for_path("frontend/app.ts"), "tier3")

    def test_missing_config_returns_none(self):
        dcm._load_module_config = lambda: None
        self.assertIsNone(dcm.tier_for_path("anything.py"))


class TestTierThresholds(_Patched):
    def test_thresholds_for_tier1(self):
        self.assertEqual(
            dcm.tier_thresholds("backend/apps/audit/models.py"),
            {"line": 95, "branch": 90, "mutation": 80})

    def test_missing_config_returns_none(self):
        dcm._load_module_config = lambda: None
        self.assertIsNone(dcm.tier_thresholds("anything.py"))


class TestTierFloors(_Patched):
    def test_line_floor_exact(self):
        self.assertEqual(dcm.tier_line_floor("backend/apps/audit/models.py"), 95)

    def test_mutation_floor_exact(self):
        self.assertEqual(dcm.tier_mutation_floor("backend/apps/audit/models.py"), 80)

    def test_line_floor_default_tier(self):
        self.assertEqual(dcm.tier_line_floor("backend/other/x.py"), 60)

    def test_floor_none_when_config_missing(self):
        dcm._load_module_config = lambda: None
        self.assertIsNone(dcm.tier_line_floor("anything.py"))
