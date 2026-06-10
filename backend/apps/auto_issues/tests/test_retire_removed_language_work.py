"""Tests for the retire_removed_language_work management command.

Given open AutoIssue + paper-trail rows, some tied to a REMOVED backend
language (Go / Haskell / Lua) and some that must be protected (Rust, Python,
C/C++ mid-port, live sidecar Python clients),
When retire_removed_language_work runs,
Then only the genuinely removed-language rows are classified for retirement,
the protected rows are left alone, and --apply closes them with an ADR-0007
note while --dry-run (the default) changes nothing.

Source of record for the policy: docs/adr/0007-python-rust-two-language.md.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.management.commands.retire_removed_language_work import (
    classify_removed_language,
)


class ClassifyRemovedLanguageTests(SimpleTestCase):
    """Pure-function classifier tests — no database needed."""

    def test_when_haskell_then_retirable(self) -> None:
        result = classify_removed_language(
            "Haskell service tier follow-up", "uses mucheck", AutoIssue.SOURCE_AGENT
        )
        self.assertEqual(result.language, "haskell")

    def test_when_lua_then_retirable(self) -> None:
        result = classify_removed_language(
            "Lua mutation tool wiring quarterly review", "", AutoIssue.SOURCE_AGENT
        )
        self.assertEqual(result.language, "lua")

    def test_when_go_service_tier_then_retirable(self) -> None:
        result = classify_removed_language(
            "go-mutesting survivor in services tier", "", AutoIssue.SOURCE_AGENT
        )
        self.assertEqual(result.language, "go")

    def test_when_rust_defect_source_then_protected(self) -> None:
        # Even if text mentions a removed language, rust_defect source is never retired.
        result = classify_removed_language(
            "go vet style finding", "", AutoIssue.SOURCE_RUST_DEFECT
        )
        self.assertIsNone(result.language)

    def test_when_cpp_then_protected_because_mid_port(self) -> None:
        result = classify_removed_language(
            "test_case: backend/extensions/papertrail_dedup.cpp",
            "C++ kernel",
            AutoIssue.SOURCE_AGENT,
        )
        self.assertIsNone(result.language)

    def test_when_rust_text_then_protected(self) -> None:
        result = classify_removed_language(
            "rust clippy lint in services/speccheck", "cargo", AutoIssue.SOURCE_AGENT
        )
        self.assertIsNone(result.language)

    def test_when_live_sidecar_python_client_then_protected(self) -> None:
        result = classify_removed_language(
            "test_case: backend/apps/auto_issues/_sidecars/searchd_client.py",
            "",
            AutoIssue.SOURCE_AGENT,
            affected_files=["backend/apps/auto_issues/_sidecars/searchd_client.py"],
        )
        self.assertIsNone(result.language)

    def test_when_pure_python_then_protected(self) -> None:
        result = classify_removed_language(
            "Fix N+1 query in apps.sources.services", "", AutoIssue.SOURCE_AGENT
        )
        self.assertIsNone(result.language)

    def test_when_evaluate_word_then_not_a_lua_match(self) -> None:
        # Regression: bare "lua" used to match inside "evaLUAte".
        result = classify_removed_language(
            "Parse Prometheus text and evaluate PostgreSQL health rules",
            "",
            AutoIssue.SOURCE_AGENT,
        )
        self.assertIsNone(result.language)

    def test_when_loki_go_stack_frame_then_protected(self) -> None:
        # Regression: ".go" used to match third-party observability Go binaries.
        result = classify_removed_language(
            "Loki: [hot_pattern] level=error caller=manager.go victoriametrics",
            "",
            AutoIssue.SOURCE_LOKI,
        )
        self.assertIsNone(result.language)


class RetireRemovedLanguageCommandTests(TestCase):
    """Database-backed command behaviour: dry-run vs apply, protection."""

    def _mk(self, title: str, source: str = AutoIssue.SOURCE_AGENT, files=None) -> AutoIssue:
        return AutoIssue.objects.create(
            source=source,
            external_id=f"ext-{title[:40]}",
            title=title,
            description="",
            affected_files=files or [],
            status=AutoIssue.STATUS_OPEN,
        )

    def test_dry_run_is_default_and_changes_nothing(self) -> None:
        issue = self._mk("Haskell services tier removal follow-up")
        out = StringIO()
        call_command("retire_removed_language_work", stdout=out)
        issue.refresh_from_db()
        self.assertEqual(issue.status, AutoIssue.STATUS_OPEN)
        self.assertIn("[REMOVED-LANGUAGE DRY-RUN:", out.getvalue())

    def test_apply_resolves_removed_language_issue_with_adr_note(self) -> None:
        issue = self._mk("Lua mutation tool wiring quarterly review")
        out = StringIO()
        call_command("retire_removed_language_work", "--apply", stdout=out)
        issue.refresh_from_db()
        self.assertEqual(issue.status, AutoIssue.STATUS_RESOLVED)
        self.assertIsNotNone(issue.resolved_at)
        self.assertIn("Trap:", issue.lessons_learned)
        self.assertIn("Fix shape:", issue.lessons_learned)
        self.assertIn("0007", issue.lessons_learned)
        self.assertIn("[REMOVED-LANGUAGE RETIRED:", out.getvalue())

    def test_apply_protects_rust_python_and_cpp(self) -> None:
        rust = self._mk("go vet finding", source=AutoIssue.SOURCE_RUST_DEFECT)
        cpp = self._mk("test_case: backend/extensions/linkparse.cpp")
        py = self._mk("Fix serializer bug in apps.audit")
        call_command("retire_removed_language_work", "--apply")
        for row in (rust, cpp, py):
            row.refresh_from_db()
            self.assertEqual(row.status, AutoIssue.STATUS_OPEN, row.title)
