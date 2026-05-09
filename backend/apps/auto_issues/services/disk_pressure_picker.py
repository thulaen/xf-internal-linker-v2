"""Disk-pressure → AutoIssue picker.

Closes Gap #5 from `docs/OBSERVABILITY-GAPS-EXTENSION.md`. Neither
GlitchTip nor Pyroscope catches disk-fill conditions until something
crashes with `OSError: No space left on device`. This picker reads
filesystem free-space for the volumes that matter and emits an AutoIssue
ahead of the wall.

Volumes monitored:
  /                       — container root (catches log + tmp growth)
  /var/lib/postgresql/data — pgdata (only inside the postgres container,
                              not the backend; we proxy via psql)
  /data                   — Pyroscope storage (similarly proxied)

The picker runs INSIDE the backend container so it sees the backend's
view of the filesystem. For the named volumes attached to OTHER services
we query Postgres for the pgdata size and Pyroscope's disk usage by
inspection, but as a v1 we keep it simple — only check what's directly
mounted on the backend container. Future extension: add a single Celery
task running on each container.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _DiskCheck:
    name: str
    path: str
    warn_pct: float
    crit_pct: float


# Each entry: (label, path, warn-threshold-pct-used, critical-pct-used).
# Warn → severity=medium ; Critical → severity=high.
_TARGETS: tuple[_DiskCheck, ...] = (
    _DiskCheck("backend-root", "/", warn_pct=80.0, crit_pct=92.0),
    _DiskCheck("backend-tmp", "/tmp", warn_pct=85.0, crit_pct=95.0),
    _DiskCheck("repo-mount", "/repo", warn_pct=85.0, crit_pct=95.0),
)


def _measure(target: _DiskCheck) -> tuple[float, int, int] | None:
    """Returns (used_pct, free_bytes, total_bytes) or None if path missing."""
    try:
        usage = shutil.disk_usage(target.path)
    except (FileNotFoundError, PermissionError) as exc:
        logger.warning(
            "[disk_pressure_picker] cannot stat %s: %s", target.path, exc
        )
        return None
    used_pct = (usage.used / usage.total) * 100.0 if usage.total else 0.0
    return used_pct, usage.free, usage.total


def _severity_for(used_pct: float, target: _DiskCheck) -> str | None:
    """Return severity if used_pct crosses warn/crit; None to skip."""
    if used_pct >= target.crit_pct:
        return AutoIssue.SEVERITY_HIGH
    if used_pct >= target.warn_pct:
        return AutoIssue.SEVERITY_MEDIUM
    return None


def _upsert_disk_issue(
    target: _DiskCheck, used_pct: float, free_bytes: int, total_bytes: int
) -> str:
    severity = _severity_for(used_pct, target)
    if severity is None:
        return "skip"
    title = (
        f"Disk pressure: {target.name} at {used_pct:.0f}% "
        f"({free_bytes / 1e9:.1f} GB free of {total_bytes / 1e9:.1f} GB)"
    )
    description = (
        f"Volume `{target.path}` is {used_pct:.1f}% full. Warn threshold "
        f"{target.warn_pct:.0f}%, critical {target.crit_pct:.0f}%. Free "
        f"space: {free_bytes / 1e9:.2f} GB. Without intervention, future "
        f"writes (logs, embeddings, media) will fail with `OSError: No "
        f"space left on device`. Recommended actions: prune Docker "
        f"images / volumes, rotate old logs, run `manage.py prune_*` "
        f"commands, OR expand the underlying disk."
    )
    canonical = canonical_fingerprint(f"disk-pressure::{target.name}", "")
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"disk-{target.name}",
        fingerprint=f"disk-{target.name}",
        title=title,
        description=description,
        affected_files=[],
        severity=severity,
        priority_score=0.85 if severity == AutoIssue.SEVERITY_HIGH else 0.5,
        occurrence_count=1,
    )
    return outcome


def pick_disk_pressure() -> dict:
    """Walk the watched paths, surface any over warn/crit threshold."""
    counts = {"created": 0, "merged": 0, "updated": 0, "skip": 0}
    measured = 0
    for target in _TARGETS:
        result = _measure(target)
        if result is None:
            continue
        measured += 1
        used_pct, free_bytes, total_bytes = result
        outcome = _upsert_disk_issue(target, used_pct, free_bytes, total_bytes)
        counts[outcome] = counts.get(outcome, 0) + 1
    logger.info(
        "[auto_issues.disk_pressure_picker] measured=%d created=%d merged=%d updated=%d below_threshold=%d",
        measured, counts["created"], counts["merged"], counts["updated"], counts["skip"],
    )
    return {
        "status": "ok",
        "measured": measured,
        "promoted": counts["created"] + counts["merged"] + counts["updated"],
        **counts,
    }
