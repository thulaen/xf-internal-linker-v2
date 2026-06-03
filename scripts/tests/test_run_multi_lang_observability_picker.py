"""Tests for scripts/run-multi-lang-observability-picker.py pure helpers.

The module imports the backend picker (apps.auto_issues.services.
multi_lang_picker) at load time; that package is not on the quality image's
path, so a fake module is injected into sys.modules before the module is
executed. Only the filesystem helpers are exercised here.

BDD:
  Given a path like "streamd.cpu.json"
  When _service_from_path() runs
  Then it returns the leading service name "streamd"

  Given a directory of *.json files
  When _json_files() runs
  Then it returns them sorted (and [] when the directory is absent)
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest import TestCase

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "run-multi-lang-observability-picker.py"

_PICKER_NAMES = [
    "find_multi_lang_observability_issues",
    "normalize_gwp_asan_crash",
    "normalize_perfetto_trace",
    "normalize_prometheus_series",
    "pprof_collector_gap_findings",
    "pprof_cpu_sample_rate_for_language",
    "send_findings_to_windows_backend",
]


def _install_fake_picker() -> None:
    pkg_apps = types.ModuleType("apps")
    pkg_ai = types.ModuleType("apps.auto_issues")
    pkg_services = types.ModuleType("apps.auto_issues.services")
    picker = types.ModuleType("apps.auto_issues.services.multi_lang_picker")
    for name in _PICKER_NAMES:
        setattr(picker, name, lambda *a, **k: None)
    sys.modules.setdefault("apps", pkg_apps)
    sys.modules.setdefault("apps.auto_issues", pkg_ai)
    sys.modules.setdefault("apps.auto_issues.services", pkg_services)
    sys.modules["apps.auto_issues.services.multi_lang_picker"] = picker


def _load():
    _install_fake_picker()
    spec = importlib.util.spec_from_file_location(
        "run_multi_lang_observability_picker", _MODULE_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_multi_lang_observability_picker"] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load()


class TestServiceFromPath(TestCase):
    def test_splits_on_first_dot(self) -> None:
        self.assertEqual(m._service_from_path(Path("streamd.cpu.json")), "streamd")

    def test_no_dot_uses_full_stem(self) -> None:
        self.assertEqual(m._service_from_path(Path("backend.json")), "backend")

    def test_empty_stem_falls_back(self) -> None:
        self.assertEqual(m._service_from_path(Path(".json")), "unknown-service")


class TestJsonFiles(TestCase):
    def test_missing_dir_returns_empty(self, ) -> None:
        self.assertEqual(m._json_files(Path("/no/such/dir/xyz")), [])

    def test_returns_sorted_json(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "b.json").write_text("{}", encoding="utf-8")
            (root / "a.json").write_text("{}", encoding="utf-8")
            (root / "c.txt").write_text("x", encoding="utf-8")
            result = m._json_files(root)
        self.assertEqual([p.name for p in result], ["a.json", "b.json"])


class TestLoadJson(TestCase):
    def test_loads_valid_json(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.json"
            path.write_text(json.dumps({"k": 1}), encoding="utf-8")
            self.assertEqual(m._load_json(path), {"k": 1})

    def test_returns_none_on_bad_json(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertIsNone(m._load_json(path))
