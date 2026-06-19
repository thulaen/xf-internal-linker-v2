"""Print the open auto-issues an agent should consider before any new task.

Used by the pre-session hook (``.githooks/print-open-issues.ps1``) and by
the ``[REGISTRY READ: ...]`` startup marker every agent must emit per the
ABSOLUTE rule in CLAUDE.md. Output is intentionally compact so it fits
in a session-start banner.

Phase 7 of the test-hardening plan added a second marker line for
``[CI FAILED RUNS READ: ...]`` so the opening ritual also surfaces the
10 latest failed GitHub Actions workflow runs that haven't been
remediated. Failing CI runs auto-issue themselves via the
``ci_failed_runs`` picker (Phase 6) so they CAN show up among the 18
picks; the explicit ``gh run list`` step is the freshness check at
session start.
"""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404

from django.core.management.base import BaseCommand

from apps.auto_issues.models import AutoIssue


_OPEN_STATUSES = (AutoIssue.STATUS_OPEN, AutoIssue.STATUS_PICKED)
_TITLE_WIDTH = 80
_FILES_WIDTH = 80


class Command(BaseCommand):
    help = "Print open AutoIssue rows in priority order. Used at session start."

    _DEFAULT_LIMIT = 10

    # Ordered the same way the 10-source [REGISTRY READ] marker prints the
    # per-source breakdown (agent / glitchtip / pyroscope / tempo / loki /
    # faro / mutation / fuzz / contract / gh_ci). Matches
    # `.githooks/check-registry-read.py:NEW_MARKER_RE`.
    _SOURCE_ORDER = (
        AutoIssue.SOURCE_AGENT,
        AutoIssue.SOURCE_GLITCHTIP,
        AutoIssue.SOURCE_PYROSCOPE,
        AutoIssue.SOURCE_TEMPO,
        AutoIssue.SOURCE_LOKI,
        AutoIssue.SOURCE_FARO,
        AutoIssue.SOURCE_MUTATION,
        AutoIssue.SOURCE_FUZZ,
        AutoIssue.SOURCE_CONTRACT,
        AutoIssue.SOURCE_GH_CI,
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=self._DEFAULT_LIMIT,
            help=f"Max rows to print (default {self._DEFAULT_LIMIT}).",
        )
        parser.add_argument(
            "--source",
            choices=[c[0] for c in AutoIssue.SOURCE_CHOICES],
            default=None,
            help=(
                "Restrict to one source "
                "(agent, glitchtip, pyroscope, tempo, loki, faro)."
            ),
        )

    def handle(self, *args, **opts):
        rows = _pick_unique_open_issues(
            limit=opts["limit"],
            source=opts["source"],
        )
        if not rows:
            self.stdout.write("[REGISTRY READ: 0 open auto-issues]")
            return

        total = AutoIssue.objects.filter(status__in=_OPEN_STATUSES).count()
        # All-source view also prints a one-line per-source breakdown so
        # an agent can copy it into the [REGISTRY READ ...] marker
        # without running --source six times.
        if not opts["source"]:
            counts = {
                s: AutoIssue.objects.filter(
                    status__in=_OPEN_STATUSES, source=s,
                ).count()
                for s in self._SOURCE_ORDER
            }
            breakdown = " / ".join(
                f"{counts[s]} {s}" for s in self._SOURCE_ORDER
            )
            # The [REGISTRY READ] marker's N is the SUM of the ten picker-source
            # counts — exactly what .githooks/check-registry-read.py asserts
            # (NEW_MARKER_RE: the ten numbers must sum to N). It is NOT the grand
            # total of every AutoIssue: open rows in non-picker categories
            # (code_review_lesson, tdd_lesson, hook_failure, test_case,
            # observability, ...) are excluded from the 30-pick ritual, so the
            # header must equal the bucket sum to stay self-consistent.
            picker_total = sum(counts[s] for s in self._SOURCE_ORDER)
            self.stdout.write(
                f"[REGISTRY READ: {picker_total} open ({breakdown}), "
                f"showing top {len(rows)}]"
            )
        else:
            self.stdout.write(
                f"[REGISTRY READ: {total} open, "
                f"showing top {len(rows)}]"
            )
        self._print_issue_table(rows)

        # Phase 7: also print the 10 latest failed CI runs so the
        # opening ritual surfaces them before any new work begins.
        self._print_ci_failed_runs()

        # FR-251: also print the top 10 coverage-gap AutoIssues so the
        # session-start ritual surfaces them. See AI-CODING-GUIDELINES.md
        # and docs/CODE-COVERAGE-RULES.md for the contract.
        self._print_coverage_gaps()

        # FR-251: emit the guidelines-read marker so the agent acknowledges
        # both the comprehensive coding rules AND the coverage rules.
        self.stdout.write(
            "[GUIDELINES READ: "
            "AI-CODING-GUIDELINES.md + docs/CODE-COVERAGE-RULES.md]"
        )

    def _print_ci_failed_runs(self) -> None:
        """Shell out to `gh run list` and print the second marker line.

        Fails graceful: if `gh` isn't installed or isn't authed, prints
        a `[CI FAILED RUNS READ: skipped — gh unavailable]` marker and
        returns. The check-registry-read.py hook accepts that form so
        contributors without `gh` aren't blocked.
        """
        gh_path = shutil.which("gh")
        if gh_path is None:
            self.stdout.write("[CI FAILED RUNS READ: skipped — gh unavailable]")
            return

        try:
            result = subprocess.run(  # nosec B603
                [
                    gh_path, "run", "list",
                    "--status", "failure",
                    "--limit", "10",
                    "--json", "databaseId,name,headBranch,conclusion,url,workflowName",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self.stdout.write("[CI FAILED RUNS READ: skipped — gh unavailable]")
            return

        if result.returncode != 0:
            # gh not authed, no remote, or some other transient failure.
            self.stdout.write("[CI FAILED RUNS READ: skipped — gh unavailable]")
            return

        try:
            runs = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            self.stdout.write("[CI FAILED RUNS READ: skipped — gh JSON unparseable]")
            return

        if not runs:
            self.stdout.write("[CI FAILED RUNS READ: 0 latest — no failed runs]")
            return

        run_ids = ", ".join(f"#{r['databaseId']}" for r in runs[:10])
        self.stdout.write(f"[CI FAILED RUNS READ: {len(runs)} latest — picked: {run_ids}]")
        for r in runs[:10]:
            self.stdout.write(
                f"  #{r['databaseId']} [{r.get('workflowName', '?')}/{r.get('name', '?')}] "
                f"on {r.get('headBranch', '?')} — {r.get('url', '')}"
            )

    def _print_coverage_gaps(self) -> None:
        """Print the top-10 open coverage-gap AutoIssues + the marker line.

        Coverage-gap AutoIssues are agent-filed entries with a title
        starting with `[coverage-gap]`. They live in the same AutoIssue
        table as everything else, but the ritual mandates a separate
        10-pick quota so coverage work doesn't get squeezed out by
        higher-severity telemetry findings.

        Drought form: when fewer than 10 are open, the marker uses
        `<K> picked + <10-K> filed` and the agent files new gap rows
        for missing Level A areas (see docs/CODE-COVERAGE-RULES.md).
        """
        qs = AutoIssue.objects.filter(
            status__in=_OPEN_STATUSES,
            source=AutoIssue.SOURCE_AGENT,
            title__startswith="[coverage-gap]",
        ).order_by("-priority_score", "spam_score", "-last_seen")
        rows = _unique_issue_rows(qs, 10)
        if not rows:
            self.stdout.write(
                "[COVERAGE GAPS READ: 0 picked + 10 to file — drought; file new "
                "AutoIssue(kind='coverage-gap') rows for missing Level A areas "
                "from docs/CODE-COVERAGE-RULES.md before claiming the ritual is done]"
            )
            return
        pick_ids = ", ".join(f"#{r.id}" for r in rows)
        if len(rows) < 10:
            self.stdout.write(
                f"[COVERAGE GAPS READ: {len(rows)} picked + {10 - len(rows)} to file — "
                f"#{pick_ids} (drought; file the remainder per docs/CODE-COVERAGE-RULES.md)]"
            )
        else:
            self.stdout.write(f"[COVERAGE GAPS READ: 10 picked — {pick_ids}]")
        for r in rows:
            self.stdout.write(
                f"  #{r.id} [agent/{r.severity}] {r.title[:90]}"
            )

    def _print_issue_table(self, rows: list[AutoIssue]) -> None:
        self.stdout.write("| ID | Source | Severity | Title | Files |")
        self.stdout.write("| --- | --- | --- | --- | --- |")
        for row in rows:
            self.stdout.write(_format_issue_row(row))


def _pick_unique_open_issues(
    *,
    limit: int,
    source: str | None,
) -> list[AutoIssue]:
    qs = AutoIssue.objects.filter(status__in=_OPEN_STATUSES)
    if source:
        qs = qs.filter(source=source)
    return _unique_issue_rows(
        qs.order_by("-priority_score", "spam_score", "-last_seen"),
        limit,
    )


def _unique_issue_rows(queryset, limit: int) -> list[AutoIssue]:
    rows: list[AutoIssue] = []
    seen_keys: set[str] = set()
    for issue in queryset.iterator():
        key = _issue_dedupe_key(issue)
        if key in seen_keys:
            continue
        rows.append(issue)
        seen_keys.add(key)
        if len(rows) == limit:
            break
    return rows


def _issue_dedupe_key(issue: AutoIssue) -> str:
    return issue.canonical_fingerprint or f"{issue.source}:{issue.external_id}"


def _format_issue_row(issue: AutoIssue) -> str:
    files = ", ".join(issue.affected_files[:3]) if issue.affected_files else "-"
    cells = (
        f"#{issue.id}",
        issue.source,
        issue.severity,
        _clip_cell(issue.title, _TITLE_WIDTH),
        _clip_cell(files, _FILES_WIDTH),
    )
    return "| " + " | ".join(_clean_cell(cell) for cell in cells) + " |"


def _clip_cell(value: str, width: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= width:
        return cleaned
    return cleaned[: width - 3] + "..."


def _clean_cell(value: str) -> str:
    return value.replace("|", "/")
