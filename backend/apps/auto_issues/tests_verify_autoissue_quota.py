"""Tests for the AutoIssue quota verifier management command."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue

_DEFAULT_RESOLVED_AT = object()


class VerifyAutoIssueQuotaCommandTests(TestCase):
    def test_thirty_resolved_issues_with_lessons_pass(self) -> None:
        issue_ids = _create_resolved_issues(30)
        out = StringIO()
        call_command("verify_autoissue_quota", ids=issue_ids, stdout=out)
        self.assertIn("30 resolved", out.getvalue())

    def test_twenty_nine_issues_fail(self) -> None:
        issue_ids = _create_resolved_issues(29)
        with self.assertRaisesMessage(CommandError, "Expected 30 picked AutoIssues"):
            call_command("verify_autoissue_quota", ids=issue_ids)

    def test_duplicate_issue_id_fails(self) -> None:
        issue_ids = _create_resolved_issues(29)
        issue_ids.append(issue_ids[0])
        with self.assertRaisesMessage(CommandError, "Duplicate picked AutoIssue IDs"):
            call_command("verify_autoissue_quota", ids=issue_ids)

    def test_duplicate_canonical_work_fails(self) -> None:
        issue_ids = _create_resolved_issues(30)
        AutoIssue.objects.filter(id__in=issue_ids[:2]).update(
            canonical_fingerprint="same-autoissue-root"
        )
        with self.assertRaisesMessage(CommandError, "Duplicate picked AutoIssue work"):
            call_command("verify_autoissue_quota", ids=issue_ids)

    def test_open_issue_fails(self) -> None:
        issue_ids = _create_resolved_issues(29)
        open_issue = _create_issue(status=AutoIssue.STATUS_OPEN)
        issue_ids.append(str(open_issue.id))
        with self.assertRaisesMessage(CommandError, f"#{open_issue.id} is open"):
            call_command("verify_autoissue_quota", ids=issue_ids)

    def test_resolved_issue_without_lessons_fails(self) -> None:
        issue_ids = _create_resolved_issues(29)
        empty_lesson = _create_issue(lessons_learned="")
        issue_ids.append(str(empty_lesson.id))
        with self.assertRaisesMessage(CommandError, "has no lessons_learned note"):
            call_command("verify_autoissue_quota", ids=issue_ids)

    def test_missing_resolved_time_fails(self) -> None:
        issue_ids = _create_resolved_issues(29)
        missing_time = _create_issue()
        AutoIssue.objects.filter(id=missing_time.id).update(resolved_at=None)
        issue_ids.append(str(missing_time.id))
        with self.assertRaisesMessage(CommandError, "has no resolved_at time"):
            call_command("verify_autoissue_quota", ids=issue_ids)

    def test_issue_resolved_before_previous_handoff_fails(self) -> None:
        old_time = timezone.now() - timedelta(days=2)
        issue_ids = _create_resolved_issues(29)
        old_issue = _create_issue(resolved_at=old_time)
        issue_ids.append(str(old_issue.id))
        yesterday = (timezone.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        with self.assertRaisesMessage(CommandError, "before the previous handoff"):
            call_command(
                "verify_autoissue_quota",
                ids=issue_ids,
                resolved_after=yesterday,
            )

    def test_non_numeric_id_fails(self) -> None:
        with self.assertRaisesMessage(CommandError, "must be a number"):
            call_command("verify_autoissue_quota", ids=["abc"])

    def test_invalid_resolved_after_fails(self) -> None:
        issue_ids = _create_resolved_issues(30)
        with self.assertRaisesMessage(CommandError, "YYYY-MM-DD HH:MM"):
            call_command(
                "verify_autoissue_quota",
                ids=issue_ids,
                resolved_after="not-a-date",
            )

    def test_missing_issue_id_fails(self) -> None:
        issue_ids = _create_resolved_issues(29)
        issue_ids.append("999999")
        with self.assertRaisesMessage(CommandError, "do not exist"):
            call_command("verify_autoissue_quota", ids=issue_ids)

    def test_missing_ids_without_hard_flag_fails(self) -> None:
        # Line 136: with neither --hard nor --ids, the command refuses.
        with self.assertRaisesMessage(
            CommandError, "--ids is required unless --hard is used."
        ):
            call_command("verify_autoissue_quota")

    def test_hard_docs_session_type_passes_with_no_quota(self) -> None:
        # Lines 117-121: --hard --session-type docs short-circuits to a
        # success marker and requires no resolved issues at all.
        out = StringIO()
        call_command(
            "verify_autoissue_quota",
            hard=True,
            session_type="docs",
            stdout=out,
        )
        self.assertIn(
            "[AUTOISSUE QUOTA VERIFIED: docs — no quota required]", out.getvalue()
        )


class HardQuotaTests(TestCase):
    """Tests for _hard_quota_errors() — Fixes 5, 6, and 7."""

    def _counts(self, **overrides) -> dict:
        """Build a counts dict that satisfies all hard requirements by default."""
        from apps.auto_issues.management.commands.verify_autoissue_quota import (
            REQUIRED_RUST_DEFECT_FIXES,
            REQUIRED_ALLOY_FIXES,
            REQUIRED_LOKI_HARD_FIXES,
            REQUIRED_LIGHTHOUSE_FIXES,
            REQUIRED_PG_STAT_FIXES,
        )
        base = {
            AutoIssue.SOURCE_RUST_DEFECT: REQUIRED_RUST_DEFECT_FIXES,
            AutoIssue.SOURCE_ALLOY: REQUIRED_ALLOY_FIXES,
            AutoIssue.SOURCE_LOKI: REQUIRED_LOKI_HARD_FIXES,
            AutoIssue.SOURCE_LIGHTHOUSE: REQUIRED_LIGHTHOUSE_FIXES,
            AutoIssue.SOURCE_PG_STAT: REQUIRED_PG_STAT_FIXES,
            AutoIssue.SOURCE_AGENT: 3,
            AutoIssue.SOURCE_GLITCHTIP: 3,
            AutoIssue.SOURCE_PYROSCOPE: 3,
            AutoIssue.SOURCE_TEMPO: 3,
            AutoIssue.SOURCE_FARO: 3,
            AutoIssue.SOURCE_MUTATION: 3,
            AutoIssue.SOURCE_FUZZ: 3,
            AutoIssue.SOURCE_CONTRACT: 3,
            AutoIssue.SOURCE_GH_CI: 3,
            AutoIssue.SOURCE_VMALERT: 3,
        }
        base.update(overrides)
        return base

    # ── Fix 5: lighthouse + pg_stat enforcement ────────────────────────

    def test_hard_quota_fails_when_lighthouse_below_threshold(self):
        """AutoIssue Fix 5: lighthouse was in REQUIRED_LIGHTHOUSE_FIXES but never enforced."""
        from apps.auto_issues.management.commands.verify_autoissue_quota import (
            _hard_quota_errors,
        )
        _create_open_issue(AutoIssue.SOURCE_LIGHTHOUSE)
        counts = self._counts(**{AutoIssue.SOURCE_LIGHTHOUSE: 0})
        errors = _hard_quota_errors(counts)
        self.assertTrue(
            any("lighthouse" in e.lower() for e in errors),
            f"Expected lighthouse in errors but got: {errors}",
        )

    def test_hard_quota_fails_when_pg_stat_below_threshold(self):
        """AutoIssue Fix 5: pg_stat was in REQUIRED_PG_STAT_FIXES but never enforced."""
        from apps.auto_issues.management.commands.verify_autoissue_quota import (
            _hard_quota_errors,
        )
        _create_open_issue(AutoIssue.SOURCE_PG_STAT)
        counts = self._counts(**{AutoIssue.SOURCE_PG_STAT: 0})
        errors = _hard_quota_errors(counts)
        self.assertTrue(
            any("pg_stat" in e.lower() for e in errors),
            f"Expected pg_stat in errors but got: {errors}",
        )

    def test_hard_quota_passes_when_all_requirements_met(self):
        """Sanity: meeting all requirements must produce no errors."""
        from apps.auto_issues.management.commands.verify_autoissue_quota import (
            _hard_quota_errors,
        )
        errors = _hard_quota_errors(self._counts())
        self.assertEqual(errors, [], f"Unexpected errors: {errors}")

    # ── Fix 6: remove unused resolved_after parameter ─────────────────

    def test_hard_quota_errors_signature_accepts_counts_only(self):
        """AutoIssue Fix 6: _hard_quota_errors takes only counts after the fix."""
        import inspect
        from apps.auto_issues.management.commands.verify_autoissue_quota import (
            _hard_quota_errors,
        )
        sig = inspect.signature(_hard_quota_errors)
        params = list(sig.parameters.keys())
        self.assertNotIn(
            "resolved_after",
            params,
            "_hard_quota_errors must not have a resolved_after parameter after Fix 6",
        )
        self.assertEqual(params, ["counts"], f"Expected only 'counts', got {params}")



    def test_hard_quota_passes_when_live_mandatory_bucket_is_dry(self):
        """A mandatory bucket with no open work cannot block the commit."""
        from apps.auto_issues.management.commands.verify_autoissue_quota import (
            _hard_quota_errors,
        )
        counts = self._counts(**{AutoIssue.SOURCE_ALLOY: 0})
        errors = _hard_quota_errors(counts)
        self.assertEqual(errors, [], f"Dry hard bucket must be exempt; got: {errors}")

    def test_hard_quota_ignores_retired_native_observability_source(self):
        """Retired removed-runtime observability sources no longer block commits."""
        from apps.auto_issues.management.commands.verify_autoissue_quota import (
            _hard_quota_errors,
        )
        _create_open_issue(AutoIssue.SOURCE_PPROF)
        _create_open_issue(AutoIssue.SOURCE_PERFETTO)
        _create_open_issue(AutoIssue.SOURCE_GWP_ASAN)
        counts = self._counts(
            **{
                AutoIssue.SOURCE_PPROF: 0,
                AutoIssue.SOURCE_PERFETTO: 0,
                AutoIssue.SOURCE_GWP_ASAN: 0,
            }
        )
        errors = _hard_quota_errors(counts)
        self.assertEqual(errors, [], f"Retired hard sources must not block: {errors}")

    def test_hard_quota_requires_only_available_open_work(self):
        """If fewer issues exist than the quota, resolving those available rows is enough."""
        from apps.auto_issues.management.commands.verify_autoissue_quota import (
            _hard_quota_errors,
        )
        first = _create_open_issue(AutoIssue.SOURCE_ALLOY)
        second = _create_open_issue(AutoIssue.SOURCE_ALLOY)
        counts = self._counts(**{AutoIssue.SOURCE_ALLOY: 0})
        errors = _hard_quota_errors(counts)
        self.assertTrue(
            any("alloy: 0 of 2 available resolved" in e for e in errors),
            f"Expected available-work shortfall, got: {errors}",
        )

        AutoIssue.objects.filter(id__in=[first.id, second.id]).update(
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=timezone.now(),
            resolved_by="codex-test",
            lessons_learned="Trap: available rows were finite.\nFix shape: resolved all available rows.",
        )
        counts = self._counts(**{AutoIssue.SOURCE_ALLOY: 2})
        errors = _hard_quota_errors(counts)
        self.assertEqual(errors, [], f"Available hard-bucket work is resolved: {errors}")


class ScaledRequirementsTests(TestCase):
    """Tests for _scaled_requirements — session-type quota scaling (Increment 0)."""

    def _import(self):
        from apps.auto_issues.management.commands.verify_autoissue_quota import (
            _scaled_requirements,
            _HARD_SOURCE_REQUIREMENTS,
            _CROSS_SOURCE_REQUIREMENTS,
        )
        return _scaled_requirements, _HARD_SOURCE_REQUIREMENTS, _CROSS_SOURCE_REQUIREMENTS

    def test_docs_returns_all_zero(self):
        fn, hard, cross = self._import()
        h, c = fn("docs")
        self.assertEqual(sum(h.values()), 0, "docs: all hard reqs must be 0")
        self.assertEqual(sum(c.values()), 0, "docs: all cross reqs must be 0")

    def test_reconciliation_hard_all_zero(self):
        fn, hard, cross = self._import()
        h, c = fn("reconciliation")
        self.assertEqual(sum(h.values()), 0, "reconciliation: hard buckets must be 0")

    def test_reconciliation_cross_all_one(self):
        fn, hard, cross = self._import()
        h, c = fn("reconciliation")
        for src, req in c.items():
            self.assertEqual(req, 1, f"reconciliation: {src} cross-req must be 1, got {req}")

    def test_reconciliation_total_ten(self):
        fn, hard, cross = self._import()
        h, c = fn("reconciliation")
        self.assertEqual(sum(c.values()), 10, "reconciliation: total cross-source must be 10")

    def test_infrastructure_hard_all_zero(self):
        fn, hard, cross = self._import()
        h, c = fn("infrastructure")
        self.assertEqual(sum(h.values()), 0, "infrastructure: hard buckets must be 0")

    def test_infrastructure_cross_all_two(self):
        fn, hard, cross = self._import()
        h, c = fn("infrastructure")
        for src, req in c.items():
            self.assertEqual(req, 2, f"infrastructure: {src} cross-req must be 2, got {req}")

    def test_infrastructure_total_twenty(self):
        fn, hard, cross = self._import()
        h, c = fn("infrastructure")
        self.assertEqual(sum(c.values()), 20, "infrastructure: total cross-source must be 20")

    def test_feature_matches_full_quotas(self):
        fn, hard, cross = self._import()
        h, c = fn("feature")
        self.assertEqual(h, hard, "feature: hard reqs must match full quota")
        self.assertEqual(c, cross, "feature: cross reqs must match full quota")

    def test_feature_hard_quotas_exclude_retired_native_observability_sources(self):
        fn, hard, cross = self._import()
        h, c = fn("feature")
        self.assertNotIn(AutoIssue.SOURCE_PPROF, h)
        self.assertNotIn(AutoIssue.SOURCE_PERFETTO, h)
        self.assertNotIn(AutoIssue.SOURCE_GWP_ASAN, h)

    def test_hard_flag_reconciliation_passes_with_ten_cross_source(self):
        """verify_autoissue_quota --hard --session-type reconciliation accepts 1-per-cross-source."""
        from apps.auto_issues.management.commands.verify_autoissue_quota import (
            _hard_quota_errors_scaled,
            _scaled_requirements,
            _CROSS_SOURCE_REQUIREMENTS,
        )
        h, c = _scaled_requirements("reconciliation")
        # One resolved issue per cross-source satisfies reconciliation requirements.
        counts = {src: 1 for src in _CROSS_SOURCE_REQUIREMENTS}
        errors = _hard_quota_errors_scaled(counts, h, c)
        self.assertEqual(errors, [], f"Expected no errors, got: {errors}")

    def test_hard_flag_reconciliation_fails_with_zero_cross_source(self):
        """Reconciliation quota fails when a bucket HAS open issues but none resolved.

        The shortfall must be reported for buckets that have resolvable open
        work; the genuine-drought exemption only spares buckets that are empty.
        """
        from apps.auto_issues.management.commands.verify_autoissue_quota import (
            _hard_quota_errors_scaled,
            _scaled_requirements,
            _CROSS_SOURCE_REQUIREMENTS,
        )
        # Give every cross-source bucket an OPEN issue so none is "dry"; then
        # resolve none, so the quota must report every bucket short.
        for src in _CROSS_SOURCE_REQUIREMENTS:
            AutoIssue.objects.create(
                source=src,
                external_id=f"open-{src}",
                title=f"open {src} issue",
                status=AutoIssue.STATUS_OPEN,
            )
        h, c = _scaled_requirements("reconciliation")
        counts: dict = {}  # no resolved issues at all
        errors = _hard_quota_errors_scaled(counts, h, c)
        self.assertGreater(len(errors), 0, "Expected errors with zero resolved cross-source")

    def test_reconciliation_dry_cross_source_bucket_is_exempt(self):
        """A cross-source bucket with NO open issues is exempt in reconciliation.

        Regression: the genuine-drought exemption was gated on
        `required == _CROSS_SOURCE_FIXES` (3, the feature-mode value), so it
        never fired for reconciliation (required=1) or infrastructure (2).
        That made every reconciliation commit impossible whenever pyroscope /
        fuzz / contract were legitimately empty — you cannot resolve issues
        that do not exist. The exemption must apply for any scaled requirement.
        """
        from apps.auto_issues.management.commands.verify_autoissue_quota import (
            _hard_quota_errors_scaled,
            _scaled_requirements,
            _CROSS_SOURCE_REQUIREMENTS,
        )
        # Empty DB: every cross-source bucket is dry (0 open issues).
        h, c = _scaled_requirements("reconciliation")
        counts: dict = {}  # nothing resolved, but nothing exists to resolve
        errors = _hard_quota_errors_scaled(counts, h, c)
        self.assertEqual(
            errors, [], f"Dry cross-source buckets must be exempt; got: {errors}"
        )

    def test_feature_cross_source_requires_only_available_open_work(self):
        """Feature mode adapts cross-source quotas to available rows."""
        from apps.auto_issues.management.commands.verify_autoissue_quota import (
            _hard_quota_errors_scaled,
            _scaled_requirements,
            _CROSS_SOURCE_REQUIREMENTS,
        )
        _create_open_issue(AutoIssue.SOURCE_PYROSCOPE)
        h, c = _scaled_requirements("feature")
        counts = {src: 3 for src in _CROSS_SOURCE_REQUIREMENTS}
        counts[AutoIssue.SOURCE_PYROSCOPE] = 0
        errors = _hard_quota_errors_scaled(counts, h, c)
        self.assertTrue(
            any("pyroscope: 0 of 1 available resolved" in e for e in errors),
            f"Expected one available pyroscope row to block; got: {errors}",
        )

        AutoIssue.objects.filter(source=AutoIssue.SOURCE_PYROSCOPE).update(
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=timezone.now(),
            resolved_by="codex-test",
            lessons_learned="Trap: one row was available.\nFix shape: resolved the one row.",
        )
        counts[AutoIssue.SOURCE_PYROSCOPE] = 1
        errors = _hard_quota_errors_scaled(counts, h, c)
        self.assertEqual(errors, [], f"Resolved available cross-source row: {errors}")


def _create_resolved_issues(count: int) -> list[str]:
    return [str(_create_issue().id) for _ in range(count)]


def _create_issue(
    *,
    status: str = AutoIssue.STATUS_RESOLVED,
    resolved_at=_DEFAULT_RESOLVED_AT,
    lessons_learned: str = "Trap: test trap.\nFix shape: test fix.",
) -> AutoIssue:
    if resolved_at is _DEFAULT_RESOLVED_AT and status == AutoIssue.STATUS_RESOLVED:
        resolved_at = timezone.now()
    if resolved_at is _DEFAULT_RESOLVED_AT:
        resolved_at = None
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"quota-test-{AutoIssue.objects.count()}",
        title="Quota verifier test issue",
        status=status,
        resolved_at=resolved_at,
        resolved_by="codex-test",
        lessons_learned=lessons_learned,
    )


def _create_open_issue(source: str) -> AutoIssue:
    return AutoIssue.objects.create(
        source=source,
        external_id=f"open-{source}-{AutoIssue.objects.count()}",
        title=f"Open {source} quota issue",
        status=AutoIssue.STATUS_OPEN,
    )
