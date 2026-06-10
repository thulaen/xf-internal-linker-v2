"""Verify the observability pipeline is actually feeding AutoIssues.

The observability containers (Loki, Pyroscope, GlitchTip, Tempo, vmalert,
SonarQube, ...) are useless if their findings never reach the AutoIssue
table. A container can be "healthy" while its picker is silently broken.

This module answers: for each observability source, has at least one
AutoIssue been seen (``last_seen``) within a recent window? A source that
has been silent for the whole window is *suspicious* — its picker may be
broken — but silence is not proof of breakage (the system may simply be
quiet), so callers treat it as a warning, not a hard block.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from apps.auto_issues.models import AutoIssue

# Sources that a running observability stack is expected to feed. These are
# the "problem-producing" sources, distinct from agent/test/CI sources.
OBSERVABILITY_SOURCES: tuple[str, ...] = (
    AutoIssue.SOURCE_GLITCHTIP,
    AutoIssue.SOURCE_PYROSCOPE,
    AutoIssue.SOURCE_TEMPO,
    AutoIssue.SOURCE_LOKI,
    AutoIssue.SOURCE_FARO,
    AutoIssue.SOURCE_VMALERT,
)


@dataclass(frozen=True)
class SourceFreshness:
    source: str
    recent_count: int
    is_silent: bool


def pipeline_freshness(
    *, hours: int = 24, sources: tuple[str, ...] = OBSERVABILITY_SOURCES
) -> list[SourceFreshness]:
    """Return per-source freshness over the last ``hours`` window."""
    cutoff = timezone.now() - timedelta(hours=hours)
    out: list[SourceFreshness] = []
    for source in sources:
        count = AutoIssue.objects.filter(
            source=source, last_seen__gte=cutoff
        ).count()
        out.append(
            SourceFreshness(source=source, recent_count=count, is_silent=count == 0)
        )
    return out


def silent_sources(
    *, hours: int = 24, sources: tuple[str, ...] = OBSERVABILITY_SOURCES
) -> list[str]:
    """Return the sources that produced no AutoIssue in the window."""
    return [f.source for f in pipeline_freshness(hours=hours, sources=sources) if f.is_silent]
