"""Regression tests for the shared tar-exclude recipe (scripts/_sync_tar_excludes.py).

The 14-pattern exclude tuple was copy-pasted into 5 Python files + 1 shell
syncer and had to stay byte-identical (the Dell side re-hashes the same bytes, so
a drifted list fails the content manifest). These tests assert:
  * the shared tuple is byte-identical to the former hand-written literal, and
  * every consumer now imports/reads the shared list instead of redefining it.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED = REPO_ROOT / "scripts" / "_sync_tar_excludes.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _sync_tar_excludes import TAR_EXCLUDES, TAR_EXCLUDE_PATTERNS  # noqa: E402

# The exact literal every consumer used before consolidation. The shared tuple
# MUST equal this, or remote manifests built against the old bytes break.
GOLDEN = (
    "--exclude=__pycache__", "--exclude=*.pyc", "--exclude=*.so",
    "--exclude=build", "--exclude=build_*", "--exclude=.pytest_cache",
    "--exclude=.ruff_cache", "--exclude=htmlcov", "--exclude=backend/reports",
    "--exclude=backend/backups", "--exclude=backend/coverage-html",
    "--exclude=backend/extensions/build", "--exclude=backend/extensions/build_*",
    "--exclude=backend/extensions/reports",
)

PY_CONSUMERS = (
    "scripts/run_pytest_on_context.py",
    "scripts/turbo_tests.py",
    "scripts/run_lint_on_context.py",
    ".githooks/check-scoped-mutation.py",
    ".githooks/check-per-file-coverage.py",
)
SHELL_CONSUMER = ".githooks/_sync_to_dell.sh"


def test_shared_tuple_is_byte_identical_to_legacy():
    assert TAR_EXCLUDES == GOLDEN


def test_backups_and_coverage_html_are_excluded():
    assert "--exclude=backend/backups" in TAR_EXCLUDES
    assert "--exclude=backend/coverage-html" in TAR_EXCLUDES


def test_patterns_have_no_prefix():
    assert TAR_EXCLUDE_PATTERNS[0] == "__pycache__"
    assert all(not p.startswith("--exclude=") for p in TAR_EXCLUDE_PATTERNS)


def test_python_consumers_import_shared_and_have_no_inline_tuple():
    for rel in PY_CONSUMERS:
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "_sync_tar_excludes" in src, f"{rel} must import the shared excludes module"
        assert '"--exclude=__pycache__"' not in src, f"{rel} still defines an inline exclude tuple"


def test_shell_consumer_reads_shared_and_has_no_inline_list():
    src = (REPO_ROOT / SHELL_CONSUMER).read_text(encoding="utf-8")
    assert "_sync_tar_excludes.py" in src, "shell syncer must read the shared excludes module"
    assert "--exclude='backend/backups'" not in src, "shell syncer still has an inline exclude list"


def test_module_run_as_script_prints_exact_args():
    out = subprocess.run(
        [sys.executable, str(SHARED)], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert tuple(out) == GOLDEN
