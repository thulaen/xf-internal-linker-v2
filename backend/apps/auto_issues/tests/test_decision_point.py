"""Tests for manage.py decision_point — Session S2 of the TDD-pipeline rule.

The command runs after every successful commit (via .githooks/post-commit)
and surfaces follow-up work in six fixed buckets:

  1. improvements_possible    — functions over 50 lines, etc.
  2. warnings                  — TO" "DO / FIX" "ME / XX" "X comments introduced
  3. problems                  — bare `except:`, hardcoded passwords, …
  4. missing_spec              — new feature / signal / weight / setting
                                 without a matching docs/specs/<id>.md
                                 citation
  5. off_track_test_case       — TEST CASE MAPPING marker references an
                                 AutoIssue(category='test_case') with
                                 fewer than 10 BDD fields filled
  6. off_track_tdd             — TDD CYCLE STRICT marker references an
                                 AutoIssue(category='tdd_lesson') with a
                                 weak (single-part) lessons_learned

Each finding is filed as `AutoIssue(category='decision_point',
source='post_commit', severity=…)` with structured lessons_learned.

The command prints a `[DECISION POINT: …]` marker for the handoff entry.

Tested behaviours (written FIRST per the strict-TDD rule the pipeline enforces):
"""

from __future__ import annotations

import re
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue, AutoIssueCategory


_MARKER_RE = re.compile(
    r"\[DECISION POINT:\s*"
    r"commit=(?P<commit>\S+)\s+"
    r"findings=(?P<findings>\d+)\s+"
    r"improvements=(?P<improvements>\d+)\s+"
    r"warnings=(?P<warnings>\d+)\s+"
    r"problems=(?P<problems>\d+)\s+"
    r"missing_spec=(?P<missing_spec>\d+)\s+"
    r"off_track_test_case=(?P<off_track_test_case>\d+)\s+"
    r"off_track_tdd=(?P<off_track_tdd>\d+)\s+"
    r"autoissues_filed=(?P<autoissues_filed>\S+)\s+"
    r"filed_at=(?P<filed_at>\S+)\]"
)


def _call(*args: str, diff: str = "", **kwargs) -> str:
    """Invoke manage.py decision_point with a mocked git-show diff."""
    out = StringIO()
    with mock.patch(
        "apps.auto_issues.management.commands.decision_point._git_show_diff",
        return_value=diff,
    ):
        call_command("decision_point", *args, stdout=out, **kwargs)
    return out.getvalue()


def _short_hash() -> str:
    return "abc1234"


class DecisionPointMarkerShapeTests(TestCase):

    def test_marker_emitted_for_clean_commit(self) -> None:
        # Clean diff: no findings. Marker still emitted with zero counts.
        diff = (
            "diff --git a/backend/apps/quiet.py b/backend/apps/quiet.py\n"
            "+def add(a, b):\n"
            "+    return a + b\n"
        )
        output = _call("--commit", _short_hash(), diff=diff)
        match = _MARKER_RE.search(output)
        self.assertIsNotNone(match, msg=f"missing marker in: {output!r}")
        self.assertEqual(int(match.group("findings")), 0)

    def test_marker_carries_filed_at_iso8601_utc(self) -> None:
        output = _call("--commit", _short_hash(), diff="+x = 1\n")
        match = _MARKER_RE.search(output)
        assert match is not None
        self.assertRegex(
            match.group("filed_at"),
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$",
        )

    def test_no_autoissues_when_diff_is_clean(self) -> None:
        before = AutoIssue.objects.filter(
            category__key="decision_point"
        ).count()
        _call("--commit", _short_hash(), diff="+x = 1\n")
        after = AutoIssue.objects.filter(
            category__key="decision_point"
        ).count()
        self.assertEqual(before, after)


class WarningsBucketTests(TestCase):

    def test_todo_comment_added_files_a_warning(self) -> None:
        diff = (
            "diff --git a/backend/apps/x.py b/backend/apps/x.py\n"
            "+def thing():\n"
            "+    # TO" "DO: revisit when the new API ships\n"
            "+    pass\n"
        )
        output = _call("--commit", _short_hash(), diff=diff)
        match = _MARKER_RE.search(output)
        assert match is not None
        self.assertGreaterEqual(int(match.group("warnings")), 1)
        # AutoIssue was filed.
        self.assertTrue(
            AutoIssue.objects.filter(
                category__key="decision_point",
                title__icontains="warning",
            ).exists()
        )

    def test_fixme_xxx_also_counted(self) -> None:
        diff = (
            "diff --git a/backend/apps/x.py b/backend/apps/x.py\n"
            "+# FIX" "ME: brittle\n"
            "+# XX" "X: ha" "ck\n"
        )
        output = _call("--commit", _short_hash(), diff=diff)
        match = _MARKER_RE.search(output)
        assert match is not None
        self.assertGreaterEqual(int(match.group("warnings")), 2)


class ProblemsBucketTests(TestCase):

    def test_bare_except_files_a_problem(self) -> None:
        diff = (
            "diff --git a/backend/apps/danger.py b/backend/apps/danger.py\n"
            "+try:\n"
            "+    do_thing()\n"
            "+except:\n"
            "+    pass\n"
        )
        output = _call("--commit", _short_hash(), diff=diff)
        match = _MARKER_RE.search(output)
        assert match is not None
        self.assertGreaterEqual(int(match.group("problems")), 1)

    def test_except_exception_pass_files_a_problem(self) -> None:
        diff = (
            "diff --git a/backend/apps/danger.py b/backend/apps/danger.py\n"
            "+try:\n"
            "+    do_thing()\n"
            "+except Exception:\n"
            "+    pass\n"
        )
        output = _call("--commit", _short_hash(), diff=diff)
        match = _MARKER_RE.search(output)
        assert match is not None
        self.assertGreaterEqual(int(match.group("problems")), 1)

    def test_except_exception_with_raise_does_not_file_a_problem(self) -> None:
        diff = (
            "diff --git a/backend/apps/safe.py b/backend/apps/safe.py\n"
            "+try:\n"
            "+    do_thing()\n"
            "+except Exception:\n"
            "+    raise\n"
        )
        output = _call("--commit", _short_hash(), diff=diff)
        match = _MARKER_RE.search(output)
        assert match is not None
        self.assertEqual(int(match.group("problems")), 0)


class ImprovementsBucketTests(TestCase):

    def test_long_function_files_an_improvement(self) -> None:
        # A function over 50 lines on a single staged file.
        body = "\n".join([f"+    x_{i} = {i}" for i in range(60)])
        diff = (
            "diff --git a/backend/apps/big.py b/backend/apps/big.py\n"
            "+def big():\n" + body + "\n"
        )
        output = _call("--commit", _short_hash(), diff=diff)
        match = _MARKER_RE.search(output)
        assert match is not None
        self.assertGreaterEqual(int(match.group("improvements")), 1)


class DryRunTests(TestCase):

    def test_dry_run_emits_marker_but_files_no_autoissues(self) -> None:
        diff = (
            "diff --git a/backend/apps/x.py b/backend/apps/x.py\n"
            "+# TO" "DO: dry run shouldnt persist this finding\n"
        )
        before = AutoIssue.objects.filter(
            category__key="decision_point"
        ).count()
        output = _call("--commit", _short_hash(), "--dry-run", diff=diff)
        # Dry-run uses a distinguishable marker so the post-commit hook
        # doesn't pretend a real run happened.
        self.assertIn("[DECISION POINT DRY-RUN", output)
        after = AutoIssue.objects.filter(
            category__key="decision_point"
        ).count()
        self.assertEqual(before, after)


class CategoryBootstrapTests(TestCase):

    def test_decision_point_category_exists_after_run(self) -> None:
        _call("--commit", _short_hash(), diff="+x = 1\n")
        self.assertTrue(
            AutoIssueCategory.objects.filter(key="decision_point").exists()
        )


class HelperFunctionTests(TestCase):
    """Unit tests for the private helper functions extracted from the
    high-complexity detect_* functions (SonarQube S3776 fixes)."""

    # --- _is_silent_except_exception ---

    def test_is_silent_except_exception_true_when_next_is_pass(self) -> None:
        from apps.auto_issues.management.commands.decision_point import (
            _is_silent_except_exception,
        )
        lines = [(1, "except Exception:"), (2, "    pass")]
        self.assertTrue(_is_silent_except_exception(lines, 0))

    def test_is_silent_except_exception_false_when_next_is_not_pass(self) -> None:
        from apps.auto_issues.management.commands.decision_point import (
            _is_silent_except_exception,
        )
        lines = [(1, "except Exception:"), (2, "    raise")]
        self.assertFalse(_is_silent_except_exception(lines, 0))

    def test_is_silent_except_exception_false_when_no_next_line(self) -> None:
        from apps.auto_issues.management.commands.decision_point import (
            _is_silent_except_exception,
        )
        lines = [(1, "except Exception:")]
        self.assertFalse(_is_silent_except_exception(lines, 0))

    # --- _extract_function_name ---

    def test_extract_function_name_returns_name_for_def(self) -> None:
        from apps.auto_issues.management.commands.decision_point import (
            _extract_function_name,
        )
        self.assertEqual(_extract_function_name("    def my_func(args):"), "my_func")

    def test_extract_function_name_returns_name_for_async_def(self) -> None:
        from apps.auto_issues.management.commands.decision_point import (
            _extract_function_name,
        )
        self.assertEqual(_extract_function_name("async def my_func():"), "my_func")

    def test_extract_function_name_returns_unknown_for_non_def(self) -> None:
        from apps.auto_issues.management.commands.decision_point import (
            _extract_function_name,
        )
        self.assertEqual(_extract_function_name("    class Foo:"), "<unknown>")

    # --- _append_long_function_finding ---

    def test_append_long_function_finding_adds_one_finding(self) -> None:
        from apps.auto_issues.management.commands.decision_point import (
            Finding,
            _append_long_function_finding,
        )
        findings: list[Finding] = []
        _append_long_function_finding(findings, "foo.py", "bar", 10, 55)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].bucket, "improvements")
        self.assertIn("bar", findings[0].detail)
        self.assertIn("56 lines", findings[0].detail)

    def test_append_long_function_finding_hint_contains_start_line(self) -> None:
        from apps.auto_issues.management.commands.decision_point import (
            Finding,
            _append_long_function_finding,
        )
        findings: list[Finding] = []
        _append_long_function_finding(findings, "foo.py", "baz", 42, 51)
        self.assertIn("42", findings[0].line_hint)
