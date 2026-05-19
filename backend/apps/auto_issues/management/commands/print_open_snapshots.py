"""Slice 1.6 — print the open snapshots attached to AutoIssues.

Emits the `[SNAPSHOTS READ: ...]` marker the snapshotd-ritual hook
(`.githooks/check-snapshotd-ritual.py`) accepts in two forms:

  1. Full picked form (when snapshotd is reachable):
       [SNAPSHOTS READ: <N> snapshots attached to <M> open issues —
       picked: #<id>(<kind>), #<id>(<kind>), #<id>(<kind>)]

  2. Skipped fallback (when snapshotd isn't running or the Python client
     stubs are missing):
       [SNAPSHOTS READ: skipped — snapshotd unavailable]

The picks are the 3 highest-severity snapshots whose AutoIssues are
currently open (status in OPEN / PICKED). Severity ordering: critical >
error > warning > before > after > info > unknown.

Usage::

    docker compose exec -T backend python manage.py print_open_snapshots \\
        --by-severity --top 3

`--by-severity` and `--top N` are the canonical flags from the slice 1.6
spec; both are kept settable so future agents can change the cap without
editing this file.
"""

from __future__ import annotations

import logging
from typing import Iterable

from django.core.management.base import BaseCommand

from apps.auto_issues.models import AutoIssue

logger = logging.getLogger(__name__)

# Severity order for the picker. Lower number = higher priority pick.
_SEVERITY_RANK = {
    "SK_CRITICAL": 0,
    "SK_ERROR": 1,
    "SK_WARNING": 2,
    "SK_BEFORE": 3,
    "SK_AFTER": 4,
    "SK_INFO": 5,
    "SK_UNKNOWN": 6,
}

_OPEN_STATUSES = (AutoIssue.STATUS_OPEN, AutoIssue.STATUS_PICKED)


class Command(BaseCommand):
    help = (
        "Print snapshotd evidence for open AutoIssues. Emits the "
        "[SNAPSHOTS READ: ...] marker required by CLAUDE.md slice 1.6."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--by-severity",
            action="store_true",
            default=True,
            help="Order picks by severity (critical first). Default: on.",
        )
        parser.add_argument(
            "--top",
            type=int,
            default=3,
            help="Number of snapshots to pick. Default: 3 (the hook minimum).",
        )

    def handle(self, *args, **options):
        top = max(1, int(options["top"]))
        try:
            picks = self._collect_picks(top)
        except _SnapshotdUnavailable as err:
            # Fallback form — the hook accepts this so contributors who
            # have not yet booted snapshotd are not blocked.
            self.stdout.write(
                "[SNAPSHOTS READ: skipped — snapshotd unavailable]"
            )
            logger.info("print_open_snapshots: %s", err)
            return

        total_snapshots = len(picks["all_snapshots"])
        open_issues_with_snapshots = picks["open_issue_count"]
        chosen = picks["chosen"]
        if not chosen:
            self.stdout.write(
                f"[SNAPSHOTS READ: {total_snapshots} snapshots attached to "
                f"{open_issues_with_snapshots} open issues — picked: "
                f"(none — no open AutoIssue has an attached snapshot yet)]"
            )
            return
        chosen_fmt = ", ".join(
            f"#{snap['id']}({snap['kind']})" for snap in chosen
        )
        self.stdout.write(
            f"[SNAPSHOTS READ: {total_snapshots} snapshots attached to "
            f"{open_issues_with_snapshots} open issues — picked: {chosen_fmt}]"
        )

    def _collect_picks(self, top: int) -> dict:
        """Query snapshotd for every open AutoIssue's snapshots and rank by
        severity. Raises `_SnapshotdUnavailable` when the Python client cannot
        reach the binary (stubs missing or socket down)."""
        try:
            from apps.auto_issues._sidecars.snapshotd_client import SnapshotdClient
        except Exception as exc:  # noqa: BLE001 - lazy import barrier
            raise _SnapshotdUnavailable(
                f"snapshotd client import failed: {exc}"
            ) from exc

        client = SnapshotdClient(deadline=5.0)
        try:
            health = client.health()
        except Exception as exc:  # noqa: BLE001 - any RPC failure is "unavailable"
            raise _SnapshotdUnavailable(
                f"snapshotd Health() failed: {exc}"
            ) from exc
        if health != "HEALTH_SERVING":
            raise _SnapshotdUnavailable(
                f"snapshotd Health() returned {health!r}"
            )

        open_issue_ids = list(
            AutoIssue.objects.filter(status__in=_OPEN_STATUSES)
            .values_list("id", flat=True)
        )
        all_snapshots: list[dict] = []
        for issue_id in open_issue_ids:
            try:
                items = client.list_by_issue(issue_id)
            except Exception as exc:  # noqa: BLE001 - per-issue failure
                logger.warning(
                    "print_open_snapshots: ListByIssue(%d) failed: %s",
                    issue_id, exc,
                )
                continue
            for snap in items:
                all_snapshots.append(
                    {
                        "id": snap.id[:8] if snap.id else "<unset>",
                        "issue_id": snap.issue_id,
                        "kind": snap.kind,
                        "category": snap.category,
                    }
                )

        issues_with_at_least_one_snapshot = {
            s["issue_id"] for s in all_snapshots
        }
        chosen = _rank(all_snapshots, top)
        return {
            "all_snapshots": all_snapshots,
            "open_issue_count": len(issues_with_at_least_one_snapshot),
            "chosen": chosen,
        }


def _rank(snapshots: Iterable[dict], top: int) -> list[dict]:
    """Pick the top-N highest-severity snapshots."""
    return sorted(
        snapshots,
        key=lambda s: _SEVERITY_RANK.get(s["kind"], 99),
    )[:top]


class _SnapshotdUnavailable(RuntimeError):
    """Internal marker — caller emits the skipped-form fallback."""
