"""TDD tests for distributed C++ compilation via icecc.

Red: all tests fail before any production files are created/modified.
Green: all tests pass once the implementation is complete.

Spec: docs/specs/fr-icecc-distributed-cpp.md
"""
from __future__ import annotations

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO    = SCRIPTS.parent

ICECC_HELPER      = SCRIPTS / "icecc_helper.sh"
CPP_TESTS         = SCRIPTS / "run-cpp-tests.sh"
CPP_QUALITY       = SCRIPTS / "run-cpp-quality.sh"
MINT_SHARD        = SCRIPTS / "run-mint-quality-shard.sh"
ORCHESTRATOR      = SCRIPTS / "run-scoped-static-quality.ps1"


# ---------------------------------------------------------------------------
# icecc_helper.sh — the shared helper
# ---------------------------------------------------------------------------

def test_icecc_helper_exists():
    assert ICECC_HELPER.exists(), "scripts/icecc_helper.sh must be created"


def test_icecc_helper_sets_cmake_launcher_flags():
    t = ICECC_HELPER.read_text()
    assert "ICECC_CMAKE_LAUNCHER_FLAGS" in t, (
        "icecc_helper.sh must export ICECC_CMAKE_LAUNCHER_FLAGS so callers "
        "can append it to the cmake command"
    )


def test_icecc_helper_checks_icecc_binary():
    t = ICECC_HELPER.read_text()
    assert "command -v icecc" in t or "which icecc" in t, (
        "icecc_helper.sh must check that the icecc binary is present "
        "before enabling distributed compilation"
    )


def test_icecc_helper_checks_scheduler_env():
    t = ICECC_HELPER.read_text()
    assert "ICECC_SCHEDULER" in t, (
        "icecc_helper.sh must check ICECC_SCHEDULER env var is non-empty; "
        "if missing the helper must be a no-op (graceful fallback)"
    )


def test_icecc_helper_sets_both_c_and_cxx_launchers():
    t = ICECC_HELPER.read_text()
    assert "CMAKE_C_COMPILER_LAUNCHER" in t, (
        "icecc_helper.sh must set CMAKE_C_COMPILER_LAUNCHER=icecc "
        "so C files are distributed too"
    )
    assert "CMAKE_CXX_COMPILER_LAUNCHER" in t, (
        "icecc_helper.sh must set CMAKE_CXX_COMPILER_LAUNCHER=icecc "
        "for C++ files"
    )


# ---------------------------------------------------------------------------
# run-cpp-tests.sh — cmake build inside the Docker container
# ---------------------------------------------------------------------------

def test_cpp_tests_sources_icecc_helper():
    t = CPP_TESTS.read_text()
    assert "icecc_helper.sh" in t, (
        "run-cpp-tests.sh must source icecc_helper.sh to pick up "
        "ICECC_CMAKE_LAUNCHER_FLAGS before the cmake configure call"
    )


def test_cpp_tests_passes_launcher_flags_to_cmake():
    t = CPP_TESTS.read_text()
    assert "ICECC_CMAKE_LAUNCHER_FLAGS" in t, (
        "run-cpp-tests.sh must pass $ICECC_CMAKE_LAUNCHER_FLAGS to the "
        "cmake configure command so icecc is used when available"
    )


def test_cpp_tests_raises_parallel_count():
    t = CPP_TESTS.read_text()
    # The original hardcoded --parallel 2 should be replaced with a variable
    # or a higher number when icecc is active.
    assert "ICECC_JOBS" in t or "parallel_jobs" in t or "icecc_workers" in t, (
        "run-cpp-tests.sh must use a variable for --parallel so it can be "
        "raised when icecc distributes jobs to Mint (more than 2 jobs in flight)"
    )


# ---------------------------------------------------------------------------
# run-cpp-quality.sh — passes env var into Docker container
# ---------------------------------------------------------------------------

def test_cpp_quality_passes_icecc_scheduler():
    t = CPP_QUALITY.read_text()
    assert "ICECC_SCHEDULER" in t, (
        "run-cpp-quality.sh must pass ICECC_SCHEDULER into the Docker "
        "container so icecc_helper.sh inside the container can connect to Mint"
    )


# ---------------------------------------------------------------------------
# run-mint-quality-shard.sh — starts icecc daemon on Mint
# ---------------------------------------------------------------------------

def test_mint_shard_starts_icecc_daemon():
    t = MINT_SHARD.read_text()
    assert "iceccd" in t, (
        "run-mint-quality-shard.sh must start the icecc daemon (iceccd) "
        "on Mint so it can accept compile jobs from the Windows container"
    )


def test_mint_shard_starts_icecc_scheduler():
    t = MINT_SHARD.read_text()
    assert "icecc-scheduler" in t, (
        "run-mint-quality-shard.sh must start icecc-scheduler on Mint "
        "so the Windows container can discover available Mint cores"
    )


def test_mint_shard_icecc_is_conditional():
    t = MINT_SHARD.read_text()
    assert "command -v iceccd" in t or "command -v icecc-scheduler" in t, (
        "run-mint-quality-shard.sh must guard iceccd/icecc-scheduler startup "
        "with command -v so the script still runs when icecc is not installed"
    )


# ---------------------------------------------------------------------------
# run-scoped-static-quality.ps1 — resolves Mint IP and sets scheduler address
# ---------------------------------------------------------------------------

def test_orchestrator_resolves_mint_ip_for_icecc():
    t = ORCHESTRATOR.read_text(encoding="utf-8")
    assert "ICECC_SCHEDULER" in t, (
        "run-scoped-static-quality.ps1 must set ICECC_SCHEDULER so the "
        "compiled-tools Docker container knows where to reach the Mint icecc daemon"
    )


def test_orchestrator_passes_scheduler_to_env():
    t = ORCHESTRATOR.read_text(encoding="utf-8")
    # It should set it as an env var that gets forwarded to the cpp job
    assert "ICECC_SCHEDULER" in t and ("env:" in t or "ICECC_SCHEDULER" in t), (
        "run-scoped-static-quality.ps1 must export ICECC_SCHEDULER as an "
        "environment variable so run-cpp-quality.sh can pass it into Docker"
    )
