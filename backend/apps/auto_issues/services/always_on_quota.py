"""Always-on, drought-aware "fix N" quota rule (pure, no DB).

A source's commit gate PASSES when its open backlog is under the threshold OR
when at least `threshold` of its issues were resolved this session. A clean
state (0 open) never blocks. See docs/specs/fr-pgexporter-autoissues.md.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_THRESHOLD = 10


@dataclass(frozen=True)
class QuotaStatus:
    ok: bool
    short: int  # how many more resolutions are needed to pass (0 when ok)
    message: str


def always_on_quota_status(
    *, open_count: int, resolved_count: int, threshold: int = DEFAULT_THRESHOLD
) -> QuotaStatus:
    """Return whether the always-on quota passes for one source.

    PASS iff ``open_count < threshold`` OR ``resolved_count >= threshold``.
    Counts are clamped to >= 0 so odd DB aggregates never crash the gate.
    """
    open_count = max(0, int(open_count))
    resolved_count = max(0, int(resolved_count))
    threshold = max(1, int(threshold))

    if open_count < threshold or resolved_count >= threshold:
        return QuotaStatus(ok=True, short=0, message="quota satisfied")

    short = threshold - resolved_count
    message = (
        f"{open_count} open at or above the threshold of {threshold}, "
        f"but only {resolved_count} resolved this session — "
        f"resolve {short} more before committing."
    )
    return QuotaStatus(ok=False, short=short, message=message)
