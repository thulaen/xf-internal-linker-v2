"""Tests for manage.py session_close — Session S4 of the TDD-pipeline rule.

The command is run at session end. It:

  1. Verifies the staged AGENT-HANDOFF entry's TDD CYCLE STRICT markers
     all reference real resolved tdd_lesson AutoIssues (best-effort —
     the strict-TDD hook already enforces this at commit time; the
     session-close check is a final sweep).
  2. Delegates to `manage.py prune_test_artefacts --prefix <p>` for
     each of the six prefixes (mull / coverage / mutmut / stryker /
     fuzz-work / pytest-debug).
  3. Emits a `[SESSION CLOSE: …]` marker that the next session's
     `.githooks/check-session-close.py` hook validates.

Written FIRST (Red) per the strict-TDD rule the pipeline enforces.
"""

from __future__ import annotations

import re
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase


_MARKER_RE = re.compile(
    r"\[SESSION CLOSE:\s*"
    r"lessons_verified=(?P<lessons_verified>\d+)\s+"
    r"artefacts_pruned_mb=(?P<artefacts_pruned_mb>\d+(?:\.\d+)?)\s+"
    r"prefixes=(?P<prefixes>\S+)\s+"
    r"closed_at=(?P<closed_at>\S+)\]"
)


def _call(*args: str) -> str:
    out = StringIO()
    # Stub the pruner so tests don't touch /tmp on the host.
    with mock.patch(
        "apps.auto_issues.management.commands.session_close._prune_prefix",
        return_value=1.0,  # MiB freed per prefix
    ):
        call_command("session_close", *args, stdout=out)
    return out.getvalue()


class SessionCloseMarkerTests(TestCase):

    def test_marker_is_emitted(self) -> None:
        output = _call()
        self.assertIn("[SESSION CLOSE:", output)

    def test_marker_matches_full_shape(self) -> None:
        output = _call()
        match = _MARKER_RE.search(output)
        self.assertIsNotNone(match, msg=f"missing marker in: {output!r}")

    def test_marker_lists_all_six_prefixes(self) -> None:
        output = _call()
        match = _MARKER_RE.search(output)
        assert match is not None
        prefixes = match.group("prefixes").split(",")
        self.assertEqual(
            sorted(prefixes),
            sorted([
                "coverage", "fuzz-work", "mull", "mutmut",
                "pytest-debug", "stryker",
            ]),
        )

    def test_marker_closed_at_is_iso8601_utc(self) -> None:
        output = _call()
        match = _MARKER_RE.search(output)
        assert match is not None
        self.assertRegex(
            match.group("closed_at"),
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$",
        )

    def test_marker_reports_total_artefacts_pruned(self) -> None:
        # The mock returns 1.0 MiB freed per prefix × 6 prefixes = 6.0.
        output = _call()
        match = _MARKER_RE.search(output)
        assert match is not None
        self.assertEqual(float(match.group("artefacts_pruned_mb")), 6.0)


class SessionCloseDryRunTests(TestCase):

    def test_dry_run_does_not_emit_real_marker(self) -> None:
        out = StringIO()
        with mock.patch(
            "apps.auto_issues.management.commands.session_close._prune_prefix",
            return_value=1.0,
        ):
            call_command("session_close", "--dry-run", stdout=out)
        output = out.getvalue()
        self.assertIn("DRY-RUN", output)
        self.assertNotIn("[SESSION CLOSE:", output)
