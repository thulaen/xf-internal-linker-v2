"""Tests for scripts/plan-scoped-quality-shards.py.

BDD:
  Given a generated-artifact path (reports/, __pycache__, .tmp/)
  When is_disposable_artifact() runs
  Then it returns True and the file is dropped before sharding

  Given a non-empty changed-file list
  When build_manifest() runs
  Then every file lands on Mint (windows_pct=0) and the weight proof sums
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "plan-scoped-quality-shards.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "plan_scoped_quality_shards", _MODULE_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plan_scoped_quality_shards"] = mod
    spec.loader.exec_module(mod)
    return mod


p = _load()


class TestIsDisposableArtifact(TestCase):
    def test_reports_prefix_is_disposable(self) -> None:
        self.assertTrue(p.is_disposable_artifact("reports/codeql/python.sarif"))

    def test_tmp_prefix_is_disposable(self) -> None:
        self.assertTrue(p.is_disposable_artifact(".tmp/manifest.json"))

    def test_pycache_part_is_disposable(self) -> None:
        self.assertTrue(p.is_disposable_artifact("backend/apps/__pycache__/x.pyc"))

    def test_backslash_normalised(self) -> None:
        self.assertTrue(p.is_disposable_artifact("reports\\codeql\\x.sarif"))

    def test_findbugs_root_png_is_disposable(self) -> None:
        self.assertTrue(p.is_disposable_artifact("findbugs-001.png"))

    def test_normal_source_not_disposable(self) -> None:
        self.assertFalse(p.is_disposable_artifact("backend/apps/audit/models.py"))


class TestCost(TestCase):
    def test_cpp_is_most_expensive(self) -> None:
        self.assertEqual(p._cost("a.cpp"), 6)

    def test_go_and_rust_weight_five(self) -> None:
        self.assertEqual(p._cost("a.go"), 5)
        self.assertEqual(p._cost("a.rs"), 5)

    def test_python_weight_two(self) -> None:
        self.assertEqual(p._cost("a.py"), 2)

    def test_unknown_uses_default(self) -> None:
        self.assertEqual(p._cost("a.unknownext"), p.DEFAULT_COST)


class TestBuildManifest(TestCase):
    def test_empty_returns_zero_weight_proof(self) -> None:
        manifest = p.build_manifest([], 0, 8)
        self.assertEqual(manifest["weight_proof"]["total_cost"], 0)
        self.assertEqual(manifest["mint_megalinter_paths"], [])

    def test_all_files_go_to_mint(self) -> None:
        manifest = p.build_manifest(["a.py", "b.go"], 0, 8)
        self.assertEqual(manifest["windows_megalinter_paths"], [])
        self.assertEqual(set(manifest["mint_megalinter_paths"]), {"a.py", "b.go"})
        self.assertEqual(manifest["weight_proof"]["windows_pct"], 0.0)
        self.assertEqual(manifest["weight_proof"]["mint_pct"], 100.0)

    def test_total_cost_sums_file_costs(self) -> None:
        manifest = p.build_manifest(["a.py", "b.cpp"], 0, 8)
        self.assertEqual(manifest["weight_proof"]["total_cost"], 2 + 6)
        self.assertEqual(
            manifest["weight_proof"]["mint_cost"],
            manifest["weight_proof"]["total_cost"],
        )

    def test_disposable_files_dropped_to_empty_manifest(self) -> None:
        manifest = p.build_manifest(["reports/x.sarif", ".tmp/y.json"], 0, 8)
        self.assertEqual(manifest["mint_megalinter_paths"], [])
        self.assertEqual(manifest["weight_proof"]["total_cost"], 0)
