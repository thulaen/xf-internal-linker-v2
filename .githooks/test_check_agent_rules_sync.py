"""Tests for shared agent-rule synchronization."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_sync(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/sync_agent_rules.py", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_manifest_exists_and_names_four_agent_files() -> None:
    manifest = ROOT / "docs/agent-rules-sync-manifest.yml"
    assert manifest.exists()
    text = manifest.read_text(encoding="utf-8")
    for path in ("CLAUDE.md", "AGENTS.md", "CODEX.md", "GEMINI.md"):
        assert path in text


def test_shared_sections_are_byte_identical() -> None:
    result = run_sync("--check")
    assert result.returncode == 0, result.stderr


def test_apply_mode_is_available() -> None:
    result = run_sync("--help")
    assert result.returncode == 0, result.stderr
    assert "--apply SOURCE_FILE" in result.stdout


def test_plan_40_41_42_rules_are_present_in_all_agent_files() -> None:
    result = run_sync("--verify-plan-40-41-42")
    assert result.returncode == 0, result.stderr


def test_forbidden_phrases_are_identical_across_agent_files() -> None:
    result = run_sync("--verify-forbidden-phrases")
    assert result.returncode == 0, result.stderr


def test_no_silent_disablement_rule_is_shared() -> None:
    manifest = ROOT / "docs/agent-rules-sync-manifest.yml"
    manifest_text = manifest.read_text(encoding="utf-8")
    assert "ABSOLUTE — No silent disablement" in manifest_text

    required = (
        "Anything disabled, moved behind a profile, made optional, stopped, "
        "removed, credential-blanked, or route-changed"
    )
    for path in ("CLAUDE.md", "AGENTS.md", "CODEX.md", "GEMINI.md"):
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "ABSOLUTE — No silent disablement" in text
        assert required in text


def test_shared_sections_stay_in_manifest_order_in_agent_files() -> None:
    manifest = ROOT / "docs/agent-rules-sync-manifest.yml"
    anchors = [
        line.strip()[3:].strip('"')
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("- \"ABSOLUTE")
    ]
    for path in ("CLAUDE.md", "AGENTS.md", "CODEX.md", "GEMINI.md"):
        text = (ROOT / path).read_text(encoding="utf-8")
        positions = [text.index(f"**{anchor}") for anchor in anchors]
        assert positions == sorted(positions), f"{path} shared sections are out of order"


def test_hook_reports_rule_f_on_drift() -> None:
    hook = ROOT / ".githooks/check-agent-rules-sync.py"
    assert hook.exists()
    result = subprocess.run(
        [sys.executable, str(hook), "--check-only"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
