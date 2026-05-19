"""manage.py defer_work — file a new paper-trail deferral.

Resolves AutoIssue-equivalent: every deliberately deferred work item
flows through this command so the database is authoritative.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.services import dedup as dedup_service
from apps.paper_trail.services.evidence import (
    REQUIRED_BDD_FIELDS,
    validate_citation,
    validate_test_case_completeness,
)
from apps.paper_trail.services.priority import compute_priority_score


_VALID_CATEGORIES = {c[0] for c in PaperTrailEntry.CATEGORY_CHOICES}
_VALID_SEVERITIES = {c[0] for c in PaperTrailEntry.SEVERITY_CHOICES}


class Command(BaseCommand):
    help = "File a new paper-trail deferral entry (or bump an existing one on dupe)."

    def add_arguments(self, parser):
        parser.add_argument("--title", required=True)
        parser.add_argument("--category", required=True, choices=sorted(_VALID_CATEGORIES))
        parser.add_argument("--abstract", required=True)
        parser.add_argument("--deferred-by", required=True)
        parser.add_argument("--severity", default=PaperTrailEntry.SEVERITY_MEDIUM,
                            choices=sorted(_VALID_SEVERITIES))
        parser.add_argument("--linked-autoissue", type=int, default=None)
        parser.add_argument("--linked-registry-id", default="")
        parser.add_argument("--deferred-in-handoff", default="")
        parser.add_argument("--deferral-reason-key", default="multi_session")
        parser.add_argument("--similarity-threshold", type=float, default=0.85)
        parser.add_argument("--next-action", action="append", default=[])
        parser.add_argument("--affected-file", action="append", default=[])
        parser.add_argument("--blocker", action="append", default=[])
        parser.add_argument("--required-skill", action="append", default=[])
        parser.add_argument("--complexity", default="M", choices=["XS", "S", "M", "L", "XL"])
        parser.add_argument("--estimated-hours", type=float, default=0.0)
        parser.add_argument(
            "--risk-on-inaction",
            default="",
            help="Required: plain-English risk if this work is never done.",
        )
        parser.add_argument("--resolution-criteria", default="")
        # Required-on-new (2026-05-16). Plain-English FAIL on missing.
        parser.add_argument(
            "--acceptance-criteria",
            default="",
            help=(
                "Required: bullet list or sentence describing the checks "
                "that prove this entry can be marked resolved."
            ),
        )
        parser.add_argument(
            "--evidence-level",
            default=PaperTrailEntry.EVIDENCE_LOW,
            choices=[c[0] for c in PaperTrailEntry.EVIDENCE_CHOICES],
            help=(
                "How well-grounded the entry's claims are. `cited` "
                "requires a patent / DOI / RFC / URL in the abstract."
            ),
        )
        parser.add_argument(
            "--supersedes",
            type=int,
            action="append",
            default=[],
            help=(
                "ID of an existing paper-trail entry this one replaces. "
                "Can be repeated. The old rows will be marked status=superseded."
            ),
        )
        # Paper Trail Evidence Rule (2026-05-17). Required on every new
        # entry from the cutoff onward. See docs/PAPER-TRAIL-EVIDENCE-RULE.md.
        parser.add_argument(
            "--test-case-autoissue",
            type=int,
            default=None,
            help=(
                "PK of the AutoIssue(category='test_case') row whose "
                "lessons_learned carries the FULL 10-field BDD contract "
                "(Given + When + Then + edge_cases + failure_cases + "
                "security + usability + scalability + maintainability + "
                "regression_risks). Required on entries from 2026-05-17 "
                "onward per docs/PAPER-TRAIL-EVIDENCE-RULE.md."
            ),
        )
        parser.add_argument(
            "--citation",
            action="append",
            dest="citations",
            default=[],
            help=(
                "Stable identifier for a patent, DOI, arXiv, ISO/IEEE/IETF "
                "standard, RFC, ISBN, or URL on the official-vendor "
                "allowlist. Repeatable. Required (>= 1) on entries from "
                "2026-05-17 onward."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate all inputs without writing the paper-trail row.",
        )

    def handle(self, *args, **opts):
        abstract = opts["abstract"].strip()
        word_count = len(abstract.split())
        if word_count > 1200:
            raise CommandError(
                f"FAIL defer_work: abstract exceeds 1200 words (got {word_count}).\n"
                "WHY: Paper-trail abstracts are capped at 1200 words so the "
                "table stays scannable. Move long-form detail into a "
                "docs/specs/ file and reference it from the abstract.\n"
                "UNBLOCK: Trim the abstract; keep the BDD Given/When/Then "
                "structure intact."
            )

        # Required-on-new field pre-check (2026-05-16). The model also
        # enforces; this surfaces the FAIL before the DB write attempt.
        risk = (opts.get("risk_on_inaction") or "").strip()
        acceptance = (opts.get("acceptance_criteria") or "").strip()
        missing_required: list[str] = []
        if not risk:
            missing_required.append("--risk-on-inaction")
        if not acceptance:
            missing_required.append("--acceptance-criteria")
        if missing_required:
            raise CommandError(
                "FAIL defer_work: missing required field(s): "
                + ", ".join(missing_required)
                + ".\n"
                "WHY: Every new paper-trail entry MUST tell the next agent "
                "(a) what breaks if this is ignored, and (b) what 'done' "
                "looks like. Without those, the entry is just an unscoped "
                "promise.\n"
                "UNBLOCK: Re-run with --risk-on-inaction \"<plain English>\" "
                "and --acceptance-criteria \"<bullet list or sentence>\"."
            )
        # BDD-format pre-check (the model also validates; this gives a
        # better error before the DB write attempt).
        lowered = abstract.lower()
        import re as _re
        missing_bdd = [
            kw.capitalize() for kw in ("given", "when", "then")
            if not _re.search(rf"\b{kw}\b", lowered)
        ]
        if missing_bdd:
            raise CommandError(
                f"FAIL defer_work: abstract is missing required BDD "
                f"section(s): {', '.join(missing_bdd)}.\n"
                "WHY: Every new paper-trail abstract MUST be in BDD style "
                "(`Given <context> When <action> Then <expected outcome>`) "
                "so the next agent can read the deferral as a self-contained "
                "acceptance spec.\n"
                "UNBLOCK: Rewrite the abstract using all three sections, "
                "for example:\n"
                "  Given the CVE scanner reports 18 known vulnerabilities "
                "in 8 packages, When the operator runs the dependency "
                "upgrade chain, Then every vulnerable package is bumped to "
                "the patched version and the backend test suite stays "
                "green at >68%% coverage."
            )

        # Paper Trail Evidence Rule (2026-05-17). Validate citations + the
        # linked test_case AutoIssue BEFORE the dedup check so an entry
        # with bad evidence never reaches the dedup index.
        test_case_id = opts.get("test_case_autoissue")
        citations_raw = [c.strip() for c in (opts.get("citations") or []) if c.strip()]
        if test_case_id is None:
            raise CommandError(
                "FAIL defer_work: --test-case-autoissue is required.\n"
                "WHY: every new paper-trail entry from 2026-05-17 onward "
                "MUST link to an AutoIssue(category='test_case') row whose "
                "lessons_learned carries the FULL 10-field BDD contract "
                "(Given + When + Then + edge_cases + failure_cases + "
                "security + usability + scalability + maintainability + "
                "regression_risks). Without that link the next agent has "
                "no spec for this deferred work.\n"
                "UNBLOCK: file the test case first via "
                "`docker compose exec -T backend python manage.py "
                "log_test_case --file <p> --title \"...\" "
                "--given \"...\" --when \"...\" --then \"...\" "
                "--edge-cases \"...\" --failure-cases \"...\" "
                "--security \"...\" --usability \"...\" "
                "--scalability \"...\" --maintainability \"...\" "
                "--regression-risks \"...\"` and pass the returned "
                "AutoIssue id to --test-case-autoissue."
            )
        if not citations_raw:
            raise CommandError(
                "FAIL defer_work: --citation is required (at least one).\n"
                "WHY: paper-trail entries must be grounded in evidence — "
                "patents, academic papers (DOI / arXiv), ISO/IEEE/IETF "
                "standards, RFCs, ISBN books, or URLs on the official-"
                "vendor allowlist. Free-prose abstracts without a stable "
                "identifier rot fast.\n"
                "UNBLOCK: pass one or more --citation <id> per "
                "docs/PAPER-TRAIL-EVIDENCE-RULE.md § \"Citation forms "
                "accepted\"."
            )
        bad_citations: list[tuple[str, str]] = []
        for c in citations_raw:
            ok, _kind = validate_citation(c)
            if not ok:
                bad_citations.append((c, "matched no accepted citation regex"))
        if bad_citations:
            bad_list = "\n".join(f"  - {raw}: {why}" for raw, why in bad_citations[:5])
            raise CommandError(
                "FAIL defer_work: one or more --citation value(s) did not "
                "match any accepted citation form.\n"
                f"{bad_list}\n"
                "WHY: the rule requires citations to be machine-validatable "
                "stable identifiers so the next agent can resolve them.\n"
                "UNBLOCK: rewrite each failing citation per "
                "docs/PAPER-TRAIL-EVIDENCE-RULE.md § \"Citation forms "
                "accepted\" (DOI / arXiv / patent / ISO-IEEE-IETF / RFC / "
                "ISBN / official-vendor URL)."
            )

        # Verify the linked test_case AutoIssue exists, is the right
        # category, and carries all 10 required BDD fields.
        from apps.auto_issues.models import AutoIssue  # local import to avoid cycle
        try:
            tc = AutoIssue.objects.select_related("category").get(pk=test_case_id)
        except AutoIssue.DoesNotExist as exc:
            raise CommandError(
                f"FAIL defer_work: --test-case-autoissue #{test_case_id} "
                f"does not exist.\n"
                f"WHY: the referenced AutoIssue must be a real test_case "
                f"row written via manage.py log_test_case.\n"
                f"UNBLOCK: file the test case first and pass the printed "
                f"#N to --test-case-autoissue."
            ) from exc
        cat_key = getattr(tc.category, "key", None) if tc.category else None
        if cat_key != "test_case":
            raise CommandError(
                f"FAIL defer_work: AutoIssue #{test_case_id} has category "
                f"{cat_key!r}, not 'test_case'.\n"
                f"WHY: only rows filed via manage.py log_test_case satisfy "
                f"the test-case requirement. Cross-category references "
                f"hide the wrong shape behind a real-looking ID.\n"
                f"UNBLOCK: file a fresh test case via "
                f"`manage.py log_test_case ...` and pass its #N."
            )
        missing_fields = validate_test_case_completeness(tc)
        if missing_fields:
            raise CommandError(
                f"FAIL defer_work: AutoIssue #{test_case_id} is in the "
                f"test_case category but is missing required BDD "
                f"section(s): {', '.join(missing_fields)}.\n"
                f"WHY: paper-trail entries require a FULL test case (all "
                f"10 fields: {', '.join(REQUIRED_BDD_FIELDS)}). Casual "
                f"test cases with only the BDD triple satisfy the Test "
                f"Case First rule for code mapping but NOT this rule for "
                f"paper-trail entries.\n"
                f"UNBLOCK: re-file the test case with the missing field(s) "
                f"populated:\n"
                f"  manage.py log_test_case ... "
                + " ".join(
                    f"--{name.lower().replace(' ', '-')} \"...\""
                    for name in missing_fields if name not in ("Given", "When", "Then")
                )
                + (" --given \"...\" --when \"...\" --then \"...\""
                   if any(f in missing_fields for f in ("Given", "When", "Then")) else "")
            )

        # C++ dedup check FIRST — if a near-duplicate exists, bump it.
        threshold = float(opts["similarity_threshold"])
        hits = dedup_service.find_similar(abstract, threshold=threshold)
        if hits:
            top_id, top_sim = hits[0]
            try:
                existing = PaperTrailEntry.objects.get(pk=top_id)
            except PaperTrailEntry.DoesNotExist:
                # Index drift — fall through to normal create.
                pass
            else:
                if existing.status in PaperTrailEntry._ACTIVE_STATUSES:
                    existing.occurrence_count += 1
                    existing.last_seen = timezone.now()
                    existing.history = [
                        *existing.history,
                        {
                            "at": timezone.now().isoformat(),
                            "by": opts["deferred_by"],
                            "action": "re_deferred",
                            "note": f"similarity={top_sim:.2f}",
                        },
                    ]
                    existing.save()
                    self.stdout.write(
                        f"[PAPER TRAIL DUPED: matched #{existing.pk} at "
                        f"similarity {top_sim:.2f}]"
                    )
                    return

        # Integrity check: search existing entries for stale rows that
        # mention the same affected_files or linked_autoissue so the
        # filing agent (and the next agent reading the entry) sees the
        # context up-front. Result is recorded on the entry itself.
        integrity_lines: list[str] = []
        if opts["linked_autoissue"] is not None:
            link_hits = PaperTrailEntry.objects.filter(
                linked_autoissue_id=opts["linked_autoissue"],
            ).exclude(status__in=PaperTrailEntry._TERMINAL_STATUSES).values_list("pk", flat=True)[:5]
            if link_hits:
                integrity_lines.append(
                    f"linked_autoissue overlap with #{list(link_hits)}"
                )
        if opts["affected_file"]:
            for f in opts["affected_file"]:
                file_hits = PaperTrailEntry.objects.filter(
                    affected_files__contains=[f],
                ).exclude(status__in=PaperTrailEntry._TERMINAL_STATUSES).values_list("pk", flat=True)[:3]
                if file_hits:
                    integrity_lines.append(
                        f"affected_file `{f}` overlap with #{list(file_hits)}"
                    )
        integrity_check_result = (
            " | ".join(integrity_lines)
            if integrity_lines
            else "no overlap found"
        )

        # Auto-bump evidence_level to 'cited' when citations are supplied
        # AND the agent did not explicitly request a different level. This
        # closes the "I have citations but evidence_level=low" loophole so
        # the entry's grouping classifier matches its underlying evidence.
        evidence_level = opts["evidence_level"]
        if citations_raw and evidence_level == PaperTrailEntry.EVIDENCE_LOW:
            evidence_level = PaperTrailEntry.EVIDENCE_CITED

        if opts.get("dry_run"):
            self.stdout.write(
                f"[PAPER TRAIL DRY-RUN: would file category={opts['category']} "
                f"title={opts['title'][:60]!r} test_case={test_case_id} "
                f"citations={len(citations_raw)} evidence_level={evidence_level}]"
            )
            return

        # No dupe — create a new entry.
        try:
            entry = PaperTrailEntry.objects.create(
                title=opts["title"][:512],
                category=opts["category"],
                abstract=abstract,
                deferred_by=opts["deferred_by"][:64],
                severity=opts["severity"],
                linked_autoissue_id=opts["linked_autoissue"],
                linked_registry_id=opts["linked_registry_id"][:24],
                deferred_in_handoff=opts["deferred_in_handoff"][:24],
                deferral_reason_key=opts["deferral_reason_key"][:32],
                next_actions=opts["next_action"],
                affected_files=opts["affected_file"],
                blockers=opts["blocker"],
                required_skills=opts["required_skill"],
                complexity_bucket=opts["complexity"],
                estimated_hours=opts["estimated_hours"],
                risk_on_inaction=risk,
                resolution_criteria=opts["resolution_criteria"],
                acceptance_criteria=acceptance,
                evidence_level=evidence_level,
                integrity_check_result=integrity_check_result,
                test_case_autoissue_id=test_case_id,
                citations=citations_raw,
            )
        except ValidationError as exc:
            raise CommandError(str(exc)) from exc

        # Compute priority and insert into the C++ dedup index.
        entry.priority_score = compute_priority_score(entry)
        entry.save(update_fields=["priority_score"])
        dedup_service.add_entry(entry.pk, abstract)

        # Handle --supersedes: mark old rows as superseded by this one.
        superseded_ids: list[int] = []
        for old_id in opts.get("supersedes", []) or []:
            try:
                old = PaperTrailEntry.objects.get(pk=old_id)
            except PaperTrailEntry.DoesNotExist:
                self.stdout.write(
                    f"[PAPER TRAIL SUPERSEDE WARN: #{old_id} not found, skipped]"
                )
                continue
            old.superseded_by = entry
            old.status = PaperTrailEntry.STATUS_SUPERSEDED
            old.save()
            superseded_ids.append(old.pk)

        if superseded_ids:
            self.stdout.write(
                f"[PAPER TRAIL SUPERSEDED: #{entry.pk} now replaces "
                f"{', '.join(f'#{i}' for i in superseded_ids)}]"
            )
        if integrity_lines:
            self.stdout.write(
                f"[PAPER TRAIL INTEGRITY: {integrity_check_result}]"
            )
        self.stdout.write(f"[PAPER TRAIL FILED: #{entry.pk}]")
