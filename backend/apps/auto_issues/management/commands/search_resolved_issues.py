"""Search resolved AutoIssue rows by area / keyword / fingerprint.

Used by every agent at session start AFTER `print_open_issues`. The
question this answers: "did anyone fix something in this area before,
and what did they learn?". Output is a compact list with one row per
match — id, last-resolved date, title, lessons_learned excerpt.

Examples:
    manage.py search_resolved_issues --area backend/apps/audit
    manage.py search_resolved_issues --keyword "fingerprint collision"
    manage.py search_resolved_issues --fingerprint <16-char-hash>

If no match is found the command exits 0 with a single "no prior
fixes found in this area" line — the absence of prior fixes is itself
information for the agent.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.auto_issues.concept_tags import build_tag_query, collect_and_validate_tags
from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import resolved_issue_index


class Command(BaseCommand):
    help = "Search resolved AutoIssue rows by area / keyword / fingerprint."

    _DEFAULT_LIMIT = 10
    _DEFAULT_SCAN_LIMIT = 500

    def add_arguments(self, parser):
        parser.add_argument(
            "--area",
            action="append",
            help=(
                "Repo-relative path or path prefix; matches anything in "
                "`affected_files`. Can be repeated. Example: backend/apps/audit"
            ),
        )
        parser.add_argument(
            "--keyword",
            help=(
                "Free-text token to match against title / description / "
                "lessons_learned. Case-insensitive."
            ),
        )
        parser.add_argument(
            "--fingerprint",
            help="Exact fingerprint match (16-char hex). For dedup checks.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=self._DEFAULT_LIMIT,
            help=f"Max matches to print (default {self._DEFAULT_LIMIT}).",
        )
        parser.add_argument(
            "--tag",
            action="append",
            default=[],
            help="Approved concept tag; repeat for more than one.",
        )
        parser.add_argument(
            "--scan-limit",
            type=int,
            default=self._DEFAULT_SCAN_LIMIT,
            help=(
                "Max resolved rows to inspect for path-prefix matching "
                f"(default {self._DEFAULT_SCAN_LIMIT})."
            ),
        )
        parser.add_argument(
            "--agent",
            default="",
            help=(
                "Override the agent name recorded in the audit log. "
                "Defaults to claude / codex / gemini detection via XF_AGENT."
            ),
        )

    def handle(self, *args, **opts):
        limit = _positive_int(opts["limit"], fallback=self._DEFAULT_LIMIT)
        scan_limit = _positive_int(opts["scan_limit"], fallback=self._DEFAULT_SCAN_LIMIT)
        tags = collect_and_validate_tags(opts, key="tag")
        qs = AutoIssue.objects.filter(status=AutoIssue.STATUS_RESOLVED)
        if opts["fingerprint"]:
            qs = qs.filter(fingerprint=opts["fingerprint"])
        if opts["keyword"]:
            kw = opts["keyword"]
            qs = qs.filter(
                Q(title__icontains=kw)
                | Q(description__icontains=kw)
                | Q(lessons_learned__icontains=kw)
            )
        candidates = list(qs.order_by("-resolved_at")[:scan_limit])
        if tags:
            tagged = qs.filter(build_tag_query(tags)).order_by("-resolved_at")
            candidates = _dedupe_rows([*tagged[:scan_limit], *candidates])
        areas = _as_area_list(opts["area"])
        task_id = resolved_issue_index.current_task_id()
        agent = opts.get("agent") or _detect_agent()
        if len(areas) > 1:
            self._write_multiple_area_results(
                candidates,
                areas=areas,
                limit=limit,
                tags=tags,
                task_id=task_id,
                agent=agent,
            )
            return
        rows = _matching_rows(
            candidates,
            area=areas[0] if areas else None,
            limit=limit,
            tags=tags,
        )

        # Disk-backed audit log: one entry per area lookup. Required by the
        # 2026-05-18 user rule; a memory-only lookup does not satisfy the
        # mandate. We still write the entry when zero results are found,
        # because zero-results is itself information for the agent.
        if areas:
            resolved_issue_index.append_audit_entry(
                file_path=areas[0],
                task_id=task_id,
                agent=agent,
                result_count=len(rows),
                result_ids=[r.id for r in rows],
            )

        if not rows:
            self.stdout.write("[RESOLVED SEARCH: 0 matches — no prior fixes found in this area]")
            return

        self.stdout.write(f"[RESOLVED SEARCH: {len(rows)} prior fix(es) — read these BEFORE rewriting]")
        for r in rows:
            date = r.resolved_at.strftime("%Y-%m-%d") if r.resolved_at else "????-??-??"
            files = ",".join(r.affected_files[:3]) if r.affected_files else "—"
            self.stdout.write(
                f"  #{r.id} ({date}) [{r.source}/{r.severity}] {r.title[:80]}"
            )
            if r.lessons_learned:
                # Print up to two lines of the lesson — first is the trap
                # description, second is typically the fix shape.
                first_two = "\n      ".join(
                    r.lessons_learned.strip().splitlines()[:2]
                )
                self.stdout.write(f"      lesson: {first_two}")
            self.stdout.write(f"      files: {files}")

    def _write_multiple_area_results(
        self,
        candidates: list[AutoIssue],
        *,
        areas: list[str],
        limit: int,
        tags: list[str],
        task_id: str,
        agent: str,
    ) -> None:
        for area in areas:
            rows = _matching_rows(candidates, area=area, limit=limit, tags=tags)
            # Append one audit entry per --area; zero-result entries still count
            # as evidence that the lookup ran.
            resolved_issue_index.append_audit_entry(
                file_path=area,
                task_id=task_id,
                agent=agent,
                result_count=len(rows),
                result_ids=[r.id for r in rows],
            )
            if not rows:
                self.stdout.write(f"[RESOLVED SEARCH: {area}: 0 matches]")
                continue
            self.stdout.write(f"[RESOLVED SEARCH: {area}: {len(rows)} prior fix(es)]")
            for row in rows:
                date = row.resolved_at.strftime("%Y-%m-%d") if row.resolved_at else "????-??-??"
                self.stdout.write(f"  #{row.id} ({date}) {row.title[:80]}")


def _matching_rows(
    rows,
    *,
    area: str | None,
    limit: int,
    tags: list[str] | None = None,
) -> list[AutoIssue]:
    matches: list[AutoIssue] = []
    for row in rows:
        tag_match = bool(tags and _row_has_any_tag(row, tags))
        area_match = bool(area and _row_touches_area(row, area))
        if area and not (area_match or tag_match):
            continue
        if not area and tags and not tag_match:
            continue
        matches.append(row)
        if len(matches) >= limit:
            break
    return matches


def _dedupe_rows(rows: list[AutoIssue]) -> list[AutoIssue]:
    seen: set[int] = set()
    unique_rows: list[AutoIssue] = []
    for row in rows:
        if row.id in seen:
            continue
        seen.add(row.id)
        unique_rows.append(row)
    return unique_rows


def _row_has_any_tag(row: AutoIssue, tags: list[str]) -> bool:
    return bool(set(row.concept_tags or []).intersection(tags))


def _row_touches_area(row: AutoIssue, area: str) -> bool:
    normalised_area = _normalise_path(area)
    for file_path in row.affected_files or []:
        normalised_file = _normalise_path(str(file_path))
        if normalised_file == normalised_area or normalised_file.startswith(
            f"{normalised_area}/"
        ):
            return True
    return False


def _normalise_path(path: str) -> str:
    return path.replace("\\", "/").strip().strip("/")


def _as_area_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _positive_int(value: int, *, fallback: int) -> int:
    return value if isinstance(value, int) and value > 0 else fallback


def _detect_agent() -> str:
    """Best-effort agent detection from environment; defaults to claude."""
    import os
    value = os.environ.get("XF_AGENT", "").strip().lower()
    if value in {"claude", "codex", "gemini", "antigravity"}:
        return value
    return "claude"
