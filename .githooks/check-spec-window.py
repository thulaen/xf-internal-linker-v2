#!/usr/bin/env python3
"""
Pre-commit hook: enforce the 14-day Settled-Spec Window (Phase K.3).

Sticky #1 (paper_trail row 11) addendum "Settled-Spec Window" gives
every newly-landed source-backed spec under ``docs/specs/*.md`` fourteen
calendar days of open authoring. After fourteen days the spec is
"settled" and edits are hard-blocked unless paired with one of three
documented reopen markers:

  [USER REQUEST SPEC EDIT: spec=<path> reason="<>=20-char plain-English>"]
  [SPEC CITATION DRIFT: spec=<path> previous_id=<id> new_id=<id>
                        evidence_url=<URL>]
  [SPEC KPI DRIFT: spec=<path> metric=<name> baseline=<X> observed=<Y>
                   threshold_pct=<P>]

The spec's ``opened_at`` is derived from its ``[SPEC FRESHNESS: ...
reviewed_at=YYYY-MM-DD ...]`` marker. ``closes_at`` is ``opened_at + 14
days``. Files with no ``SPEC FRESHNESS`` marker are treated as "not yet
landed" and pass freely (the window first applies on the merge that
introduces the spec).

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

_SPEC_PREFIX = "docs/specs/"
_SPEC_SUFFIX = ".md"

_SPEC_FRESHNESS_RE = re.compile(
    r"\[SPEC\s+FRESHNESS:\s*reviewed_at=(?P<reviewed_at>\d{4}-\d{2}-\d{2})"
)

_USER_REOPEN_RE = re.compile(
    r"\[USER\s+REQUEST\s+SPEC\s+EDIT:\s*"
    r"spec=(?P<spec>[^\s]+)\s+"
    r'reason="(?P<reason>[^"]+)"\]'
)

_CITATION_DRIFT_RE = re.compile(
    r"\[SPEC\s+CITATION\s+DRIFT:\s*"
    r"spec=(?P<spec>[^\s]+)\s+"
    r"previous_id=(?P<previous>[^\s]+)\s+"
    r"new_id=(?P<new>[^\s]+)\s+"
    r"evidence_url=(?P<url>[^\]\s]+)\]"
)

_KPI_DRIFT_RE = re.compile(
    r"\[SPEC\s+KPI\s+DRIFT:\s*"
    r"spec=(?P<spec>[^\s]+)\s+"
    r"metric=(?P<metric>[^\s]+)\s+"
    r"baseline=(?P<baseline>[0-9.]+)\s+"
    r"observed=(?P<observed>[0-9.]+)\s+"
    r"threshold_pct=(?P<threshold>[0-9.]+)\]"
)

_WINDOW_DAYS = 14
_MIN_REASON_LEN = 20


def _fail(message: str) -> int:
    sys.stderr.write(message)
    return 2


def _staged_spec_files() -> list[str]:
    """Return staged docs/specs/*.md files."""
    return [
        p
        for p in _hook_helpers.staged_code_files(REPO_ROOT)
        if p.startswith(_SPEC_PREFIX) and p.endswith(_SPEC_SUFFIX)
    ]


def _staged_handoff_diff() -> str:
    return _hook_helpers.get_staged_handoff_diff(REPO_ROOT)


def _opened_at_for(spec_path: str) -> datetime | None:
    """Return the spec's window-open timestamp from its freshness marker."""
    full = REPO_ROOT / spec_path
    if not full.is_file():
        return None
    try:
        text = full.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _SPEC_FRESHNESS_RE.search(text)
    if not match:
        return None
    try:
        date = datetime.strptime(match.group("reviewed_at"), "%Y-%m-%d")
    except ValueError:
        return None
    return date.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)


def _has_user_reopen(diff: str, path: str) -> bool:
    for match in _USER_REOPEN_RE.finditer(diff):
        if match.group("spec") == path and len(match.group("reason")) >= _MIN_REASON_LEN:
            return True
    return False


def _has_citation_drift(diff: str, path: str) -> bool:
    for match in _CITATION_DRIFT_RE.finditer(diff):
        if match.group("spec") == path and match.group("previous") != match.group("new"):
            return True
    return False


def _has_kpi_drift(diff: str, path: str) -> bool:
    for match in _KPI_DRIFT_RE.finditer(diff):
        if match.group("spec") != path:
            continue
        try:
            baseline = float(match.group("baseline"))
            observed = float(match.group("observed"))
            threshold = float(match.group("threshold"))
        except (TypeError, ValueError):
            continue
        if baseline <= 0 or threshold <= 0:
            continue
        observed_drift_pct = abs(observed - baseline) / baseline * 100.0
        if observed_drift_pct >= threshold:
            return True
    return False


def main() -> int:
    spec_files = _staged_spec_files()
    if not spec_files:
        return 0

    diff = _staged_handoff_diff()
    now = datetime.now(timezone.utc)

    settled_violations: list[str] = []
    for path in spec_files:
        opened = _opened_at_for(path)
        if opened is None:
            # No freshness marker yet — treat as not-yet-landed.
            continue
        closes = opened + timedelta(days=_WINDOW_DAYS)
        if now <= closes:
            continue
        if (
            _has_user_reopen(diff, path)
            or _has_citation_drift(diff, path)
            or _has_kpi_drift(diff, path)
        ):
            continue
        days_settled = (now - closes).days
        settled_violations.append(
            f"  {path} (closed {days_settled} day(s) ago at {closes.isoformat()})"
        )

    if not settled_violations:
        return 0

    return _fail(
        "FAIL check-spec-window: the following docs/specs/*.md files "
        "are past their 14-day open window and the staged AGENT-HANDOFF "
        "entry has no documented reopen marker for them:\n"
        + "\n".join(settled_violations)
        + "\n"
        "WHY: Sticky #1 addendum 'Settled-Spec Window' gives every spec "
        "14 days of open authoring after it lands. After that the spec "
        "is 'settled' and casual edits are blocked to prevent "
        "post-merge churn (Cockburn 2001 ch.6, protection window).\n"
        "UNBLOCK option A: pair each edit with a user-request reopen "
        "marker: [USER REQUEST SPEC EDIT: spec=<path> reason=\"<>=20 chars>\"].\n"
        "UNBLOCK option B: pair each edit with a citation-drift marker: "
        "[SPEC CITATION DRIFT: spec=<path> previous_id=<id> new_id=<id> "
        "evidence_url=<URL>].\n"
        "UNBLOCK option C: pair each edit with a KPI-drift marker: "
        "[SPEC KPI DRIFT: spec=<path> metric=<name> baseline=<X> "
        "observed=<Y> threshold_pct=<P>] where the observed drift "
        "exceeds threshold_pct.\n"
        "See docs/specs/fr-native-inspection-and-spec-windows.md.\n"
    )


if __name__ == "__main__":
    sys.exit(main())
