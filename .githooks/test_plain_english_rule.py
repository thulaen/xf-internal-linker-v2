"""Tests for plain-English response rules."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_decision_point_completion_line_required() -> None:
    text = (ROOT / "PLAIN-ENGLISH-RULE.md").read_text(encoding="utf-8")
    assert "Decision Point line" in text
    assert "every task-complete chat response" in text
