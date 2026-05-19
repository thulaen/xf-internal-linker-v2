# xf: no_dry_run -- filing the AutoIssue IS the command's only action; there is no preview mode that would be meaningful for a one-row insert that is itself the side effect being requested.
"""manage.py file_gh_helper_autoissue — argv-shaped gh-CLI failure filer.

Phase K6: replaces the heredoc-with-shell-interpolation pattern that
`scripts/_gh_helper.sh` previously used to file AutoIssues when `gh`
fails. Heredoc interpolation was unsafe — a `'` in the failure
context would break the embedded Python. Argv is shell-safe by
default.

Phase K8: `--kind` argument differentiates "missing" (gh not on PATH)
from "auth-expired" (gh installed but `gh auth status` non-zero).
Each kind gets a distinct `external_id` so the picker surfaces them
independently if both happen.

Usage (called by scripts/_gh_helper.sh):
    docker compose exec -T backend python manage.py file_gh_helper_autoissue \\
      --kind missing \\
      --context "scripts/run-angular-quality.sh tried to read latest pushed commit"

    docker compose exec -T backend python manage.py file_gh_helper_autoissue \\
      --kind auth_expired \\
      --context "gh auth status returned 1"
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.auto_issues.services.fingerprinting import canonical_fingerprint


_CATEGORY_KEY = "gh_tooling_broken"
_CATEGORY_LABEL = "gh CLI tooling broken"

# K8: per-kind titles + external_ids so the picker surfaces each
# independently. Two parallel tooling gaps deserve two AutoIssue rows.
_KIND_TITLES = {
    "missing": "gh CLI not installed",
    "auth_expired": "gh CLI auth expired or not configured",
    "api_failure": "gh CLI api call returned empty or non-zero",
}

_KIND_DESCRIPTIONS = {
    "missing": (
        "Trap: agents need `gh` to read the latest pushed commit "
        "from the remote, but the CLI is not on PATH.\n"
        "Fix shape: install GitHub CLI (https://cli.github.com/), "
        "run `gh auth login`, then retry the failing command."
    ),
    "auth_expired": (
        "Trap: `gh` is installed but `gh auth status` returned non-zero, "
        "so API calls fail. Local git fallback works but cannot resolve "
        "remote branch state.\n"
        "Fix shape: run `gh auth login` (or `gh auth refresh`) and "
        "verify with `gh auth status`."
    ),
    "api_failure": (
        "Trap: `gh` is installed and authenticated but the API call "
        "returned empty or non-zero. Branch may not exist on the remote, "
        "or the API was rate-limited.\n"
        "Fix shape: verify the branch is pushed (`git push -u origin <branch>`), "
        "wait for rate-limit reset, then retry."
    ),
}


def _get_or_create_category() -> AutoIssueCategory:
    cat, _ = AutoIssueCategory.objects.get_or_create(
        key=_CATEGORY_KEY,
        defaults={
            "label": _CATEGORY_LABEL,
            "description": (
                "gh CLI tooling failed. Agents fall back to local `git` for "
                "the duration of the session. Each kind (missing / "
                "auth_expired / api_failure) is a separate row so the "
                "picker surfaces all parallel problems."
            ),
            "sort_order": 300,
        },
    )
    return cat


class Command(BaseCommand):
    help = "File an AutoIssue for a gh CLI failure (kind-aware)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--kind", required=True, choices=sorted(_KIND_TITLES.keys()),
            help="Failure type: missing / auth_expired / api_failure.",
        )
        parser.add_argument(
            "--context", default="",
            help="Optional plain-English context (caller, command, etc).",
        )
        parser.add_argument(
            "--agent", default="claude",
            help="Agent name recorded as the observation source.",
        )

    def handle(self, *args, **opts):
        kind = opts["kind"]
        context = (opts["context"] or "").strip()
        agent = opts["agent"][:64]

        if kind not in _KIND_TITLES:
            raise CommandError(
                f"FAIL file_gh_helper_autoissue: --kind {kind!r} not recognised."
            )

        title = _KIND_TITLES[kind][:200]
        # Distinct external_id per kind so a session that hits BOTH
        # missing AND auth_expired gets TWO AutoIssue rows.
        ext_id = f"gh_helper::{kind}"
        cf = canonical_fingerprint(title)

        description = _KIND_DESCRIPTIONS[kind]
        if context:
            description = f"{description}\n\nContext: {context[:1500]}"

        category = _get_or_create_category()
        now = timezone.now()
        existing = AutoIssue.objects.filter(external_id=ext_id).first()

        if existing is not None:
            existing.occurrence_count += 1
            existing.last_seen = now
            obs = {
                "source": "gh_helper",
                "external_id": ext_id,
                "first_seen": existing.first_seen.isoformat()
                if existing.first_seen else now.isoformat(),
                "last_seen": now.isoformat(),
                "occurrence_count": existing.occurrence_count,
                "kind": kind,
                "context_excerpt": context[:200],
                "agent": agent,
            }
            existing.source_observations = [
                *(existing.source_observations or []),
                obs,
            ][:50]
            existing.save()
            self.stdout.write(
                f"[GH HELPER AUTOISSUE DEDUPED: matched AutoIssue=#{existing.pk} kind={kind}]"
            )
            return

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
            source_observations=[
                {
                    "source": "gh_helper",
                    "external_id": ext_id,
                    "first_seen": now.isoformat(),
                    "last_seen": now.isoformat(),
                    "occurrence_count": 1,
                    "kind": kind,
                    "context_excerpt": context[:200],
                    "agent": agent,
                }
            ],
        )
        self.stdout.write(
            f"[GH HELPER AUTOISSUE FILED: AutoIssue=#{ai.pk} kind={kind} title={title[:60]!r}]"
        )
