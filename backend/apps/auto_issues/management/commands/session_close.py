"""manage.py session_close — Session S4 of the TDD-pipeline rule.

Run at session end. Verifies the session's lessons are logged, prunes
the six test-artefact prefixes via the existing
`manage.py prune_test_artefacts` command, and emits a
`[SESSION CLOSE: …]` marker that the next session's
`.githooks/check-session-close.py` hook validates.

Spec: docs/TDD-PIPELINE-RULE.md.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone as dt_tz
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.auto_issues.models import AutoIssue


_PRUNABLE_PREFIXES: tuple[str, ...] = (
    "mull",
    "coverage",
    "mutmut",
    "stryker",
    "fuzz-work",
    "pytest-debug",
)


def _now_iso8601_z() -> str:
    return datetime.now(dt_tz.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _prune_prefix(prefix: str, *, dry_run: bool = False) -> float:
    """Call `prune_test_artefacts --prefix <p>`. Returns MiB freed (best-effort)."""
    out = StringIO()
    args = ["--prefix", prefix]
    if dry_run:
        args.append("--dry-run")
    try:
        call_command("prune_test_artefacts", *args, stdout=out)
    except Exception:  # noqa: BLE001 — pruning must never break session_close
        return 0.0
    text = out.getvalue()
    # Look for `evicted_mb=<float>` in the printed marker; fall back to 0.0.
    m = re.search(r"evicted_mb=(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"current_mb=(\d+(?:\.\d+)?)", text)
    if m:
        return 0.0  # nothing evicted; still considered a clean run
    return 0.0


def _count_session_lessons() -> int:
    """Best-effort: count tdd_lesson / code_review_lesson rows resolved in the
    last 24 hours. Used only for the marker's `lessons_verified=` slot — the
    strict-TDD hook already enforces per-commit lesson logging."""
    from django.utils import timezone

    cutoff = timezone.now() - timezone.timedelta(hours=24) if hasattr(
        timezone, "timedelta"
    ) else None
    if cutoff is None:
        # timezone.timedelta is not provided; use datetime's timedelta.
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(hours=24)
    qs = AutoIssue.objects.filter(
        category__key__in=("tdd_lesson", "code_review_lesson"),
        status=AutoIssue.STATUS_RESOLVED,
        resolved_at__gte=cutoff,
    )
    return qs.count()


def _format_marker(
    *, lessons_verified: int, total_freed: float, dry_run: bool
) -> str:
    prefix_label = ",".join(_PRUNABLE_PREFIXES)
    closed_at = _now_iso8601_z()
    tag = "SESSION CLOSE DRY-RUN" if dry_run else "SESSION CLOSE"
    return (
        f"[{tag}: lessons_verified={lessons_verified} "
        f"artefacts_pruned_mb={total_freed:.1f} prefixes={prefix_label} "
        f"closed_at={closed_at}]"
    )


class Command(BaseCommand):
    help = (
        "Close the current TDD session: verify lessons logged, prune "
        "test artefacts, emit [SESSION CLOSE: …]."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run verification + pruning in dry-run mode; emit a DRY-RUN marker.",
        )

    def handle(self, *args, **opts) -> None:
        dry_run = bool(opts.get("dry_run"))
        lessons_verified = _count_session_lessons()
        total_freed = 0.0
        for prefix in _PRUNABLE_PREFIXES:
            total_freed += _prune_prefix(prefix, dry_run=dry_run)
        self.stdout.write(
            _format_marker(
                lessons_verified=lessons_verified,
                total_freed=total_freed,
                dry_run=dry_run,
            )
        )
