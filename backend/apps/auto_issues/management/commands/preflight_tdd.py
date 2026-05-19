"""manage.py preflight_tdd — arm the TDD pipeline at session start.

Session-start gate command for the PARAMOUNT TDD-pipeline rule. Prints a
`[TDD PREFLIGHT: …]` marker that the matching `.githooks/check-tdd-preflight.py`
hook validates at commit time.

The marker carries:
  * `pipeline=SPEC→TEST_CASE→TDD→CODE→CODE_REVIEW→LESSON` — the de-facto coding shape.
  * A human-readable `[TDD PREFLIGHT PIPELINE: ...]` line that explains the
    six stages for a non-coder operator and the next agent.
  * Eight pipeline switches (`spec_citation`, `test_case_mandate`,
    `tdd_red_green_refactor`, `5_layer_coverage`, `code_review_logging`,
    `lesson_logging`, `decision_point`, `artefact_pruning`) — each `on` once
    the matching hook / command exists.
  * `session_id=<uuid4|user-supplied>` so the hook can correlate the same
    session across multiple commits.
  * `armed_at=<ISO8601 UTC>` so the next agent can see how fresh the arm is.

Bootstraps the five AutoIssueCategory rows the pipeline depends on
(`test_case`, `tdd_lesson`, `code_review_lesson`, `hook_failure`,
`decision_point`) via `get_or_create`, which is idempotent — the command
is safe to run as many times per session as you like.

Spec ref: docs/TDD-PIPELINE-RULE.md (to be authored in Session S4).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone as dt_tz

from django.core.management.base import BaseCommand

from apps.auto_issues.models import AutoIssueCategory


_PIPELINE = "SPEC→TEST_CASE→TDD→CODE→CODE_REVIEW→LESSON"
_PIPELINE_GUIDE = (
    "[TDD PREFLIGHT PIPELINE: "
    "SPEC (source-backed)=what to build, why, citations -> "
    "TEST CASE (10 BDD fields)=agent-readable contract derived from the spec -> "
    "TDD (red -> green -> refactor)=implementation METHOD -> "
    "CODE -> "
    "CODE REVIEW=after-the-fact check -> "
    "LESSON=persisted for the next agent]"
)

_REQUIRED_CATEGORIES: tuple[tuple[str, str, str, int], ...] = (
    (
        "test_case",
        "Test case (BDD contract)",
        "Given/When/Then test-case AutoIssue authored before the code is written.",
        205,
    ),
    (
        "tdd_lesson",
        "TDD Red-Green-Refactor lesson",
        "One Red-Green-Refactor cycle captured as a durable lesson.",
        210,
    ),
    (
        "code_review_lesson",
        "Code review lesson",
        "Self-review finding captured after the diff is staged.",
        215,
    ),
    (
        "hook_failure",
        "Pre-commit hook failure",
        "Auto-logged when any pre-commit hook exits non-zero.",
        220,
    ),
    (
        "decision_point",
        "Post-commit decision point",
        (
            "Post-commit retrospective finding (improvement / warning / problem / "
            "missing-spec / off-track-test-case / off-track-TDD) filed by the "
            "post-commit Decision Point ritual."
        ),
        225,
    ),
)

_SWITCH_KEYS: tuple[str, ...] = (
    "spec_citation",
    "test_case_mandate",
    "tdd_red_green_refactor",
    "5_layer_coverage",
    "code_review_logging",
    "lesson_logging",
    "decision_point",
    "artefact_pruning",
    # 2026-05-18 user directive: "nothing should be bypassed and that to the
    # session preflight." The session asserts no-bypass at arm time so any
    # downstream attempt to use --no-verify, skip hooks, or weaken the chain
    # is caught against the armed contract.
    "no_bypass",
    # The disk-backed per-file search_resolved_issues mandate is armed at
    # preflight so the chain can refuse commits that lack the audit log
    # entry per file per task.
    "per_file_lookup",
    # Pre-commit lookup of past commit failures (parallels per_file_lookup
    # but scoped to commit-failure recurrence).
    "commit_failure_lookup",
)


def _bootstrap_categories() -> None:
    """Idempotent: create the five required AutoIssueCategory rows if absent."""
    for key, label, description, sort_order in _REQUIRED_CATEGORIES:
        AutoIssueCategory.objects.get_or_create(
            key=key,
            defaults={
                "label": label,
                "description": description,
                "sort_order": sort_order,
            },
        )


def _now_iso8601_z() -> str:
    """UTC ISO-8601 with a trailing `Z` so the hook's strict parser accepts it."""
    return datetime.now(dt_tz.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_marker(session_id: str, armed_at: str) -> str:
    switches = " ".join(f"{key}=on" for key in _SWITCH_KEYS)
    return (
        f"[TDD PREFLIGHT: pipeline={_PIPELINE} "
        f"{switches} "
        f"session_id={session_id} armed_at={armed_at}]"
    )


class Command(BaseCommand):
    help = (
        "Arm the TDD pipeline at session start. Prints a [TDD PREFLIGHT: …] "
        "marker that the matching pre-commit hook validates."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--session-id",
            default="",
            help="Optional explicit session id (default: a fresh UUID4).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate inputs and bootstrap categories without printing the real marker.",
        )

    def handle(self, *args, **opts) -> None:
        session_id = (opts.get("session_id") or "").strip() or str(uuid.uuid4())
        armed_at = _now_iso8601_z()

        # Bootstrap is cheap and idempotent — safe in dry-run too because it
        # only inserts missing category rows; never deletes or modifies.
        _bootstrap_categories()

        if opts.get("dry_run"):
            self.stdout.write(
                f"[TDD PREFLIGHT DRY-RUN: would arm session_id={session_id} at {armed_at}]"
            )
            return

        self.stdout.write(_build_marker(session_id, armed_at))
        self.stdout.write(_PIPELINE_GUIDE)
