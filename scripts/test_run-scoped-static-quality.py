"""TDD guard for scripts/run-scoped-static-quality.ps1."""
from __future__ import annotations

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SCRIPT = SCRIPTS / "run-scoped-static-quality.ps1"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_orchestrator_file_exists():
    assert SCRIPT.exists(), "scripts/run-scoped-static-quality.ps1 must be created"


def test_starts_windows_quality_scripts_as_jobs():
    t = _text()
    for s in (
        "run-python-quality.sh",
        "run-python-repo-mutation.sh",
        "run-angular-quality.sh",
        "run-lua-quality.sh",
    ):
        assert s in t, f"Orchestrator must start {s} as a background job"


def test_does_not_run_rust_on_windows_host():
    t = _text()
    windows_section = t.split("# --- 3. Start Mint job", maxsplit=1)[0]
    assert '"scripts/run-rust-quality.sh"' not in windows_section


def test_delegates_megalinter_to_mint():
    t = _text()
    assert "run-mint-quality-shard.sh" in t
    assert "megalinter-windows" not in t


def test_reuses_existing_quality_images_for_turbo_speed():
    t = _text()
    assert "XF_QUALITY_NO_BUILD" in t
    assert "XF_TURBO_MUTATION" in t


def test_starts_mint_job_via_ssh():
    t = _text()
    assert "ssh" in t
    assert "run-mint-quality-shard.sh" in t


def test_waits_for_all_jobs():
    t = _text()
    assert "Receive-Job" in t or "Wait-Job" in t


def test_does_not_call_existing_sequential_scripts_directly():
    """Orchestrator must not reference the old sequential meta-lock."""
    t = _text()
    assert "quality_acquire_meta_lock" not in t


def test_has_plain_english_docker_error():
    t = _text()
    assert "Docker" in t and (
        "not running" in t or "not found" in t or "unavailable" in t
    )


def test_handles_zero_failed_jobs_under_strict_mode():
    t = _text()
    assert "@($failed).Count" in t


def test_syncs_working_tree_to_mint_before_shard():
    """Mint runs compiled-language quality against its OWN checkout, so the
    orchestrator must push the current working tree (including unstaged edits)
    to Mint BEFORE the shard runs — otherwise it builds Mint's stale code."""
    t = _text()
    assert "sync-tree-to-mint.sh" in t, (
        "orchestrator must invoke the Mint source-sync helper "
        "(rsync isn't on Windows; we tar-over-ssh through git-bash)"
    )
    before_shard = t.split("# --- 3. Start Mint job", maxsplit=1)[0]
    assert "sync-tree-to-mint.sh" in before_shard, (
        "the source-sync must run BEFORE the Mint shard ssh call, "
        "or Mint builds stale code"
    )
