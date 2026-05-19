"""manage.py log_test_case — PARAMOUNT Test Case First rule command.

Files an `AutoIssue(category='test_case', status='open')` row that captures
the agent-readable implementation contract for a code change BEFORE the
code is written. The row's `lessons_learned` field holds the
`Given … When … Then …` triple plus optional extended fields
(edge_cases, failure_cases, security, usability, scalability,
maintainability, regression_risks).

Emits one of two markers:
  [TEST CASE WRITTEN: AutoIssue=#N id=<external_id> file=<src> agent=<name>]
  [TEST CASE DEDUPED: matched AutoIssue=#N]

Dedup happens on the canonical fingerprint of
`<title>::<first-file>::<given-when-then>`, matching the
`AutoIssue(category='test_case')` rows. Re-filing the same contract
increments `occurrence_count`.

Spec: docs/TEST-CASE-FIRST-RULE.md
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.concept_tags import collect_and_validate_tags, merge_tags
from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.auto_issues.services.fingerprinting import canonical_fingerprint


_CATEGORY_KEY = "test_case"
_CATEGORY_LABEL = "Test case spec"
_CATEGORY_DESC = (
    "Agent-readable implementation contract written BEFORE code edits. "
    "Captures Given/When/Then plus extended fields (edge_cases, "
    "failure_cases, security, usability, scalability, maintainability, "
    "regression_risks) so the next agent has a real spec to read for the "
    "touched surface. Required by the paramount Test Case First rule "
    "(docs/TEST-CASE-FIRST-RULE.md); deduped via canonical_fingerprint so "
    "repeated filings on the same title+file+Given/When/Then triple "
    "collapse into one row with a bumped occurrence_count."
)

_MAX_TITLE_CHARS = 512
_MAX_FIELD_CHARS = 800


def _get_or_create_category() -> AutoIssueCategory:
    cat, created = AutoIssueCategory.objects.get_or_create(
        key=_CATEGORY_KEY,
        defaults={
            "label": _CATEGORY_LABEL,
            "description": _CATEGORY_DESC,
            "sort_order": 215,
        },
    )
    if not created and (
        cat.label != _CATEGORY_LABEL or cat.description != _CATEGORY_DESC
    ):
        cat.label = _CATEGORY_LABEL
        cat.description = _CATEGORY_DESC
        cat.save(update_fields=["label", "description"])
    return cat


def _check_length(value: str, field: str, cap: int) -> None:
    if len(value) > cap:
        raise CommandError(
            f"FAIL log_test_case: --{field} is {len(value)} chars; cap is "
            f"{cap} chars.\n"
            f"WHY: short, scannable contracts get read; long-form belongs "
            f"in a paper-trail entry that the test case row can link to "
            f"via --related-autoissues.\n"
            f"UNBLOCK: trim the input, or file a paper-trail entry via "
            f"`manage.py defer_work` and reference its #id from the contract."
        )


def _format_lessons(parts: dict[str, str]) -> str:
    """Render the Given/When/Then + extended fields as the lessons_learned string."""
    lines: list[str] = [
        f"Given {parts['given']}",
        f"When {parts['when']}",
        f"Then {parts['then']}",
    ]
    extended = (
        ("Edge cases", parts.get("edge_cases")),
        ("Failure cases", parts.get("failure_cases")),
        ("Security", parts.get("security")),
        ("Usability", parts.get("usability")),
        ("Scalability", parts.get("scalability")),
        ("Maintainability", parts.get("maintainability")),
        ("Regression risks", parts.get("regression_risks")),
    )
    for label, value in extended:
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


class Command(BaseCommand):
    help = (
        "File a test case spec as an AutoIssue BEFORE code edits. "
        "Required by docs/TEST-CASE-FIRST-RULE.md."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--file", action="append", dest="files", required=True,
                            help="Production source file(s) this contract governs.")
        parser.add_argument("--title", required=True,
                            help="Short noun-phrase title (<= 512 chars).")
        parser.add_argument("--given", required=True,
                            help="BDD: the pre-condition the code can assume.")
        parser.add_argument("--when", required=True,
                            help="BDD: the action / input / system event.")
        parser.add_argument("--then", required=True,
                            help="BDD: the expected result / behaviour.")
        parser.add_argument("--edge-cases", default="",
                            help="Boundary conditions, malformed input, off-by-one.")
        parser.add_argument("--failure-cases", default="",
                            help="What the code must do when inputs are invalid.")
        parser.add_argument("--security", default="",
                            help="Auth, input sanitisation, secret handling.")
        parser.add_argument("--usability", default="",
                            help="Plain English, accessibility, error pages.")
        parser.add_argument("--scalability", default="",
                            help="Behaviour at 10x and 100x typical load.")
        parser.add_argument("--maintainability", default="",
                            help="How the next agent can repair / extend this code.")
        parser.add_argument("--regression-risks", default="",
                            help="Existing behaviour that could break.")
        parser.add_argument("--related-files", action="append", dest="related_files",
                            default=[], help="Other files likely to be touched together.")
        parser.add_argument("--related-tests", action="append", dest="related_tests",
                            default=[], help="Existing automated tests.")
        parser.add_argument("--related-autoissues", action="append",
                            dest="related_autoissues", default=[],
                            help="Prior fixes / lessons / duplicates.")
        parser.add_argument("--concept-tag", action="append", default=[],
                            help="Approved concept tag; repeat for more than one.")
        parser.add_argument("--agent", default="claude",
                            help="Agent name (claude, codex, gemini, …).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Show what would be filed without writing to the DB.")

    def handle(self, *args, **opts) -> None:
        files: list[str] = [f.strip() for f in opts["files"] if f.strip()]
        if not files:
            raise CommandError("FAIL log_test_case: at least one --file is required.")
        title: str = opts["title"].strip()
        given: str = opts["given"].strip()
        when: str = opts["when"].strip()
        then: str = opts["then"].strip()
        if not title or not given or not when or not then:
            raise CommandError(
                "FAIL log_test_case: --title, --given, --when, --then are all required "
                "and must be non-empty plain-English sentences.\n"
                "WHY: the next agent reads the contract via "
                "`manage.py read_scoped_lessons --area <path>` and needs all four parts "
                "(title + BDD triple) to know what the code must do.\n"
                "UNBLOCK: pass --title \"...\" --given \"...\" --when \"...\" --then \"...\""
            )
        _check_length(title, "title", _MAX_TITLE_CHARS)
        for f, v in (("given", given), ("when", when), ("then", then)):
            _check_length(v, f, _MAX_FIELD_CHARS)

        parts = {
            "given": given,
            "when": when,
            "then": then,
            "edge_cases": opts["edge_cases"].strip(),
            "failure_cases": opts["failure_cases"].strip(),
            "security": opts["security"].strip(),
            "usability": opts["usability"].strip(),
            "scalability": opts["scalability"].strip(),
            "maintainability": opts["maintainability"].strip(),
            "regression_risks": opts["regression_risks"].strip(),
        }
        for label, value in (
            ("edge-cases", parts["edge_cases"]),
            ("failure-cases", parts["failure_cases"]),
            ("security", parts["security"]),
            ("usability", parts["usability"]),
            ("scalability", parts["scalability"]),
            ("maintainability", parts["maintainability"]),
            ("regression-risks", parts["regression_risks"]),
        ):
            if value:
                _check_length(value, label, _MAX_FIELD_CHARS)

        agent: str = opts["agent"].strip()[:64]
        related_files: list[str] = [s.strip() for s in opts["related_files"] if s.strip()]
        related_tests: list[str] = [s.strip() for s in opts["related_tests"] if s.strip()]
        related_autoissues: list[str] = [
            s.strip() for s in opts["related_autoissues"] if s.strip()
        ]
        concept_tags = collect_and_validate_tags(opts)

        fingerprint_basis = f"{title}::{files[0]}::{given}::{when}::{then}"
        canonical = canonical_fingerprint(fingerprint_basis)
        ext_id = f"tc::{canonical}"

        if opts["dry_run"]:
            self.stdout.write(
                f"[TEST CASE DRY-RUN: would file id={ext_id} file={files[0]} "
                f"agent={agent}]"
            )
            return

        category = _get_or_create_category()
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
                    "source": "test_case",
                    "external_id": f"{ext_id}::{existing.occurrence_count}",
                    "first_seen": (
                        existing.first_seen.isoformat()
                        if existing.first_seen else now.isoformat()
                    ),
                    "last_seen": now.isoformat(),
                    "occurrence_count": existing.occurrence_count,
                    "agent": agent,
                },
            ]
            existing.concept_tags = merge_tags(existing.concept_tags, concept_tags)
            existing.save()
            self.stdout.write(
                f"[TEST CASE DEDUPED: matched AutoIssue=#{existing.pk}]"
            )
            return

        lessons = _format_lessons(parts)
        description = (
            f"Test case spec filed by {agent} at {now.isoformat()} for "
            f"{', '.join(files)}. Implementation must satisfy the BDD triple "
            f"plus extended fields in lessons_learned."
        )

        ai = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id=ext_id,
            fingerprint=ext_id[:64],
            canonical_fingerprint=canonical,
            title=title[:512],
            description=description,
            affected_files=files,
            severity=AutoIssue.SEVERITY_LOW,
            category=category,
            status=AutoIssue.STATUS_OPEN,
            lessons_learned=lessons,
            concept_tags=concept_tags,
            occurrence_count=1,
            last_seen=now,
            source_observations=[
                {
                    "source": "test_case",
                    "external_id": ext_id,
                    "first_seen": now.isoformat(),
                    "last_seen": now.isoformat(),
                    "occurrence_count": 1,
                    "agent": agent,
                    "related_files": related_files,
                    "related_tests": related_tests,
                    "related_autoissues": related_autoissues,
                }
            ],
        )
        self.stdout.write(
            f"[TEST CASE WRITTEN: AutoIssue=#{ai.pk} id={ext_id} "
            f"file={files[0]} agent={agent}]"
        )
