"""Django management command: produce the monthly Top-50 link-suggestions report.

Single entry point used by:
- The Windows scheduled task (`scripts/run-monthly-top-50.ps1`).
- The frontend "Run Now" button (calls this via a thin DRF view).
- Operator manual runs (`python scripts/backend_manage.py
  run_monthly_top_50 --month=YYYY-MM`).

Strategy auto-detection happens here so the same command works whether
Claude Code is installed and signed in or not. Strategy B (pure Python)
is the safe fallback that always works.

Records the run via the sentient-schedules tracker so the Schedules UI on
the AI Agents page can show what fired and when.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)

TASK_NAME = "pipeline.run_monthly_top_50"


class Command(BaseCommand):
    help = (
        "Pick the top 50 pending link suggestions for the given month, write a "
        "markdown report under docs/reports/, and flag the chosen suggestions "
        "as 'proposed'. Falls back to a pure-Python deterministic picker when "
        "Claude Code is not available."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--month",
            help="Target month in YYYY-MM format. Defaults to the current UTC month.",
        )
        parser.add_argument(
            "--strategy",
            choices=("auto", "claude_code", "python"),
            default="auto",
            help="Force a specific strategy. 'auto' (default) detects Claude Code at runtime.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Number of picks to write (default 50).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show the selected strategy without writing a report or updating schedule state.",
        )

    def handle(self, *args, **opts):
        month = opts.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")
        if not _is_valid_month(month):
            raise CommandError(f"--month must be YYYY-MM, got {month!r}")

        from apps.pipeline.services.strategy_router import pick_strategy

        strategy_override = opts["strategy"]
        active = pick_strategy(override=strategy_override)
        if opts["dry_run"]:
            self.stdout.write(
                self.style.NOTICE(
                    "Dry run only. Would run monthly top-50 report with "
                    f"month={month} strategy={active} limit={opts['limit']}."
                )
            )
            return

        self._run_report(month, active, opts)

    def _run_report(self, month: str, active: str, opts) -> None:
        from apps.core.services.schedule_tracker import record_run

        strategy_override = opts["strategy"]
        scheduled_for = _slot_for_month(month)
        started_at = datetime.now(timezone.utc)
        record_run(TASK_NAME, scheduled_for, status="running", started_at=started_at)
        self.stdout.write(
            self.style.NOTICE(
                f"run_monthly_top_50: month={month} strategy={active} (override={strategy_override})"
            )
        )

        try:
            report_path = _dispatch(month, active, opts["limit"])
        except Exception as exc:  # noqa: BLE001  # justification: record the failure on the schedule row before re-raising
            record_run(
                TASK_NAME,
                scheduled_for,
                status="failed",
                error=str(exc),
                finished_at=datetime.now(timezone.utc),
            )
            raise

        record_run(
            TASK_NAME,
            scheduled_for,
            status="succeeded",
            finished_at=datetime.now(timezone.utc),
            payload={"report_path": str(report_path), "strategy": active},
        )
        self.stdout.write(
            self.style.SUCCESS(f"run_monthly_top_50: wrote {report_path}")
        )


def _dispatch(month: str, strategy: str, limit: int):
    """Hand off to the chosen strategy. Both return the report Path."""
    from apps.pipeline.services import monthly_picker

    if strategy == "claude_code":
        # Strategy A is "shell out to Claude Code with the prompt template",
        # which lives in scripts/run-monthly-top-50.ps1. The management command
        # is not the right place to spawn Claude Code interactively — the
        # PowerShell wrapper handles that path. If a caller forces strategy=
        # 'claude_code' inside Django, fall back to the deterministic Python
        # path so we never silently deadlock waiting on a child process.
        logger.warning(
            "run_monthly_top_50: strategy=claude_code requested inside Django; "
            "falling back to python (use scripts/run-monthly-top-50.ps1 for the LLM path)"
        )
    return monthly_picker.run_python_strategy(month, pick_limit=limit)


def _slot_for_month(month: str) -> datetime:
    """First-of-month 09:00 UTC, used as the schedule slot timestamp."""
    year, mm = month.split("-")
    return datetime(int(year), int(mm), 1, 9, 0, 0, tzinfo=timezone.utc)


def _is_valid_month(s: str) -> bool:
    if not s or len(s) != 7 or s[4] != "-":
        return False
    try:
        datetime.strptime(s, "%Y-%m")
    except ValueError:
        return False
    return True
