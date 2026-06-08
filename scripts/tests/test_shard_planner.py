"""Tests for scripts/plan-scoped-quality-shards.py.

TDD Red: all tests fail before the planner script exists.
TDD Green: all tests pass once the planner is implemented.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
PLANNER_PATH = SCRIPTS / "plan-scoped-quality-shards.py"


def _load_planner():
    spec = importlib.util.spec_from_file_location("plan_scoped", PLANNER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_planner_file_exists():
    assert PLANNER_PATH.exists(), "scripts/plan-scoped-quality-shards.py must be created"


def test_empty_scope_returns_empty_lists():
    mod = _load_planner()
    result = mod.build_manifest(changed_files=[], windows_cpus=8, mint_cpus=4, dell_cpus=6)
    assert result["windows_megalinter_paths"] == []
    assert result["mint_megalinter_paths"] == []
    assert result["dell_megalinter_paths"] == []
    assert result["weight_proof"]["total_cost"] == 0


def test_megalinter_never_runs_on_windows_for_python_files():
    mod = _load_planner()
    result = mod.build_manifest(["backend/apps/audit/models.py"], 8, 4, 6)
    assert result["windows_megalinter_paths"] == []
    helper_paths = result["mint_megalinter_paths"] + result["dell_megalinter_paths"]
    assert "backend/apps/audit/models.py" in helper_paths


def test_all_megalinter_files_go_to_dell_mint_removed():
    """MegaLinter runs on Dell only now — Mint is removed from the compute path."""
    mod = _load_planner()
    files = [f"backend/apps/audit/models_{index}.py" for index in range(20)]
    result = mod.build_manifest(files, 8, 4, 6)
    assert result["windows_megalinter_paths"] == []
    assert result["mint_megalinter_paths"] == []
    assert set(result["dell_megalinter_paths"]) == set(files)
    assert result["weight_proof"]["dell_target_pct"] == 100.0
    assert result["weight_proof"]["mint_target_pct"] == 0.0
    assert result["weight_proof"]["dell_pct"] == 100.0
    assert result["weight_proof"]["mint_pct"] == 0.0


def test_weight_percentages_sum_to_100():
    mod = _load_planner()
    files = [
        "backend/apps/audit/models.py",
        "backend/extensions/foo.cpp",
        "services/speccheck/src/lib.rs",
        "scripts/run-go-quality.sh",
    ]
    result = mod.build_manifest(files, 8, 4, 6)
    proof = result["weight_proof"]
    assert abs(proof["windows_pct"] + proof["mint_pct"] + proof["dell_pct"] - 100.0) < 0.1


def test_deterministic_assignment():
    mod = _load_planner()
    files = ["a.py", "b.rs", "c.go", "d.cpp", "e.ts", "f.yml"]
    r1 = mod.build_manifest(files, 8, 4, 6)
    r2 = mod.build_manifest(files, 8, 4, 6)
    assert r1["windows_megalinter_paths"] == r2["windows_megalinter_paths"]
    assert r1["mint_megalinter_paths"] == r2["mint_megalinter_paths"]
    assert r1["dell_megalinter_paths"] == r2["dell_megalinter_paths"]


def test_disposable_artifacts_are_filtered_from_scope():
    mod = _load_planner()
    files = [
        "backend/apps/observability/services/stack_status.py",
        "frontend/.stryker-tmp/report.json",
        "tmp/free-code-review/output.json",
        "backend/.mutmut-cache/results.sqlite",
        ".tmp/turbo-quality-last.log",
        "backend/tmp/generated-marker.py",
        ".antigravitycli/session.json",
        "audit/session_start_payload.jsonl",
        "findbugs-current.png",
        "luacov.stats.out",
        "reports/megalinter/report.json",
    ]
    result = mod.build_manifest(files, 8, 4, 6)

    assert result["changed_files"] == ["backend/apps/observability/services/stack_status.py"]
    assert result["windows_megalinter_paths"] == []
    assert result["mint_megalinter_paths"] + result["dell_megalinter_paths"] == [
        "backend/apps/observability/services/stack_status.py"
    ]
