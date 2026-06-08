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
    windows_section = t.split("# --- 3. Start the Dell job", maxsplit=1)[0]
    assert '"scripts/run-rust-quality.sh"' not in windows_section


def test_delegates_megalinter_to_dell_only_mint_removed():
    t = _text()
    assert "run-dell-quality-shard.sh" in t
    # Mint is removed from the compute path — it stays only as the storage/
    # observability host, never a quality shard.
    assert "run-mint-quality-shard.sh" not in t
    assert "megalinter-windows" not in t


def test_reuses_existing_quality_images_for_turbo_speed():
    t = _text()
    assert "XF_QUALITY_NO_BUILD" in t
    assert "XF_TURBO_MUTATION" in t


def test_does_not_start_a_mint_job():
    """Mint is removed from compute — no Mint ssh shard, no Mint source sync."""
    t = _text()
    assert "run-mint-quality-shard.sh" not in t
    assert "sync-tree-to-mint.sh" not in t


def test_starts_dell_job_via_docker_context():
    t = _text()
    assert "docker --context dell" in t
    assert "run-dell-quality-shard.sh" in t


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


def test_does_not_sync_to_mint():
    """Mint is no longer a compute shard, so the flaky tar-over-ssh source sync
    that used to race the commit is gone. Dell carries the compiled + MegaLinter
    work; Dell does its own source sync inside run-dell-quality-shard.sh."""
    t = _text()
    assert "sync-tree-to-mint.sh" not in t
    assert "run-dell-quality-shard.sh" in t
