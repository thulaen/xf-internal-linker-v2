"""Regression tests for ``scripts/lib/sync_source_list.sh``.

Guards the bug where ``run-dell-quality-shard.sh`` shipped ~428 MB of
``backend/backups`` (plus ``backend/coverage-html``) to the Dell runner on every
remote check, because its hand-written ``tar --exclude=`` list had drifted out of
sync with the other syncers. The shared selector derives the file list from
``git ls-files`` so ``.gitignore`` is the single source of truth; these tests
assert the heavy/generated dirs are never emitted and that real source under the
requested roots still is.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "scripts" / "lib" / "sync_source_list.sh"


def _sync_file_list(*roots: str) -> list[str]:
    """Run the shared bash selector from the repo root; return its path list."""
    script = f'. "{HELPER.as_posix()}"; sync_file_list {" ".join(roots)} | tr "\\0" "\\n"'
    completed = subprocess.run(
        ["bash", "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def test_helper_file_exists():
    assert HELPER.is_file(), f"missing shared selector: {HELPER}"


def test_excludes_database_backups():
    paths = _sync_file_list("backend", "services", "rust", ".githooks", "scripts", "tools")
    offenders = [p for p in paths if p.startswith("backend/backups/")]
    assert offenders == [], f"backend/backups must never be synced; found {offenders[:5]}"


def test_excludes_coverage_html():
    paths = _sync_file_list("backend")
    offenders = [p for p in paths if p.startswith("backend/coverage-html/")]
    assert offenders == [], f"backend/coverage-html must never be synced; found {offenders[:5]}"


def test_includes_real_backend_source():
    paths = _sync_file_list("backend")
    assert any(p.startswith("backend/") and p.endswith(".py") for p in paths), (
        "expected real backend/*.py source files to still be in the sync list"
    )


def test_root_filter_limits_to_requested_roots():
    paths = _sync_file_list("scripts")
    assert paths, "expected at least one scripts/ file"
    assert all(p.startswith("scripts/") for p in paths), (
        "root filter must emit only paths under the requested roots"
    )
