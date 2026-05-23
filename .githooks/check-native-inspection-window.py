#!/usr/bin/env python3
"""
Pre-commit hook: enforce the 7-day Native Inspection Window (Phase K.3).

Sticky #1 (paper_trail row 11, SHA prefix 7b8d04510bf49e49) addendum
"Native Inspection Window" gives every newly-merged native artifact
seven calendar days of open inspection. After the window closes the
artifact is "settled" and edits are hard-blocked unless paired with one
of three documented reopen markers:

  [USER REQUEST INSPECTION: file=<path> reason="<>=20-char plain-English>"]
  [PYROSCOPE REGRESSION: file=<path> baseline_p95_ms=<X> observed_p95_ms=<Y>
                         sustained_minutes=<N>]
  [OTEL_PROFILE REGRESSION: file=<path> baseline_p95_ms=<X>
                            observed_p95_ms=<Y> sustained_minutes=<N>]

The hook scans every staged native-language file, then walks the
AGENT-HANDOFF history back-to-front to find the most recent
``[NATIVE INSPECTION WINDOW: file=<path> opened_at=... closes_at=...]``
marker for that path. Files with no prior window are treated as
"not yet merged" and pass freely (the window first applies on the merge
that introduces the artifact). Files whose window is still open pass.
Files whose window has closed need a reopen marker in the staged
AGENT-HANDOFF entry or the commit is refused.

Full spec at docs/specs/fr-native-inspection-and-spec-windows.md.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hook_helpers  # noqa: E402

# Native-language path prefixes + file extensions per Sticky #1.
_NATIVE_PREFIXES = (
    "services/",
    "backend/extensions/",
)
_NATIVE_EXTENSIONS = (".rs", ".cpp", ".hpp", ".hs", ".go")

_HANDOFF_PATH = REPO_ROOT / "AGENT-HANDOFF.md"

_WINDOW_RE = re.compile(
    r"\[NATIVE\s+INSPECTION\s+WINDOW:\s*"
    r"file=(?P<file>[^\s]+)\s+"
    r"opened_at=(?P<opened_at>[^\s]+)\s+"
    r"closes_at=(?P<closes_at>[^\]]+)\]"
)

_USER_REOPEN_RE = re.compile(
    r"\[USER\s+REQUEST\s+INSPECTION:\s*"
    r"file=(?P<file>[^\s]+)\s+"
    r'reason="(?P<reason>[^"]+)"\]'
)

_PYROSCOPE_REOPEN_RE = re.compile(
    r"\[PYROSCOPE\s+REGRESSION:\s*"
    r"file=(?P<file>[^\s]+)\s+"
    r"baseline_p95_ms=(?P<baseline>[0-9.]+)\s+"
    r"observed_p95_ms=(?P<observed>[0-9.]+)\s+"
    r"sustained_minutes=(?P<minutes>\d+)\]"
)

_OTEL_REOPEN_RE = re.compile(
    r"\[OTEL_PROFILE\s+REGRESSION:\s*"
    r"file=(?P<file>[^\s]+)\s+"
    r"baseline_p95_ms=(?P<baseline>[0-9.]+)\s+"
    r"observed_p95_ms=(?P<observed>[0-9.]+)\s+"
    r"sustained_minutes=(?P<minutes>\d+)\]"
)

_MIN_SUSTAINED_MINUTES = 10
_MIN_REGRESSION_MULTIPLIER = 1.5
_MIN_REASON_LEN = 20


def _fail(message: str) -> int:
    sys.stderr.write(message)
    return 2


def _is_native_path(path: str) -> bool:
    if any(path.startswith(p) for p in _NATIVE_PREFIXES):
        return True
    return any(path.endswith(ext) for ext in _NATIVE_EXTENSIONS)


def _staged_native_files() -> list[str]:
    """Return staged files matching native-language prefixes or extensions."""
    return [p for p in _hook_helpers.staged_code_files(REPO_ROOT) if _is_native_path(p)]


def _staged_handoff_diff() -> str:
    return _hook_helpers.get_staged_handoff_diff(REPO_ROOT)


def _handoff_text() -> str:
    if not _HANDOFF_PATH.is_file():
        return ""
    try:
        return _HANDOFF_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _parse_iso(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _latest_window_for(path: str, handoff: str) -> tuple[datetime, datetime] | None:
    """Return (opened_at, closes_at) for the most recent window marker."""
    matches = list(_WINDOW_RE.finditer(handoff))
    for match in reversed(matches):
        if match.group("file") == path:
            opened = _parse_iso(match.group("opened_at"))
            closes = _parse_iso(match.group("closes_at"))
            if opened and closes:
                return opened, closes
    return None


def _has_user_reopen(diff: str, path: str) -> bool:
    for match in _USER_REOPEN_RE.finditer(diff):
        if match.group("file") == path and len(match.group("reason")) >= _MIN_REASON_LEN:
            return True
    return False


def _has_regression_reopen(diff: str, path: str) -> bool:
    for pattern in (_PYROSCOPE_REOPEN_RE, _OTEL_REOPEN_RE):
        for match in pattern.finditer(diff):
            if match.group("file") != path:
                continue
            try:
                baseline = float(match.group("baseline"))
                observed = float(match.group("observed"))
                minutes = int(match.group("minutes"))
            except (TypeError, ValueError):
                continue
            if baseline <= 0:
                continue
            if minutes < _MIN_SUSTAINED_MINUTES:
                continue
            if observed < baseline * _MIN_REGRESSION_MULTIPLIER:
                continue
            return True
    return False


def main() -> int:
    native_files = _staged_native_files()
    if not native_files:
        return 0

    handoff = _handoff_text()
    diff = _staged_handoff_diff()
    now = datetime.now(timezone.utc)

    settled_violations: list[str] = []
    for path in native_files:
        window = _latest_window_for(path, handoff)
        if window is None:
            # First-time merge of the artifact — the window opens here.
            continue
        opened_at, closes_at = window
        if now <= closes_at:
            # Window is open; the artifact is still under inspection.
            continue
        # Settled state. Look for a documented reopen marker in the staged diff.
        if _has_user_reopen(diff, path) or _has_regression_reopen(diff, path):
            continue
        days_settled = (now - closes_at).days
        settled_violations.append(
            f"  {path} (closed {days_settled} day(s) ago at {closes_at.isoformat()})"
        )

    if not settled_violations:
        return 0

    return _fail(
        "FAIL check-native-inspection-window: the following native-language "
        "files have a closed inspection window and the staged AGENT-HANDOFF "
        "entry has no documented reopen marker for them:\n"
        + "\n".join(settled_violations)
        + "\n"
        "WHY: Sticky #1 addendum 'Native Inspection Window' gives every "
        "newly-merged native artifact 7 days of open inspection. After "
        "that window closes the artifact is 'settled' and casual edits "
        "are blocked to prevent post-merge churn (Brooks 1995 ch.8, "
        "irreversibility cost).\n"
        "UNBLOCK option A: pair each edit with a user-request reopen "
        "marker: [USER REQUEST INSPECTION: file=<path> reason=\"<>=20 chars "
        "plain-English>\"].\n"
        "UNBLOCK option B: pair each edit with a measured regression "
        "marker: [PYROSCOPE REGRESSION: file=<path> baseline_p95_ms=<X> "
        "observed_p95_ms=<Y> sustained_minutes=<N>] (or "
        "[OTEL_PROFILE REGRESSION: ...]) where observed is at least 1.5x "
        "baseline and sustained_minutes is at least 10.\n"
        "See docs/specs/fr-native-inspection-and-spec-windows.md.\n"
    )


if __name__ == "__main__":
    sys.exit(main())
