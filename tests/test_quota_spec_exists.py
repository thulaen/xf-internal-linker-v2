"""Tests for the quota hard-block specification."""

from __future__ import annotations

from pathlib import Path


SPEC_PATH = Path("docs/specs/autoissue-quota-hard-block.md")


def test_spec_file_has_all_seven_sections_and_freshness_marker() -> None:
    text = SPEC_PATH.read_text(encoding="utf-8")

    required = [
        "[SPEC FRESHNESS: reviewed_at=2026-05-20 next_review=2026-06-20]",
        "## 1. Quota definition (non-substitutable)",
        "## 2. Session boundary detection",
        "## 3. Commit check",
        "## 4. Push check",
        "## 5. No bypass",
        "## 6. Drift handling",
        "## 7. Plain-English FAIL message",
        "The 10 SonarQube picks are mandatory. Resolving 40 cross-source AutoIssues does NOT satisfy the check - the SonarQube 10 must also be present.",
    ]
    for expected in required:
        assert expected in text
