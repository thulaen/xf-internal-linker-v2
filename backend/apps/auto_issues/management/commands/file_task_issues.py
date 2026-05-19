# xf: no_dry_run -- filing the AutoIssue rows IS the command's only purpose; a preview that does not file would defeat the post-task hook's reason to exist.
"""manage.py file_task_issues — Phase K9 post-task hook backend.

Called by `.claude/hooks/post-task-summary.py` at the end of every
coding turn. Files one `AutoIssue(category='task_followup',
source='agent')` per bullet in the chat's "What still has issues /
errors (honest)" section.

Per the user policy (2026-05-18):
  - Every coding task that produces a "What still has issues" section
    must have those items captured in the AutoIssue queue.
  - The 30-pick session quota then surfaces them ordered by the
    existing C++ priority algorithm.

Why argv (not stdin / heredoc): shell-injection-safe by default. Each
bullet is passed as a separate `--issue` value; no string substitution
into source code anywhere.

Usage:
    docker compose exec -T backend python manage.py file_task_issues \\
      --turn-id <uuid> \\
      --agent claude \\
      --issue "Mull is not file-scoped — still runs all 9 GTest binaries" \\
      --issue "coverage-modules.yaml doesn't exist yet"

Markers emitted (machine-readable for the hook to parse):
  [TASK ISSUE FILED: AutoIssue=#N title="..."]
  [TASK ISSUE DEDUPED: matched AutoIssue=#N]
  [TASK ISSUES SUMMARY: turn=<uuid> filed=<N> deduped=<K> total=<N+K>]
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.auto_issues.services.fingerprinting import canonical_fingerprint


_CATEGORY_KEY = "task_followup"
_CATEGORY_LABEL = "Task follow-up"

_MAX_TITLE_CHARS = 200
_MAX_DESCRIPTION_CHARS = 4000


def _get_or_create_category() -> AutoIssueCategory:
    cat, _ = AutoIssueCategory.objects.get_or_create(
        key=_CATEGORY_KEY,
        defaults={
            "label": _CATEGORY_LABEL,
            "description": (
                "Follow-up item surfaced in an agent's 'What still has issues "
                "/ errors (honest)' section at task end. Captured by the "
                ".claude/hooks/post-task-summary.py Stop hook so the next "
                "session sees the gap in the 30-pick session quota."
            ),
            "sort_order": 220,
        },
    )
    return cat


class Command(BaseCommand):
    help = "File AutoIssues for the unresolved bullets in a coding task's wrap-up."

    def add_arguments(self, parser):
        parser.add_argument(
            "--turn-id", required=True,
            help="Stable UUID for the chat turn so the picker can group + scope.",
        )
        parser.add_argument(
            "--agent", default="claude",
            help="Agent name recorded as the observation source.",
        )
        parser.add_argument(
            "--issue", action="append", default=[],
            help="One bullet from the 'still has issues' section (repeatable).",
        )

    def handle(self, *args, **opts):
        turn_id = (opts["turn_id"] or "").strip()
        agent = opts["agent"][:64]
        issues = [s.strip() for s in (opts["issue"] or []) if s and s.strip()]

        if not turn_id:
            # Nothing to anchor against; emit a soft warning marker
            # and exit 0 so the hook never breaks a chat turn.
            self.stdout.write("[TASK ISSUES SKIPPED: empty --turn-id]")
            return

        if not issues:
            self.stdout.write(
                f"[TASK ISSUES SUMMARY: turn={turn_id} filed=0 deduped=0 total=0]"
            )
            return

        category = _get_or_create_category()
        now = timezone.now()
        filed = 0
        deduped = 0

        for raw in issues:
            # Title is first sentence or first 200 chars, whichever is
            # shorter. Description is the full bullet.
            description = raw[:_MAX_DESCRIPTION_CHARS]
            short = raw.split(". ", 1)[0]
            title = (short if len(short) <= _MAX_TITLE_CHARS
                     else short[:_MAX_TITLE_CHARS - 3] + "...")
            cf = canonical_fingerprint(title)
            ext_id = f"task_followup::{cf}"

            existing = AutoIssue.objects.filter(
                external_id=ext_id,
                category=category,
            ).first()

            if existing is not None:
                existing.occurrence_count += 1
                existing.last_seen = now
                obs = {
                    "source": "task_followup",
                    "external_id": ext_id,
                    "first_seen": existing.first_seen.isoformat()
                    if existing.first_seen else now.isoformat(),
                    "last_seen": now.isoformat(),
                    "occurrence_count": existing.occurrence_count,
                    "turn_id": turn_id,
                    "agent": agent,
                }
                existing.source_observations = [
                    *(existing.source_observations or []),
                    obs,
                ][:50]
                existing.save()
                self.stdout.write(
                    f"[TASK ISSUE DEDUPED: matched AutoIssue=#{existing.pk}]"
                )
                deduped += 1
                continue

            lessons = (
                f"Trap: this gap was surfaced in the 'What still has issues "
                f"/ errors (honest)' section of turn {turn_id} but the "
                f"underlying fix was not done in the same turn.\n"
                f"Fix shape: resolve the bullet content; see description "
                f"for the verbatim text the agent flagged."
            )

            ai = AutoIssue.objects.create(
                source=AutoIssue.SOURCE_AGENT,
                external_id=ext_id,
                fingerprint=cf[:64],
                canonical_fingerprint=cf,
                title=title,
                description=description,
                severity=AutoIssue.SEVERITY_MEDIUM,
                category=category,
                status=AutoIssue.STATUS_OPEN,
                first_seen=now,
                last_seen=now,
                occurrence_count=1,
                lessons_learned=lessons,
                source_observations=[
                    {
                        "source": "task_followup",
                        "external_id": ext_id,
                        "first_seen": now.isoformat(),
                        "last_seen": now.isoformat(),
                        "occurrence_count": 1,
                        "turn_id": turn_id,
                        "agent": agent,
                    }
                ],
            )
            self.stdout.write(
                f"[TASK ISSUE FILED: AutoIssue=#{ai.pk} title={title[:60]!r}]"
            )
            filed += 1

        total = filed + deduped
        self.stdout.write(
            f"[TASK ISSUES SUMMARY: turn={turn_id} filed={filed} "
            f"deduped={deduped} total={total}]"
        )
