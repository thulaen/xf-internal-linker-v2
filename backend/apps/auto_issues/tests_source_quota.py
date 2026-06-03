"""Tests for the shared per-source AutoIssue quota gate (GWP-ASan / Perfetto).

Given AutoIssues filed under a specific observability source,
When the per-source verify gate runs,
Then it returns open issues, enforces the max-open ceiling, and blocks on
any open issue when block_open is set.
"""

from __future__ import annotations

from django.test import TestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import gwp_asan, perfetto
from apps.auto_issues.services.source_quota import verify_source_quota


def _issue(source: str, *, status: str = AutoIssue.STATUS_OPEN) -> AutoIssue:
    return AutoIssue.objects.create(
        source=source,
        external_id=f"{source}-{AutoIssue.objects.count()}",
        title=f"{source} finding",
        status=status,
    )


class SourceQuotaTests(TestCase):
    def test_open_count_under_max_returns_issues(self) -> None:
        _issue(AutoIssue.SOURCE_GWP_ASAN)
        _issue(AutoIssue.SOURCE_GWP_ASAN)
        result = verify_source_quota(
            source=AutoIssue.SOURCE_GWP_ASAN,
            label="GWP-ASan",
            max_open=10,
            block_open=False,
        )
        self.assertEqual(len(result), 2)

    def test_over_max_raises(self) -> None:
        for _ in range(3):
            _issue(AutoIssue.SOURCE_GWP_ASAN)
        with self.assertRaisesMessage(ValueError, "above the maximum 2"):
            verify_source_quota(
                source=AutoIssue.SOURCE_GWP_ASAN,
                label="GWP-ASan",
                max_open=2,
                block_open=False,
            )

    def test_block_open_raises_when_any_open(self) -> None:
        _issue(AutoIssue.SOURCE_GWP_ASAN)
        with self.assertRaisesMessage(ValueError, "must be fixed or reviewed"):
            verify_source_quota(
                source=AutoIssue.SOURCE_GWP_ASAN,
                label="GWP-ASan",
                max_open=10,
                block_open=True,
            )

    def test_block_open_passes_when_all_resolved(self) -> None:
        _issue(AutoIssue.SOURCE_GWP_ASAN, status=AutoIssue.STATUS_RESOLVED)
        result = verify_source_quota(
            source=AutoIssue.SOURCE_GWP_ASAN,
            label="GWP-ASan",
            max_open=10,
            block_open=True,
        )
        self.assertEqual(result, [])

    def test_source_isolation(self) -> None:
        _issue(AutoIssue.SOURCE_PERFETTO)
        # A GWP-ASan check must not see a Perfetto issue.
        self.assertEqual(
            verify_source_quota(
                source=AutoIssue.SOURCE_GWP_ASAN,
                label="GWP-ASan",
                max_open=10,
                block_open=True,
            ),
            [],
        )


class GwpAsanWrapperTests(TestCase):
    def test_blocks_on_open(self) -> None:
        _issue(AutoIssue.SOURCE_GWP_ASAN)
        with self.assertRaises(ValueError):
            gwp_asan.verify_gwp_asan_autoissues(max_open=10, block_open=True)

    def test_passes_when_clean(self) -> None:
        self.assertEqual(
            gwp_asan.verify_gwp_asan_autoissues(max_open=10, block_open=True), []
        )


class PerfettoWrapperTests(TestCase):
    def test_blocks_on_open(self) -> None:
        _issue(AutoIssue.SOURCE_PERFETTO)
        with self.assertRaises(ValueError):
            perfetto.verify_perfetto_autoissues(max_open=10, block_open=True)

    def test_passes_when_clean(self) -> None:
        self.assertEqual(
            perfetto.verify_perfetto_autoissues(max_open=10, block_open=True), []
        )
