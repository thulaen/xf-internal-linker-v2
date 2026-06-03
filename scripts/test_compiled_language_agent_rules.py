"""Tests for cross-agent compiled-language build rules."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_RULE_FILES = ("AGENTS.md", "CLAUDE.md", "CODEX.md", "GEMINI.md")


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_all_agent_rulebooks_ban_host_cargo_and_require_docker_linux() -> None:
    for path in AGENT_RULE_FILES:
        text = _read(path)
        assert "Cargo and Rust builds/checks must run inside Docker-managed Linux containers" in text
        assert "Do not run `cargo` on Windows or the host shell" in text
        assert "Claude, Codex, Gemini" in text


def test_compiled_language_rulebook_names_cargo_docker_path() -> None:
    text = _read("COMPILED-LANGUAGE-RULES.md")

    assert "Cargo and Rust builds/checks run only inside Docker-managed Linux containers" in text
    assert "Do not run `cargo` from Windows PowerShell, Windows Terminal, WSL outside Docker" in text
    assert "scripts/invoke-mint-compiled-tools.ps1" in text
    assert "scripts/invoke-mint-compiled-tools.sh" in text
    assert "Do not run `docker compose run --rm compiled-tools ...`" in text


def test_agent_rulebooks_do_not_restart_moved_quality_services_on_windows() -> None:
    for path in AGENT_RULE_FILES:
        text = _read(path)
        assert "If a Windows-owned local-control-plane container is down" in text
        assert "scripts/check-mint-quality-tools.ps1 -Repair -SkipHaskell" in text
        assert "scripts/start-mint-glitchtip.ps1" in text
        assert "Do not start moved Mint services on Windows" in text
