"""Read the previous handoff timestamp for session-scoped checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from pathlib import Path

from django.utils import timezone


HANDOFF_HEADER_RE = re.compile(
    r"^# (?P<stamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s+-\s+",
    re.MULTILINE,
)


@dataclass(frozen=True)
class SessionBoundary:
    """Previous handoff timestamp, or grandfather status for a fresh repo."""

    resolved_after: datetime | None
    display: str
    grandfathered: bool


def previous_handoff_boundary(handoff_path: Path | None = None) -> SessionBoundary:
    """Return the newest handoff header timestamp."""
    path = handoff_path or _default_handoff_path()
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = list(HANDOFF_HEADER_RE.finditer(text))
    if not matches:
        return SessionBoundary(None, "grandfather: no prior session", True)
    raw_stamp = matches[-1].group("stamp")
    parsed = datetime.strptime(raw_stamp, "%Y-%m-%d %H:%M")
    return SessionBoundary(
        timezone.make_aware(parsed, timezone.get_current_timezone()),
        raw_stamp,
        False,
    )


def _default_handoff_path() -> Path:
    for candidate in _handoff_candidates():
        if candidate.exists():
            return candidate
    return Path.cwd() / "AGENT-HANDOFF.md"


def _handoff_candidates() -> tuple[Path, ...]:
    repo_root = Path(__file__).resolve().parents[4]
    return (
        Path.cwd() / "AGENT-HANDOFF.md",
        Path("/repo/AGENT-HANDOFF.md"),
        repo_root / "AGENT-HANDOFF.md",
    )
