"""Tests for the repository Antigravity CLI launcher setup."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_antigravity_launcher_defaults_to_sandboxed_repo_runs() -> None:
    text = _read("scripts/start-antigravity.ps1")

    assert "Get-Command agy" in text
    assert "--sandbox" in text
    assert "--add-dir" in text
    assert "Split-Path -Parent $PSScriptRoot" in text


def test_antigravity_launcher_blocks_unsafe_permission_bypass() -> None:
    text = _read("scripts/start-antigravity.ps1")

    assert "--dangerously-skip-permissions" in text
    assert "Unsafe Antigravity permission bypass is not allowed" in text


def test_antigravity_local_state_stays_untracked() -> None:
    gitignore = _read(".gitignore")

    assert ".gemini/" in gitignore
    assert ".antigravity/" in gitignore


def test_antigravity_setup_has_source_backed_spec_and_glossary() -> None:
    spec = _read("docs/specs/fr-antigravity-cli-repo-setup.md")
    glossary = _read("PLAIN-ENGLISH-RULE.md")

    assert "[SPEC FRESHNESS: reviewed_at=2026-05-26 next_review=2026-06-26]" in spec
    assert "https://www.antigravity.google/docs/cli-getting-started" in spec
    assert "Antigravity CLI command" in glossary
