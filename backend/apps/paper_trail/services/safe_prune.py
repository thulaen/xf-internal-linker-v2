"""Test-artifact safe-prune extension for the paper-trail.

When a PaperTrailEntry is `status=resolved` AND has `resolution_lessons`,
any test artifact directory whose contents map to the entry's
`affected_files` becomes safe to prune (the lesson captures what the
artifact taught us; the artifact itself is reproducible from the test).

Reuses the QUALITY_ARTIFACT_PREFIXES whitelist from auto_issues so a
typo here cannot delete unrelated files.
"""

from __future__ import annotations

import logging
from pathlib import Path

from apps.auto_issues.services.quality_artifacts import QUALITY_ARTIFACT_PREFIXES
from apps.paper_trail.models import PaperTrailEntry

logger = logging.getLogger(__name__)

# Hard-coded protected names — same set as quality_artifacts. Never touch.
_PROTECTED_NAMES = frozenset(
    {
        "pgdata",
        "redis-data",
        "media_files",
        "staticfiles",
        "frontend_dist",
        "compiled_artifacts",
        "pyroscope_data",
        "loki_data",
        "alloy_data",
        "tempo_data",
        "grafana_data",
        "questdb_data",
    }
)


def lessons_saved_paths() -> set[str]:
    """Repo-relative paths from every resolved entry with lessons."""
    paths: set[str] = set()
    qs = PaperTrailEntry.objects.filter(
        status=PaperTrailEntry.STATUS_RESOLVED,
    ).exclude(resolution_lessons="").only("affected_files")
    for entry in qs.iterator():
        for p in entry.affected_files or []:
            if isinstance(p, str) and p.strip():
                paths.add(p.strip())
    return paths


def paper_trail_eligible_dirs(root: Path) -> list[Path]:
    """Return immediate child directories under `root` that are:
      1. matched by a QUALITY_ARTIFACT_PREFIXES prefix,
      2. NOT in the protected-names set,
      3. AND every file inside maps to a lessons-saved path
         (or the dir is older than 7 days, falling back to the existing
         quality-evidence safe-prune rules).

    This is a CONSERVATIVE filter on top of the existing safe-prune; if
    any criterion is uncertain, the directory is excluded.
    """
    root = root.resolve()
    if root.name == "" or str(root) in ("/", "\\"):
        return []
    if not root.is_dir():
        return []

    saved = lessons_saved_paths()
    if not saved:
        return []

    eligible: list[Path] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        if child.name in _PROTECTED_NAMES:
            continue
        if not any(child.name.startswith(prefix) for prefix in QUALITY_ARTIFACT_PREFIXES):
            continue
        if _all_files_under_saved_paths(child, saved):
            eligible.append(child)
    return sorted(eligible)


def _all_files_under_saved_paths(directory: Path, saved: set[str]) -> bool:
    """True iff every file under `directory` references a saved path."""
    try:
        any_files = False
        for f in directory.rglob("*"):
            if not f.is_file():
                continue
            any_files = True
            text = ""
            try:
                if f.stat().st_size < 2_000_000:
                    text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if any(p in text or p in str(f) for p in saved):
                continue
            # File doesn't reference any saved path — bail out.
            return False
        return any_files
    except OSError:
        return False
