"""Tests for scripts/quality_cores.py.

BDD:
  Given an XF_QUALITY_CORES override below the visible CPU count
  When quality_cores() runs
  Then it uses the override and reports source="override"

  Given an override above the visible CPU count
  When quality_cores() runs
  Then it clamps to visible CPUs and reports source="override-clamped"

  Given an invalid or zero override
  When _override_value() parses it
  Then it returns None and warns
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase, mock

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "quality_cores.py"


def _load():
    spec = importlib.util.spec_from_file_location("quality_cores", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["quality_cores"] = mod
    spec.loader.exec_module(mod)
    return mod


qc = _load()


class TestOverrideValue(TestCase):
    def test_none_when_empty(self) -> None:
        self.assertIsNone(qc._override_value(None))
        self.assertIsNone(qc._override_value(""))

    def test_none_when_not_an_integer(self) -> None:
        self.assertIsNone(qc._override_value("abc"))

    def test_none_when_zero_or_negative(self) -> None:
        self.assertIsNone(qc._override_value("0"))
        self.assertIsNone(qc._override_value("-4"))

    def test_returns_parsed_positive(self) -> None:
        self.assertEqual(qc._override_value("6"), 6)


class TestQualityCores(TestCase):
    def test_default_uses_all_visible_cpus(self) -> None:
        with mock.patch.object(qc, "visible_cpus", return_value=8), mock.patch.dict(
            qc.os.environ, {}, clear=False
        ):
            qc.os.environ.pop("XF_QUALITY_CORES", None)
            result = qc.quality_cores("ruff")
        self.assertEqual(result.workers, 8)
        self.assertEqual(result.source, "default")
        self.assertEqual(result.visible_cpus, 8)

    def test_override_below_visible_is_used(self) -> None:
        with mock.patch.object(qc, "visible_cpus", return_value=8), mock.patch.dict(
            qc.os.environ, {"XF_QUALITY_CORES": "3"}
        ):
            result = qc.quality_cores("pytest")
        self.assertEqual(result.workers, 3)
        self.assertEqual(result.source, "override")

    def test_override_above_visible_is_clamped(self) -> None:
        with mock.patch.object(qc, "visible_cpus", return_value=4), mock.patch.dict(
            qc.os.environ, {"XF_QUALITY_CORES": "99"}
        ):
            result = qc.quality_cores("pytest")
        self.assertEqual(result.workers, 4)
        self.assertEqual(result.source, "override-clamped")

    def test_override_equal_to_visible_is_override_not_clamped(self) -> None:
        with mock.patch.object(qc, "visible_cpus", return_value=4), mock.patch.dict(
            qc.os.environ, {"XF_QUALITY_CORES": "4"}
        ):
            result = qc.quality_cores("pytest")
        self.assertEqual(result.workers, 4)
        self.assertEqual(result.source, "override")


class TestCgroupQuota(TestCase):
    def test_returns_none_when_quota_is_max(self) -> None:
        with mock.patch.object(qc.Path, "read_text", return_value="max 100000"):
            self.assertIsNone(qc._linux_cgroup_quota_count())

    def test_floors_quota_over_period(self) -> None:
        with mock.patch.object(qc.Path, "read_text", return_value="250000 100000"):
            self.assertEqual(qc._linux_cgroup_quota_count(), 2)

    def test_clamps_to_at_least_one(self) -> None:
        with mock.patch.object(qc.Path, "read_text", return_value="50000 100000"):
            self.assertEqual(qc._linux_cgroup_quota_count(), 1)
