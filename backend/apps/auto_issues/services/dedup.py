"""Cross-source dedup — one AutoIssue row per canonical fingerprint.

Pickers call `upsert_dedup(...)` instead of `AutoIssue.objects.update_or_create`.
The function:

  1. Looks up an existing OPEN row with the same `canonical_fingerprint`.
  2. If found:
     - merges the new source observation into `source_observations`,
     - bumps `occurrence_count`,
     - takes the higher of `priority_score`, max(severity), latest title,
     - never creates a duplicate.
  3. If not found:
     - creates a fresh row keyed by (source, external_id),
     - seeds `source_observations` with a single entry.

So when the same root cause is captured by GlitchTip + an internal
`ingest_error` + a Pyroscope regression, all three observations land on
ONE row with three entries in `source_observations`. Reading the
auto_issues table never shows duplicates of the same root cause.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils import timezone

from apps.auto_issues.models import AutoIssue


@dataclass(frozen=True)
class IssueObservation:
    """Inputs to `upsert_dedup` grouped into one struct.

    Replaces a 10-arg keyword call with a single arg. Same fields, just
    organised so each picker can build it once and pass it down without
    threading positional args through helpers.
    """

    canonical: str
    source: str
    external_id: str
    fingerprint: str
    title: str
    description: str
    affected_files: list
    severity: str
    priority_score: float
    occurrence_count: int


_SEVERITY_RANK = {
    AutoIssue.SEVERITY_CRITICAL: 4,
    AutoIssue.SEVERITY_HIGH: 3,
    AutoIssue.SEVERITY_MEDIUM: 2,
    AutoIssue.SEVERITY_LOW: 1,
}


def _max_severity(a: str, b: str) -> str:
    """Return whichever severity is more severe."""
    return a if _SEVERITY_RANK.get(a, 0) >= _SEVERITY_RANK.get(b, 0) else b


def _build_observation(
    *, source: str, external_id: str, occurrence_count: int, now
) -> dict:
    """One entry in the row's `source_observations` JSON list."""
    return {
        "source": source,
        "external_id": external_id,
        "first_seen": now.isoformat(),
        "last_seen": now.isoformat(),
        "occurrence_count": int(occurrence_count),
    }


def _merge_observation(observations: list, new: dict) -> list:
    """Merge `new` into the matching `(source, external_id)` entry in place.

    If no matching entry exists, append. Bumps `last_seen` +
    `occurrence_count` on the matching entry; preserves `first_seen`.
    """
    for obs in observations:
        if (
            obs.get("source") == new["source"]
            and obs.get("external_id") == new["external_id"]
        ):
            obs["last_seen"] = new["last_seen"]
            obs["occurrence_count"] = new["occurrence_count"]
            return observations
    observations.append(new)
    return observations


def _create_new_canonical_row(obs: IssueObservation, new_obs: dict, now) -> AutoIssue:
    """First-time-seen canonical → fresh AutoIssue row."""
    return AutoIssue.objects.create(
        source=obs.source,
        external_id=obs.external_id,
        fingerprint=obs.fingerprint,
        canonical_fingerprint=obs.canonical,
        title=obs.title[:512],
        description=obs.description[:4000],
        affected_files=obs.affected_files,
        severity=obs.severity,
        status=AutoIssue.STATUS_OPEN,
        priority_score=obs.priority_score,
        occurrence_count=obs.occurrence_count,
        last_seen=now,
        source_observations=[new_obs],
    )


def _merge_into_existing(
    existing: AutoIssue, obs: IssueObservation, new_obs: dict, now
) -> tuple[AutoIssue, str]:
    """Existing canonical row — merge new observation, escalate severity/score."""
    seen_before = any(
        o.get("source") == obs.source and o.get("external_id") == obs.external_id
        for o in (existing.source_observations or [])
    )
    existing.source_observations = _merge_observation(
        list(existing.source_observations or []), new_obs
    )
    existing.priority_score = max(existing.priority_score, obs.priority_score)
    existing.severity = _max_severity(existing.severity, obs.severity)
    existing.occurrence_count = sum(
        int(o.get("occurrence_count", 0)) for o in existing.source_observations
    )
    existing.last_seen = now
    if not existing.affected_files and obs.affected_files:
        existing.affected_files = obs.affected_files
    existing.save(update_fields=[
        "source_observations", "priority_score", "severity",
        "occurrence_count", "last_seen", "affected_files",
    ])
    return existing, "updated" if seen_before else "merged"


def upsert_dedup(**kwargs) -> tuple[AutoIssue, str]:
    """Single entry-point for pickers — returns (row, outcome_string).

    Accepts the same keyword args as `IssueObservation` for caller
    convenience. `outcome_string` is one of:
      'created' — new canonical-fingerprint row.
      'merged'  — existing row gained a new source observation.
      'updated' — existing row updated for the same (source, external_id).
    """
    obs = IssueObservation(**kwargs)
    now = timezone.now()
    new_obs = _build_observation(
        source=obs.source,
        external_id=obs.external_id,
        occurrence_count=obs.occurrence_count,
        now=now,
    )
    existing = (
        AutoIssue.objects
        .filter(canonical_fingerprint=obs.canonical)
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .first()
    )
    if existing is None:
        return _create_new_canonical_row(obs, new_obs, now), "created"
    return _merge_into_existing(existing, obs, new_obs, now)
