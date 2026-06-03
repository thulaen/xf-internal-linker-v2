"""Check the required agent chat outcome formats."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "agent_replies"

FINDINGS = r"(?:none|[1-9]\d* \((?:#\d+(?:, #\d+)*)\))"
CI_URL = r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/runs/\d+"

COMMIT_PUSH_SUCCESS = re.compile(
    rf"\A"
    r"Commit succeeded: [0-9a-f]{7}\n"
    r"Pushed to: [A-Za-z0-9._/-]+\n"
    rf"Findings filed: {FINDINGS}\n"
    rf"CI: triggered, {CI_URL}\n"
    r"Hard-floor checks: all passed\n"
    r"Status: ready for next change"
    rf"\Z"
)

COMMIT_ONLY_SUCCESS = re.compile(
    rf"\A"
    r"Commit succeeded: [0-9a-f]{7}\n"
    r"Pushed: not requested\n"
    rf"Findings filed: {FINDINGS}\n"
    r"Hard-floor checks: all passed\n"
    r"Status: ready for push or next change"
    rf"\Z"
)

COMMIT_BLOCKED = re.compile(
    r"\A"
    r"Commit blocked: [A-Za-z0-9_.-]+ .+\n"
    r"Findings filed: 1 \(#\d+ — commit_blocker\)\n"
    r"Push: skipped \(commit did not land\)\n"
    r"Suggested next: .+\n"
    r"Status: working tree still dirty, no commit"
    r"\Z"
)

PUSH_FAILED = re.compile(
    rf"\A"
    r"Commit succeeded: [0-9a-f]{7}\n"
    r"Push failed: .+\n"
    rf"Findings filed: {FINDINGS}\n"
    r"Suggested next: .+\n"
    r"Status: commit landed locally, push still needed"
    rf"\Z"
)

EDIT_ONLY = re.compile(
    r"\A"
    r"Files changed: (?:[^\n]+(?:, [^\n]+)*)\n"
    r"Not committed yet \(waiting for commit signal\)\n"
    r"Findings preview \(would file on commit\): \d+ across .+\n"
    r"Status: ready for review or commit"
    r"\Z"
)


def _fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8").strip()


def test_commit_success_format_regex() -> None:
    assert COMMIT_PUSH_SUCCESS.fullmatch(_fixture("commit_push_success.txt"))
    assert "abc1234" in _fixture("commit_push_success.txt")
    assert "#101, #102" in _fixture("commit_push_success.txt")


def test_commit_blocked_format_regex() -> None:
    sample = _fixture("commit_blocked.txt")
    assert COMMIT_BLOCKED.fullmatch(sample)
    assert "check-registry-read" in sample
    assert "commit_blocker" in sample


def test_push_success_includes_ci_link() -> None:
    sample = _fixture("commit_push_success.txt")
    assert COMMIT_PUSH_SUCCESS.fullmatch(sample)
    assert re.search(CI_URL, sample)


def test_push_failed_includes_reason() -> None:
    sample = _fixture("push_failed.txt")
    assert PUSH_FAILED.fullmatch(sample)
    assert "non-fast-forward" in sample


def test_edit_only_turn_status_line() -> None:
    assert EDIT_ONLY.fullmatch(_fixture("edit_only.txt"))


def test_commit_only_success_format_regex() -> None:
    assert COMMIT_ONLY_SUCCESS.fullmatch(_fixture("commit_only_success.txt"))


def test_missing_required_fields_fail_regex() -> None:
    missing_sha = _fixture("commit_push_success.txt").replace(
        "Commit succeeded: abc1234\n", ""
    )
    missing_findings = _fixture("commit_push_success.txt").replace(
        "Findings filed: 2 (#101, #102)\n", ""
    )
    missing_ci_link = _fixture("commit_push_success.txt").replace(
        "https://github.com/thulaen/xf-internal-linker-v2/actions/runs/987654321",
        "pending",
    )

    assert not COMMIT_PUSH_SUCCESS.fullmatch(missing_sha)
    assert not COMMIT_PUSH_SUCCESS.fullmatch(missing_findings)
    assert not COMMIT_PUSH_SUCCESS.fullmatch(missing_ci_link)


def test_agent_rule_documents_link_to_standard_section() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Trigger discipline and chat-notification protocol" in agents

    for name in ("CLAUDE.md", "CODEX.md", "GEMINI.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "Trigger discipline and chat-notification protocol" in text


def test_agents_contains_templates_verbatim() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    expected_templates = [
        "Commit succeeded: <sha7>\nPushed to: <branch>",
        "Commit succeeded: <sha7>\nPushed: not requested",
        "Commit blocked: <hook-name> <reason>",
        "Commit succeeded: <sha7>\nPush failed: <reason>",
        "Files changed: <list>\nNot committed yet (waiting for commit signal)",
    ]

    for template in expected_templates:
        assert template in agents
