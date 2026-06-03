"""Regression checks for the removed automatic review wrapper."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_FILES = ("AGENTS.md", "CLAUDE.md", "CODEX.md", "GEMINI.md", "AI-CONTEXT.md")


def test_removed_review_wrapper_files_are_gone() -> None:
    removed_paths = [
        ROOT / "scripts" / ("run_free" + "_code_review.py"),
        ROOT / "scripts" / ("test_free" + "_code_review_wrapper.py"),
        ROOT / "docs" / "specs" / ("fr-free-code-review-tools.md"),
    ]

    assert [path.relative_to(ROOT).as_posix() for path in removed_paths if path.exists()] == []


def test_agent_rules_do_not_auto_run_review_wrapper() -> None:
    forbidden = (
        "free local review wrapper",
        "python scripts/" + "run_free" + "_code_review.py",
        "do not use coderabbit or any paid review service",
    )

    offenders = []
    for relative_path in AGENT_FILES:
        text = (ROOT / relative_path).read_text(encoding="utf-8").lower()
        if any(marker in text for marker in forbidden):
            offenders.append(relative_path)

    assert offenders == []


def test_ci_no_longer_runs_removed_scanner() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8").lower()
    scanner = "code" + "ql"

    assert f"\n  {scanner}:" not in workflow
    assert f"github/{scanner}-action/" not in workflow
