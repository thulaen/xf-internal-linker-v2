"""Print GitHub Actions failure history markers and trends."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.services import gh_actions_history, session_boundary


class Command(BaseCommand):
    help = "Print failed GitHub Actions history for session startup or trends."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--since-handoff", action="store_true")
        parser.add_argument("--trend", action="store_true")
        parser.add_argument("--top", type=int, default=5)
        parser.add_argument("--repo-root", default="/repo")

    def handle(self, *args, **options) -> None:
        repo_root = Path(options["repo_root"]).resolve()
        history_path = repo_root / "audit" / "github_actions_failures.jsonl"
        if options["since_handoff"]:
            boundary = session_boundary.previous_handoff_boundary(repo_root / "AGENT-HANDOFF.md")
            marker = gh_actions_history.since_handoff_marker(boundary.resolved_after, history_path)
            self.stdout.write(marker)
            return
        if options["trend"]:
            self._print_trend(history_path, options["top"])
            return
        raise CommandError("Use --since-handoff or --trend.")

    def _print_trend(self, history_path: Path, top: int) -> None:
        rows = gh_actions_history.trend_rows(history_path, top=max(top, 0))
        self.stdout.write(f"[GH ACTIONS TREND: top={top} groups={len(rows)}]")
        for row in rows:
            self.stdout.write(
                "workflow={workflow} job={job} count={count} "
                "last_failed_at={last_failed_at} sample_run_url={sample_run_url} "
                "open_autoissues={open_autoissue_count}".format(**row)
            )
