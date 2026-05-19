"""manage.py log_tdd_lesson — PARAMOUNT strict-TDD rule command.

Creates an `AutoIssue(category='tdd_lesson', status='resolved')` row that
captures one Red→Green→Refactor cycle as a durable lesson. The row's
`lessons_learned` field holds the two-part `Trap: ... Fix shape: ...`
payload the rest of the lesson system already consumes via
`manage.py read_scoped_lessons --area <path>`.

Emits one of two markers:
  [TDD LESSON LOGGED: AutoIssue=#N file=<src> red_test=<test>]
  [TDD LESSON DEDUPED: matched AutoIssue=#N]

Hard rejects malformed input — the strict-TDD hook
(`.githooks/check-tdd-strict.py`) verifies the resulting AutoIssue exists
before letting any code-changing commit land, so a partial / fake call
breaks the commit at hook time.

Spec: docs/TDD-STRICT-RULE.md
"""

from __future__ import annotations

from datetime import datetime, timezone as dt_tz

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.concept_tags import collect_and_validate_tags, merge_tags
from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.auto_issues.services.fingerprinting import canonical_fingerprint


_CATEGORY_KEY = "tdd_lesson"
_CATEGORY_LABEL = "TDD Red-Green-Refactor lesson"
_CATEGORY_DESC = (
    "One Red-Green-Refactor cycle captured as a durable lesson. "
    "Holds the trap (what was not obvious about the code area that made "
    "the test fail initially) and the fix shape (what specific change "
    "pattern turned Red into Green). Required by the paramount strict-TDD "
    "rule; deduped via canonical_fingerprint so repeated cycles on the same "
    "file + test combination collapse into one row."
)
_MAX_TRAP_CHARS = 800
_MAX_FIX_SHAPE_CHARS = 800
_MAX_REFACTOR_CHARS = 400


def _get_or_create_category() -> AutoIssueCategory:
    cat, _ = AutoIssueCategory.objects.get_or_create(
        key=_CATEGORY_KEY,
        defaults={
            "label": _CATEGORY_LABEL,
            "description": _CATEGORY_DESC,
            "sort_order": 210,
        },
    )
    return cat


def _parse_iso8601(value: str, field: str) -> datetime:
    """Strict ISO-8601 parse so the hook can compare red < green."""
    try:
        # Python's fromisoformat accepts the common shapes including 'Z'
        # since 3.11. We normalise Z → +00:00 for older interpreters.
        normalised = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(normalised).astimezone(dt_tz.utc)
    except ValueError as exc:
        raise CommandError(
            f"FAIL log_tdd_lesson: --{field} {value!r} is not a valid ISO-8601 "
            f"timestamp (try 2026-05-17T04:01:12Z).\n"
            f"WHY: the strict-TDD hook compares red_run_at < green_run_at to "
            f"prove the test was actually Red before Green; an unparseable "
            f"timestamp defeats that check.\n"
            f"UNBLOCK: capture the timestamp via `date -u +'%Y-%m-%dT%H:%M:%SZ'` "
            f"around the test runs and pass that string."
        ) from exc


def _format_coverage_summary(coverage: dict[str, str]) -> str:
    """Render the 5-layer coverage breakdown as a single-line summary string.

    Returns an empty string when every field is empty (caller skipped all
    --edge-cases / --resource-release / --latency / --smoke / --e2e flags).
    Otherwise returns 'edge_cases=2 resource_release=1 latency=N/A:"..." smoke=1 e2e=1'.
    """
    if not any(v for v in coverage.values()):
        return ""
    parts: list[str] = []
    for key in ("edge_cases", "resource_release", "latency", "smoke", "e2e"):
        raw = coverage.get(key, "").strip()
        if not raw:
            parts.append(f"{key}=unspecified")
            continue
        if raw.startswith("N/A"):
            # Normalise to N/A:"..." quoting.
            after = raw.split(":", 1)[1].strip() if ":" in raw else ""
            inner = after.strip().strip('"')
            parts.append(f'{key}=N/A:"{inner}"')
        else:
            parts.append(f"{key}={raw}")
    return " ".join(parts)


class Command(BaseCommand):
    help = (
        "Log one Red-Green-Refactor cycle as an AutoIssue lesson. "
        "Required by docs/TDD-STRICT-RULE.md."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--file", required=True,
                            help="Production source file the cycle touched.")
        parser.add_argument("--red-test", required=True,
                            help="Test file that was Red.")
        parser.add_argument("--red-test-name", default="",
                            help="Specific test function/case name (recommended).")
        parser.add_argument("--red-run-at", required=True,
                            help="ISO-8601 timestamp when the failing run was observed.")
        parser.add_argument("--green-run-at", required=True,
                            help="ISO-8601 timestamp when the passing run was observed.")
        parser.add_argument("--trap", required=True,
                            help="Plain-English: what was NOT obvious that made the test fail.")
        parser.add_argument("--fix-shape", required=True,
                            help="Plain-English: what specific change turned Red into Green.")
        parser.add_argument("--refactor", default="",
                            help="Optional one-line refactor summary, or empty for none.")
        parser.add_argument("--agent", default="claude",
                            help="Agent name (claude, codex, gemini, …).")
        # 2026-05-17 — 5-layer coverage breakdown. Each accepts an integer
        # count OR 'N/A:<reason>'. The values land in the source observation
        # and the lessons_learned tail so the next agent sees the coverage
        # decisions when running read_scoped_lessons.
        parser.add_argument("--edge-cases", default="",
                            help="Count of edge-case tests, or 'N/A:<reason>'.")
        parser.add_argument("--resource-release", default="",
                            help="Count of resource-release tests, or 'N/A:<reason>'.")
        parser.add_argument("--latency", default="",
                            help="Count of latency tests, or 'N/A:<reason>'.")
        parser.add_argument("--smoke", default="",
                            help="Count of smoke tests, or 'N/A:<reason>'.")
        parser.add_argument("--e2e", default="",
                            help="Count of E2E tests, or 'N/A:<reason>'.")
        parser.add_argument("--concept-tag", action="append", default=[],
                            help="Approved concept tag; repeat for more than one.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Validate inputs without writing the AutoIssue row.")

    def handle(self, *args, **opts) -> None:
        source_file: str = opts["file"].strip()
        red_test: str = opts["red_test"].strip()
        red_test_name: str = opts["red_test_name"].strip()
        red_at = _parse_iso8601(opts["red_run_at"].strip(), "red-run-at")
        green_at = _parse_iso8601(opts["green_run_at"].strip(), "green-run-at")
        trap: str = opts["trap"].strip()
        fix_shape: str = opts["fix_shape"].strip()
        refactor: str = opts["refactor"].strip()
        agent: str = opts["agent"].strip()[:64]
        coverage = {
            "edge_cases": opts["edge_cases"].strip(),
            "resource_release": opts["resource_release"].strip(),
            "latency": opts["latency"].strip(),
            "smoke": opts["smoke"].strip(),
            "e2e": opts["e2e"].strip(),
        }
        concept_tags = collect_and_validate_tags(opts)

        if green_at <= red_at:
            raise CommandError(
                f"FAIL log_tdd_lesson: --green-run-at ({green_at.isoformat()}) is not "
                f"strictly AFTER --red-run-at ({red_at.isoformat()}).\n"
                f"WHY: the cycle's evidence requires the failing run to happen "
                f"BEFORE the passing run. Equal or reversed timestamps mean the "
                f"test was never actually Red.\n"
                f"UNBLOCK: rerun the failing test, capture its timestamp, then "
                f"rerun the passing test and capture that one. Pass both."
            )
        if not trap or not fix_shape:
            raise CommandError(
                "FAIL log_tdd_lesson: --trap and --fix-shape are both required and "
                "must be non-empty plain-English sentences.\n"
                "WHY: the next agent reads the lesson via "
                "`manage.py read_scoped_lessons --area <path>` and needs both halves "
                "(what was not obvious + what worked) to avoid the same trap.\n"
                "UNBLOCK: pass --trap \"...\" --fix-shape \"...\" each ≤ 800 chars."
            )
        if len(trap) > _MAX_TRAP_CHARS or len(fix_shape) > _MAX_FIX_SHAPE_CHARS:
            raise CommandError(
                f"FAIL log_tdd_lesson: --trap and --fix-shape are each capped at "
                f"{_MAX_TRAP_CHARS} chars (got trap={len(trap)}, fix-shape={len(fix_shape)}).\n"
                f"WHY: short, scannable lessons get read; long-form belongs in a "
                f"paper-trail entry that the lesson row can link to.\n"
                f"UNBLOCK: trim the inputs, or file a paper-trail entry via "
                f"`manage.py defer_work` and reference its #id from the lesson."
            )
        if len(refactor) > _MAX_REFACTOR_CHARS:
            raise CommandError(
                f"FAIL log_tdd_lesson: --refactor caps at {_MAX_REFACTOR_CHARS} chars."
            )

        if opts.get("dry_run"):
            self.stdout.write(
                f"[TDD LESSON DRY-RUN: would file lesson for file={source_file} "
                f"red_test={red_test}]"
            )
            return

        category = _get_or_create_category()
        test_title = f"{red_test}::{red_test_name}"
        canonical = canonical_fingerprint(file=source_file, title=test_title)

        existing = AutoIssue.objects.filter(
            canonical_fingerprint=canonical,
            category=category,
        ).first()
        now = timezone.now()
        if existing is not None:
            existing.occurrence_count += 1
            existing.last_seen = now
            observation = {
                "source": "tdd_cycle",
                "external_id": f"tdd::{canonical}::{existing.occurrence_count}",
                "first_seen": existing.first_seen.isoformat() if existing.first_seen else now.isoformat(),
                "last_seen": now.isoformat(),
                "occurrence_count": existing.occurrence_count,
                "red_run_at": red_at.isoformat(),
                "green_run_at": green_at.isoformat(),
                "agent": agent,
            }
            existing.source_observations = [
                *(existing.source_observations or []),
                observation,
            ]
            existing.concept_tags = merge_tags(existing.concept_tags, concept_tags)
            existing.save()
            self.stdout.write(
                f"[TDD LESSON DEDUPED: matched AutoIssue=#{existing.pk}]"
            )
            return

        lessons = (
            f"Trap: {trap}\n"
            f"Fix shape: {fix_shape}"
        )
        if refactor:
            lessons += f"\nRefactor: {refactor}"
        coverage_summary = _format_coverage_summary(coverage)
        if coverage_summary:
            lessons += f"\nCoverage: {coverage_summary}"

        ext_id = f"tdd::{canonical}"
        title = f"TDD cycle: {source_file} ↔ {red_test}"[:512]
        description = (
            f"Red at {red_at.isoformat()}: {red_test}"
            f"{('::' + red_test_name) if red_test_name else ''}\n"
            f"Green at {green_at.isoformat()}: {source_file}\n"
            f"Refactor: {refactor or 'none'}\n"
            f"Logged by {agent}."
        )

        ai = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id=ext_id,
            fingerprint=ext_id[:64],
            canonical_fingerprint=canonical,
            title=title,
            description=description,
            affected_files=[source_file, red_test],
            severity=AutoIssue.SEVERITY_LOW,
            category=category,
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=now,
            resolved_by=agent,
            lessons_learned=lessons,
            concept_tags=concept_tags,
            occurrence_count=1,
            last_seen=now,
            source_observations=[
                {
                    "source": "tdd_cycle",
                    "external_id": ext_id,
                    "first_seen": now.isoformat(),
                    "last_seen": now.isoformat(),
                    "occurrence_count": 1,
                    "red_run_at": red_at.isoformat(),
                    "green_run_at": green_at.isoformat(),
                    "red_test_name": red_test_name,
                    "agent": agent,
                }
            ],
        )
        self.stdout.write(
            f"[TDD LESSON LOGGED: AutoIssue=#{ai.pk} file={source_file} "
            f"red_test={red_test}]"
        )
