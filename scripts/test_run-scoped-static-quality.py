"""TDD guard for scripts/run-scoped-static-quality.ps1 — Dell-only orchestrator."""
from __future__ import annotations

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SCRIPT = SCRIPTS / "run-scoped-static-quality.ps1"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_orchestrator_file_exists():
    assert SCRIPT.exists(), "scripts/run-scoped-static-quality.ps1 must exist"


def test_starts_all_per_language_runners_in_parallel():
    t = _text()
    for s in (
        "run-python-quality.sh",
        "run-python-repo-mutation.sh",
        "run-rust-quality.sh",
        "run-angular-quality.sh",
    ):
        assert s in t, f"Orchestrator must start {s}"
    assert "Start-Job" in t, "Runners must start in parallel via Start-Job"


def test_dell_only_no_windows_local_or_mint_or_shard():
    """All quality runs on Dell via the self-dispatching runners. The old
    Windows-local jobs, Mint/icecc, Lua, and the compiled-language shard scripts
    are gone."""
    t = _text()
    for dead in (
        "run-dell-quality-shard.sh",
        "run-mint-quality-shard.sh",
        "run-lua-quality.sh",
        "sync-tree-to-mint.sh",
        "ICECC_SCHEDULER",
        "MintHost",
    ):
        assert dead not in t, f"Dell-only orchestrator must not reference {dead}"


def test_requires_dell_fail_closed():
    t = _text()
    assert "docker --context dell" in t
    assert "required" in t.lower()
    assert "exit 2" in t


def test_waits_for_all_jobs():
    t = _text()
    assert "Wait-Job" in t or "Receive-Job" in t


def test_reports_failed_runners_and_exits_nonzero():
    t = _text()
    assert "failed" in t.lower()
    assert "exit 1" in t


def test_has_plain_english_docker_error():
    t = _text()
    assert "Dell" in t and (
        "not reachable" in t or "not running" in t or "unavailable" in t
    )
