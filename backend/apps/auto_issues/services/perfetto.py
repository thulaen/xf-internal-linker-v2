"""Open-AutoIssue gate for Perfetto trace-analysis findings.

Perfetto is the system-wide tracing tool. When a trace shows a regression
(a slow span, a lock contention, a scheduling stall) it is filed as an
``AutoIssue(source='perfetto')``. This module asks whether any of those
remain unresolved at commit time.

Thin wrapper over :mod:`apps.auto_issues.services.source_quota` so the
Perfetto, GWP-ASan, and CodeQL gates share one verified code path.
"""

from __future__ import annotations

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.source_quota import (
    open_issues_for_source,
    verify_source_quota,
)

PERFETTO_LABEL = "Perfetto"


def open_perfetto_issues():
    """Return unresolved Perfetto-backed AutoIssues."""
    return open_issues_for_source(AutoIssue.SOURCE_PERFETTO)


def verify_perfetto_autoissues(*, max_open: int, block_open: bool) -> list[AutoIssue]:
    """Return open Perfetto issues or raise when the commit must stop."""
    return verify_source_quota(
        source=AutoIssue.SOURCE_PERFETTO,
        label=PERFETTO_LABEL,
        max_open=max_open,
        block_open=block_open,
    )
