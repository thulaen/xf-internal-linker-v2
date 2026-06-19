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


def test_flags_direct_mutation_runner_call(tmp_path: Path) -> None:
    script = tmp_path / "scripts"
    script.mkdir()
    (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
    (script / "prepush-docker.sh").write_text(
        "bash scripts/run-python-repo-mutation.sh\n",
        encoding="utf-8",
    )

    errors = check_bazel_public_entrypoints.violations(tmp_path)

    assert errors == ["scripts/prepush-docker.sh:1: use scripts/bazel_default.py instead"]


def test_flags_deleted_turbo_mutation_public_path(tmp_path: Path) -> None:
    script = tmp_path / "scripts"
    script.mkdir()
    (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
    (script / "prepush-docker.sh").write_text(
        "python scripts/turbo_mutation.py --language rust\n",
        encoding="utf-8",
    )

    errors = check_bazel_public_entrypoints.violations(tmp_path)

    assert errors == ["scripts/prepush-docker.sh:1: use scripts/bazel_default.py instead"]


def test_flags_active_docs_that_present_old_runner_as_current(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
    (docs / "KUBE-PLAN-STATUS.md").write_text(
        "Run bash scripts/run-rust-quality.sh before committing.\n",
        encoding="utf-8",
    )

    errors = check_bazel_public_entrypoints.violations(tmp_path)

    assert errors == ["docs/KUBE-PLAN-STATUS.md:1: use scripts/bazel_default.py instead"]


def test_allows_historical_old_runner_mentions(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
    (docs / "KUBE-PLAN-STATUS.md").write_text(
        "Historical note: scripts/run-rust-quality.sh used to exist.\n",
        encoding="utf-8",
    )

    assert check_bazel_public_entrypoints.violations(tmp_path) == []


def test_flags_direct_mutation_tool_in_active_workflow(tmp_path: Path) -> None:
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
    (workflow / "scoped-mutation.yml").write_text(
        "steps:\n  - run: mutmut run --max-children 2\n",
        encoding="utf-8",
    )

    errors = check_bazel_public_entrypoints.violations(tmp_path)

    assert errors == [
        ".github/workflows/scoped-mutation.yml:2: use scripts/bazel_default.py instead"
    ]


def test_main_prints_errors(monkeypatch, tmp_path: Path, capsys) -> None:
    script = tmp_path / "scripts"
    script.mkdir()
    (tmp_path / "AGENTS.md").write_text("bash scripts/run-python-quality.sh\n", encoding="utf-8")
    monkeypatch.setattr(check_bazel_public_entrypoints, "ROOT", tmp_path)

    assert check_bazel_public_entrypoints.main() == 1
    assert "AGENTS.md:1" in capsys.readouterr().out


def test_main_returns_zero_when_clean(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("python scripts/bazel_default.py test //x\n", encoding="utf-8")
    monkeypatch.setattr(check_bazel_public_entrypoints, "ROOT", tmp_path)

    assert check_bazel_public_entrypoints.main() == 0
