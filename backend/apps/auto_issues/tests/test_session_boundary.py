"""Tests for apps.auto_issues.services.session_boundary.

Covers the critical Bug 1 fix: previous_handoff_boundary() must return the
NEWEST (last) handoff entry, not the first (oldest) one.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.auto_issues.services.session_boundary import (
    _default_handoff_path,
    _handoff_candidates,
    previous_handoff_boundary,
)


class PreviousHandoffBoundaryTests(SimpleTestCase):
    def _write_temp(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        )
        f.write(content)
        f.close()
        return Path(f.name)

    def test_newest_entry_is_returned_not_oldest(self):
        """Bug 1 fix: matches[-1] must be used, not matches[0].

        AGENT-HANDOFF.md grows by appending at the bottom — the last match
        is the most recent session. Returning matches[0] gives the oldest
        session's timestamp, which makes verify_autoissue_quota accept
        resolutions from any session in history.
        """
        content = (
            "# 2026-01-01 10:00 - First ever session by claude\n"
            "Old session content.\n"
            "\n"
            "# 2026-03-15 09:00 - Second session\n"
            "Middle session content.\n"
            "\n"
            "# 2026-05-27 14:30 - Most recent session by claude\n"
            "Latest session content.\n"
        )
        path = self._write_temp(content)
        try:
            boundary = previous_handoff_boundary(handoff_path=path)
            self.assertEqual(boundary.display, "2026-05-27 14:30")
            self.assertFalse(boundary.grandfathered)
        finally:
            path.unlink()

    def test_single_entry_returned(self):
        content = "# 2026-05-20 08:00 - Solo session\nContent.\n"
        path = self._write_temp(content)
        try:
            boundary = previous_handoff_boundary(handoff_path=path)
            self.assertEqual(boundary.display, "2026-05-20 08:00")
            self.assertFalse(boundary.grandfathered)
        finally:
            path.unlink()

    def test_no_headers_returns_grandfathered(self):
        content = "Some prose with no headers at all.\n"
        path = self._write_temp(content)
        try:
            boundary = previous_handoff_boundary(handoff_path=path)
            self.assertIsNone(boundary.resolved_after)
            self.assertTrue(boundary.grandfathered)
            self.assertIn("grandfather", boundary.display)
        finally:
            path.unlink()

    def test_empty_file_returns_grandfathered(self):
        path = self._write_temp("")
        try:
            boundary = previous_handoff_boundary(handoff_path=path)
            self.assertTrue(boundary.grandfathered)
        finally:
            path.unlink()

    def test_resolved_after_is_aware_datetime(self):
        """The returned datetime must be timezone-aware (for comparisons with DB values)."""
        content = "# 2026-05-27 12:00 - Session\nContent.\n"
        path = self._write_temp(content)
        try:
            boundary = previous_handoff_boundary(handoff_path=path)
            self.assertIsNotNone(boundary.resolved_after)
            self.assertIsNotNone(boundary.resolved_after.tzinfo)
        finally:
            path.unlink()

    def test_oldest_two_entry_file_returns_second(self):
        content = (
            "# 2025-12-01 00:00 - Old session\nOld.\n\n"
            "# 2026-05-27 23:59 - New session\nNew.\n"
        )
        path = self._write_temp(content)
        try:
            boundary = previous_handoff_boundary(handoff_path=path)
            self.assertEqual(boundary.display, "2026-05-27 23:59")
        finally:
            path.unlink()


class DefaultHandoffPathTests(SimpleTestCase):
    """Tests for _default_handoff_path and _handoff_candidates (lines 44-57)."""

    def test_handoff_candidates_returns_three_paths(self):
        candidates = _handoff_candidates()
        self.assertEqual(len(candidates), 3)

    def test_handoff_candidates_includes_cwd_path(self):
        candidates = _handoff_candidates()
        self.assertIn(Path.cwd() / "AGENT-HANDOFF.md", candidates)

    def test_default_path_returns_existing_candidate(self):
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            existing = Path(f.name)
        try:
            with patch(
                "apps.auto_issues.services.session_boundary._handoff_candidates",
                return_value=(existing, Path("/nonexistent-x")),
            ):
                result = _default_handoff_path()
            self.assertEqual(result, existing)
        finally:
            existing.unlink()

    def test_default_path_falls_back_to_cwd_when_nothing_exists(self):
        with patch(
            "apps.auto_issues.services.session_boundary._handoff_candidates",
            return_value=(Path("/nonexistent-a"), Path("/nonexistent-b")),
        ):
            result = _default_handoff_path()
        self.assertEqual(result, Path.cwd() / "AGENT-HANDOFF.md")
