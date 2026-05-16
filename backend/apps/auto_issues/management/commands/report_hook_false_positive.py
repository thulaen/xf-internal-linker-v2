"""manage.py report_hook_false_positive — Rule H meta-rule command.

Files an AutoIssue(category='hook_false_positive') when an agent
believes a pre-commit hook fired incorrectly. Dedup via
canonical_fingerprint so repeated reports of the same false positive
collapse into one row.

Per Rule H.31: agents who bypass a hook MUST first run this command
and include the printed AutoIssue id in the handoff entry as
`[HOOK FALSE POSITIVE FILED: hook=<name> AutoIssue=#N]`. Using
--no-verify or any destructive bypass is forbidden by Rule F.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.auto_issues.services.fingerprinting import canonical_fingerprint


_CATEGORY_KEY = "hook_false_positive"
_CATEGORY_LABEL = "Hook false positive"
_MAX_CONTEXT_WORDS = 600


def _get_or_create_category() -> AutoIssueCategory:
    cat, _ = AutoIssueCategory.objects.get_or_create(
        key=_CATEGORY_KEY,
        defaults={
            "label": _CATEGORY_LABEL,
            "description": (
                "Agent-filed report that a pre-commit hook fired "
                "incorrectly. Maintainers triage these to tune the offending "
                "hook. Filed via `manage.py report_hook_false_positive` "
                "per Rule H.31."
            ),
            "sort_order": 250,
        },
    )
    return cat


class Command(BaseCommand):
    help = "File an AutoIssue when an agent hits a pre-commit hook false positive."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hook", required=True,
            help="Name of the hook (e.g. check-debug-code, check-tdd-cycle).",
        )
        parser.add_argument(
            "--context", required=True,
            help=f"Plain-English explanation (max {_MAX_CONTEXT_WORDS} words).",
        )
        parser.add_argument(
            "--commit-sha", default="",
            help="Optional commit SHA being attempted when the false positive fired.",
        )
        parser.add_argument("--agent", default="claude")

    def handle(self, *args, **opts):
        hook = (opts["hook"] or "").strip()
        context = (opts["context"] or "").strip()
        if not hook:
            raise CommandError(
                "FAIL report_hook_false_positive: --hook is empty.\n"
                "WHY: Rule H.31 requires the hook name so maintainers can "
                "tune the offending check.\n"
                "UNBLOCK: Re-run with `--hook <name>` (e.g. check-debug-code)."
            )
        if not context:
            raise CommandError(
                "FAIL report_hook_false_positive: --context is empty.\n"
                "WHY: Rule H.31 requires a plain-English explanation so "
                "maintainers can reproduce and fix the false positive.\n"
                "UNBLOCK: Re-run with `--context \"<what the hook complained "
                "about, why you believe it was wrong, what the right behaviour "
                "would have been>\"`."
            )
        words = len(context.split())
        if words > _MAX_CONTEXT_WORDS:
            raise CommandError(
                f"FAIL report_hook_false_positive: context is {words} words "
                f"(max {_MAX_CONTEXT_WORDS}).\n"
                "WHY: Rule H.31 caps the context at 600 words so the AutoIssue "
                "queue stays scannable.\n"
                "UNBLOCK: Trim the context to the essential reasoning."
            )

        # First sentence + hook becomes the canonical fingerprint so
        # rephrased reports of the same false positive collapse.
        first_sentence = context.split(".", 1)[0][:200]
        title = f"[hook_false_positive] {hook}: {first_sentence[:160]}"
        canonical = canonical_fingerprint(f"{hook}::{first_sentence}")
        category = _get_or_create_category()
        ext_id = f"hook_false_positive::{hook}::{canonical}"
        agent = opts["agent"][:64]
        now = timezone.now()

        existing = AutoIssue.objects.filter(
            canonical_fingerprint=canonical,
            category=category,
        ).first()
        if existing is not None:
            existing.occurrence_count += 1
            existing.last_seen = now
            existing.source_observations = [
                *(existing.source_observations or []),
                {
                    "source": "hook_false_positive",
                    "external_id": ext_id,
                    "first_seen": existing.first_seen.isoformat()
                    if existing.first_seen else now.isoformat(),
                    "last_seen": now.isoformat(),
                    "occurrence_count": existing.occurrence_count,
                    "context_excerpt": context[:200],
                    "agent": agent,
                    "commit_sha": opts["commit_sha"][:64],
                },
            ]
            existing.save()
            self.stdout.write(
                f"[HOOK FALSE POSITIVE DEDUPED: hook={hook} "
                f"AutoIssue=#{existing.pk} (occurrence={existing.occurrence_count})]"
            )
            return

        ai = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id=ext_id,
            fingerprint=ext_id[:64],
            canonical_fingerprint=canonical,
            title=title[:512],
            description=context[:4000],
            affected_files=[f".githooks/{hook}.py"],
            severity=AutoIssue.SEVERITY_MEDIUM,
            category=category,
            status=AutoIssue.STATUS_OPEN,
            occurrence_count=1,
            last_seen=now,
            source_observations=[
                {
                    "source": "hook_false_positive",
                    "external_id": ext_id,
                    "first_seen": now.isoformat(),
                    "last_seen": now.isoformat(),
                    "occurrence_count": 1,
                    "context_excerpt": context[:200],
                    "agent": agent,
                    "commit_sha": opts["commit_sha"][:64],
                }
            ],
        )
        self.stdout.write(
            f"[HOOK FALSE POSITIVE FILED: hook={hook} AutoIssue=#{ai.pk}]"
        )
