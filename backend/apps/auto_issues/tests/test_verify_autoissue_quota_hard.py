"""BDD-shaped tests for hard AutoIssue quota verification."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue


NON_SONARQUBE_SOURCES = (
    AutoIssue.SOURCE_AGENT,
    AutoIssue.SOURCE_GLITCHTIP,
    AutoIssue.SOURCE_PYROSCOPE,
    AutoIssue.SOURCE_TEMPO,
    AutoIssue.SOURCE_FARO,
    AutoIssue.SOURCE_MUTATION,
    AutoIssue.SOURCE_FUZZ,
    AutoIssue.SOURCE_CONTRACT,
    AutoIssue.SOURCE_GH_CI,
    AutoIssue.SOURCE_VMALERT,
)


class VerifyAutoIssueQuotaHardTests(TestCase):
    def test_both_quotas_met_with_full_sonarqube_exits_zero(self) -> None:
        cutoff = timezone.now() - timedelta(minutes=5)
        _create_cross_source_resolved(3)
        _create_resolved(AutoIssue.SOURCE_SONARQUBE, 10)
        _create_resolved(AutoIssue.SOURCE_RUST_DEFECT, 10)
        _create_resolved(AutoIssue.SOURCE_PPROF, 10)
        _create_resolved(AutoIssue.SOURCE_ALLOY, 10)
        _create_resolved(AutoIssue.SOURCE_LOKI, 7)
        _create_resolved(AutoIssue.SOURCE_PERFETTO, 10)
        _create_resolved(AutoIssue.SOURCE_GWP_ASAN, 10)

        out = StringIO()
        call_command(
            "verify_autoissue_quota",
            hard=True,
            resolved_after=_stamp(cutoff),
            stdout=out,
        )

        self.assertIn("[AUTOISSUE QUOTA VERIFIED: 97 resolved]", out.getvalue())

    def test_sonarqube_subquota_short_refuses_even_with_excess_cross_source(self) -> None:
        cutoff = timezone.now() - timedelta(minutes=5)
        _create_cross_source_resolved(4)
        _create_resolved(AutoIssue.SOURCE_RUST_DEFECT, 10)
        _create_resolved(AutoIssue.SOURCE_PPROF, 10)
        _create_resolved(AutoIssue.SOURCE_ALLOY, 10)
        _create_resolved(AutoIssue.SOURCE_PERFETTO, 10)
        _create_resolved(AutoIssue.SOURCE_GWP_ASAN, 10)

        with self.assertRaisesMessage(
            CommandError,
            "sonarqube: 0 of 10 resolved (NON-SUBSTITUTABLE - must come from source=sonarqube)",
        ):
            call_command(
                "verify_autoissue_quota",
                hard=True,
                resolved_after=_stamp(cutoff),
            )

    def test_partial_sonarqube_short_refuses(self) -> None:
        cutoff = timezone.now() - timedelta(minutes=5)
        _create_cross_source_resolved(3)
        _create_resolved(AutoIssue.SOURCE_SONARQUBE, 5)
        _create_resolved(AutoIssue.SOURCE_RUST_DEFECT, 10)
        _create_resolved(AutoIssue.SOURCE_PPROF, 10)
        _create_resolved(AutoIssue.SOURCE_ALLOY, 10)
        _create_resolved(AutoIssue.SOURCE_LOKI, 7)
        _create_resolved(AutoIssue.SOURCE_PERFETTO, 10)
        _create_resolved(AutoIssue.SOURCE_GWP_ASAN, 10)

        with self.assertRaisesMessage(
            CommandError,
            "sonarqube: 5 of 10 resolved (NON-SUBSTITUTABLE - must come from source=sonarqube)",
        ):
            call_command(
                "verify_autoissue_quota",
                hard=True,
                resolved_after=_stamp(cutoff),
            )

    def test_cross_source_bucket_short_refuses(self) -> None:
        cutoff = timezone.now() - timedelta(minutes=5)
        _create_resolved(AutoIssue.SOURCE_AGENT, 17)
        _create_resolved(AutoIssue.SOURCE_SONARQUBE, 10)
        _create_resolved(AutoIssue.SOURCE_RUST_DEFECT, 10)
        _create_resolved(AutoIssue.SOURCE_PPROF, 10)
        _create_resolved(AutoIssue.SOURCE_ALLOY, 10)
        _create_resolved(AutoIssue.SOURCE_LOKI, 7)
        _create_resolved(AutoIssue.SOURCE_PERFETTO, 10)
        _create_resolved(AutoIssue.SOURCE_GWP_ASAN, 10)

        with self.assertRaisesMessage(CommandError, "glitchtip: 0 of 3 resolved"):
            call_command(
                "verify_autoissue_quota",
                hard=True,
                resolved_after=_stamp(cutoff),
            )

    def test_stderr_includes_non_substitutable_note(self) -> None:
        cutoff = timezone.now() - timedelta(minutes=5)
        _create_cross_source_resolved(4)
        _create_resolved(AutoIssue.SOURCE_RUST_DEFECT, 10)
        _create_resolved(AutoIssue.SOURCE_PPROF, 10)
        _create_resolved(AutoIssue.SOURCE_ALLOY, 10)
        _create_resolved(AutoIssue.SOURCE_LOKI, 7)
        _create_resolved(AutoIssue.SOURCE_PERFETTO, 10)
        _create_resolved(AutoIssue.SOURCE_GWP_ASAN, 10)

        with self.assertRaises(CommandError) as raised:
            call_command(
                "verify_autoissue_quota",
                hard=True,
                resolved_after=_stamp(cutoff),
            )

        message = str(raised.exception)
        self.assertIn("CANNOT make up for the sonarqube shortfall", message)
        self.assertIn("UNBLOCK: resolve 10 more sonarqube AutoIssues", message)


def _create_cross_source_resolved(per_source: int) -> None:
    for source in NON_SONARQUBE_SOURCES:
        _create_resolved(source, per_source)


def _create_resolved(source: str, count: int) -> None:
    now = timezone.now()
    for index in range(count):
        AutoIssue.objects.create(
            source=source,
            external_id=f"hard-quota-{source}-{AutoIssue.objects.count()}-{index}",
            title=f"Given quota rows exist When source is {source} Then they count",
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=now,
            resolved_by="codex-test",
            lessons_learned="Trap: hard quota rows need two-part lessons. Fix shape: create resolved rows with lessons.",
        )


def _stamp(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M")
