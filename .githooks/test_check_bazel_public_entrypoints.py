"""Tests for the Bazel public entry-point guard."""

from __future__ import annotations

import importlib.util
from pathlib import Path


HOOK = Path(__file__).with_name("check-bazel-public-entrypoints.py")
SPEC = importlib.util.spec_from_file_location("check_bazel_public_entrypoints", HOOK)
assert SPEC and SPEC.loader
check_bazel_public_entrypoints = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_bazel_public_entrypoints)


def test_flags_direct_old_runner_call(tmp_path: Path) -> None:
    script = tmp_path / "scripts"
    script.mkdir()
    (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
    (script / "precommit-docker.sh").write_text(
        "bash scripts/run-python-quality.sh\n",
        encoding="utf-8",
    )

    errors = check_bazel_public_entrypoints.violations(tmp_path)

    assert errors == ["scripts/precommit-docker.sh:1: use scripts/bazel_default.py instead"]


def test_allows_bazel_default_call(tmp_path: Path) -> None:
    script = tmp_path / "scripts"
    script.mkdir()
    (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
    (script / "precommit-docker.sh").write_text(
        "python scripts/bazel_default.py run //tools/quality:python\n",
        encoding="utf-8",
    )

    assert check_bazel_public_entrypoints.violations(tmp_path) == []
