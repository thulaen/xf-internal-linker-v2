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
        assert "Compiled-language builds, checks, runtime artifacts" in text
        assert "must use the Docker-managed path" in text
        assert "Do not require host compilers" in text
        assert "Claude, Codex, Gemini" in text


def test_compiled_language_rulebook_names_cargo_docker_path() -> None:
    text = _read("COMPILED-LANGUAGE-RULES.md")

    assert "Compiled languages must work through Docker without manual host builds" in text
    assert "Docker-managed artifact store" in text
    assert "Do not require host Visual Studio, host Go, host CMake, or host compiler tools" in text
    assert "`docker compose exec -T compiled-tools ...`" in text
    assert "If the tool container is not running yet, start it with" in text


def test_agent_rulebooks_do_not_restart_moved_quality_services_on_windows() -> None:
    for path in AGENT_RULE_FILES:
        text = _read(path)
        assert "Host split (updated 2026-06-05)" in text
        assert "scripts/check-dell-sonar-tools.ps1" in text
        assert "scripts/check-mint-quality-tools.ps1" in text
        assert "scripts/start-dell-sonar-tools.ps1" in text
        assert "not a local `docker compose up`" in text
