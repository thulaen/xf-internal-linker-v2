"""Open-AutoIssue gate for GWP-ASan memory-safety findings.

GWP-ASan is a sampling memory-error detector for the C++ extensions. When
it catches a heap-buffer-overflow or use-after-free it lands as an
``AutoIssue(source='gwp_asan')``. This module asks the one question the
commit gate needs: are any of those still unresolved?

Thin wrapper over :mod:`apps.auto_issues.services.source_quota` so the
GWP-ASan, Perfetto, and CodeQL gates share one verified code path.
"""

from __future__ import annotations

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.source_quota import (
    open_issues_for_source,
    verify_source_quota,
)

GWP_ASAN_LABEL = "GWP-ASan"


def open_gwp_asan_issues():
    """Return unresolved GWP-ASan-backed AutoIssues."""
    return open_issues_for_source(AutoIssue.SOURCE_GWP_ASAN)


def verify_gwp_asan_autoissues(*, max_open: int, block_open: bool) -> list[AutoIssue]:
    """Return open GWP-ASan issues or raise when the commit must stop."""
    return verify_source_quota(
        source=AutoIssue.SOURCE_GWP_ASAN,
        label=GWP_ASAN_LABEL,
        max_open=max_open,
        block_open=block_open,
    )
