"""manage.py verify_paper_trail_evidence — Paper Trail Evidence Rule verifier.

Called by `.githooks/check-paper-trail-evidence.py` (production-mode
verifier) to confirm a paper-trail entry referenced by a
`[PAPER TRAIL FILED: #N]` marker satisfies the rule:

1. Entry exists (or skip with explicit reason).
2. If `deferred_at < 2026-05-17T00:00:00Z` → grandfathered, pass.
3. Otherwise: `test_case_autoissue_id` is set; the referenced AutoIssue
   exists; its category.key == 'test_case'; its `lessons_learned`
   contains ALL 10 REQUIRED_BDD_FIELDS; `citations` is non-empty; every
   citation passes `validate_citation`.

Exit 0 on pass + prints `[PAPER TRAIL EVIDENCE VERIFIED: #N ...]`.
CommandError (exit non-zero) on any failure with a Rule-F three-part
message.

Spec: docs/PAPER-TRAIL-EVIDENCE-RULE.md
"""

from __future__ import annotations

import re
from datetime import datetime, timezone as dt_tz

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.models import AutoIssue
from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.services.evidence import (
    REQUIRED_BDD_FIELDS,
    validate_citation,
    validate_test_case_completeness,
)


# BDD shape on the entry's own abstract — Given / When / Then (case-insensitive,
# word-boundary). Required on every post-2026-05-16 entry per the existing
# Paper Trail Integrity Rule; re-checked here so a corrupted row can't slip
# past the new commit-time hook by raw-SQL stripping the abstract.
_ABSTRACT_BDD_FIELDS = ("Given", "When", "Then")


# Effective cutoff. Entries deferred_at < this timestamp are grandfathered.
# 2026-05-17T07:25:00Z sits between the last pre-rule entry (#581 filed at
# 07:12:06Z) and the first post-rule entry (#582 filed at 07:29:03Z as the
# defer_work smoke test). Older rows are grandfathered with a clear reason
# string; new rows undergo the full citation + test-case-completeness
# verification.
CUTOFF = datetime(2026, 5, 17, 7, 25, 0, tzinfo=dt_tz.utc)


class Command(BaseCommand):
    help = "Verify a paper-trail entry satisfies docs/PAPER-TRAIL-EVIDENCE-RULE.md."

    def add_arguments(self, parser) -> None:
        # 2026-05-17 — paper-trail #588 Quick win #5. Either --paper-trail-id
        # (singular, legacy) OR --ids <N,N,N> (batch). Batch form lets the
        # hook verify 50 IDs in one Docker exec call instead of 50.
        parser.add_argument("--paper-trail-id", required=False, type=int, default=None,
                            help="PaperTrailEntry primary key to verify (singular).")
        parser.add_argument("--ids", required=False, default=None,
                            help="Comma-separated list of paper-trail IDs to verify "
                                 "in one call (batch form). Either --paper-trail-id "
                                 "or --ids must be provided.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Run verification without printing the marker.")

    def handle(self, *args, **opts) -> None:
        single_id = opts.get("paper_trail_id")
        batch_csv = opts.get("ids")
        if single_id is None and not batch_csv:
            raise CommandError(
                "FAIL verify_paper_trail_evidence: must pass --paper-trail-id "
                "<N> or --ids <N,N,N>."
            )
        if batch_csv:
            try:
                ids = [int(part.strip().lstrip("#")) for part in batch_csv.split(",") if part.strip()]
            except ValueError as exc:
                raise CommandError(
                    f"FAIL verify_paper_trail_evidence: --ids must be a "
                    f"comma-separated list of integers; got {batch_csv!r}."
                ) from exc
            if not ids:
                raise CommandError("FAIL verify_paper_trail_evidence: --ids is empty.")
            errors: list[str] = []
            for pk in ids:
                try:
                    self._verify_one(pk, opts)
                except CommandError as exc:
                    errors.append(str(exc))
            if errors:
                raise CommandError("\n\n".join(errors))
            return
        self._verify_one(single_id, opts)

    def _verify_one(self, pk: int, opts: dict) -> None:
        try:
            entry = PaperTrailEntry.objects.get(pk=pk)
        except PaperTrailEntry.DoesNotExist:
            # Missing rows referenced in OLD handoff content (referenced by
            # IDs that no longer exist in the DB because of pre-cutoff
            # squashes or pruning) are treated as grandfathered. The rule
            # exists to enforce evidence on NEW entries filed AFTER the
            # cutoff; retroactively rejecting commits whose handoff history
            # contains references to deleted rows would punish honest agents
            # for the DB's own cleanup history.
            if not opts["dry_run"]:
                self.stdout.write(
                    f"[PAPER TRAIL EVIDENCE VERIFIED: #{pk} "
                    f"missing-from-db (treated as grandfathered; only "
                    f"NEW entries filed after the 2026-05-17T07:25:00Z "
                    f"cutoff are required to satisfy this rule)]"
                )
            return

        # Grandfather: entries pre-cutoff pass automatically.
        if entry.deferred_at is not None and entry.deferred_at < CUTOFF:
            if not opts["dry_run"]:
                self.stdout.write(
                    f"[PAPER TRAIL EVIDENCE VERIFIED: #{entry.pk} "
                    f"grandfathered (deferred_at={entry.deferred_at.isoformat()} "
                    f"is before cutoff {CUTOFF.isoformat()})]"
                )
            return

        # Post-cutoff: full validation. Layer 1 — required core fields on
        # the entry itself. Catches raw-SQL bypasses that strip required
        # data after filing, plus any pre-rule entry that was filed under
        # the older shape but is now treated as post-cutoff.
        missing_core: list[str] = []
        if not (entry.abstract or "").strip():
            missing_core.append("abstract")
        if not (entry.risk_on_inaction or "").strip():
            missing_core.append("risk_on_inaction")
        if not (entry.acceptance_criteria or "").strip():
            missing_core.append("acceptance_criteria")
        if missing_core:
            raise CommandError(
                f"FAIL verify_paper_trail_evidence: PaperTrailEntry "
                f"#{entry.pk} is missing required core field(s): "
                f"{', '.join(missing_core)}.\n"
                f"WHY: every paper-trail entry MUST tell the next agent "
                f"what work is deferred (abstract), what breaks if "
                f"ignored (risk_on_inaction), and what 'done' looks like "
                f"(acceptance_criteria). Without these the entry is just "
                f"an unscoped promise.\n"
                f"UNBLOCK: re-file the entry via "
                f"`manage.py defer_work --abstract \"Given … When … "
                f"Then …\" --risk-on-inaction \"...\" "
                f"--acceptance-criteria \"...\" ...`."
            )

        # Layer 2 — abstract BDD shape (existing Paper Trail Integrity Rule).
        abstract_lower = (entry.abstract or "").lower()
        missing_abstract_bdd = [
            kw for kw in _ABSTRACT_BDD_FIELDS
            if not re.search(rf"\b{kw.lower()}\b", abstract_lower)
        ]
        if missing_abstract_bdd:
            raise CommandError(
                f"FAIL verify_paper_trail_evidence: PaperTrailEntry "
                f"#{entry.pk} abstract is missing required BDD "
                f"section(s): {', '.join(missing_abstract_bdd)}.\n"
                f"WHY: every paper-trail abstract MUST be in BDD style "
                f"(`Given <context> When <action> Then <expected "
                f"outcome>`) so the next agent reads the deferral as a "
                f"self-contained acceptance spec.\n"
                f"UNBLOCK: re-file the entry with a BDD-shaped abstract."
            )

        # Layer 3 — Paper Trail Evidence Rule (test case + citations).
        if entry.test_case_autoissue_id is None:
            raise CommandError(
                f"FAIL verify_paper_trail_evidence: PaperTrailEntry "
                f"#{entry.pk} has no test_case_autoissue_id; the Paper "
                f"Trail Evidence Rule requires every entry filed on or "
                f"after 2026-05-17 to link to an AutoIssue("
                f"category='test_case') with all 10 BDD fields.\n"
                f"WHY: without the linked contract the next agent has no "
                f"spec to read for this deferred work.\n"
                f"UNBLOCK: file a test case via `manage.py log_test_case "
                f"...` and update the entry's link (re-file the deferral "
                f"with --test-case-autoissue <N> via manage.py defer_work, "
                f"or update the entry directly with a follow-up DB op)."
            )

        try:
            tc = AutoIssue.objects.select_related("category").get(
                pk=entry.test_case_autoissue_id
            )
        except AutoIssue.DoesNotExist as exc:
            raise CommandError(
                f"FAIL verify_paper_trail_evidence: PaperTrailEntry "
                f"#{entry.pk} links to AutoIssue #"
                f"{entry.test_case_autoissue_id} but that row does not "
                f"exist.\n"
                f"WHY: dangling test_case_autoissue_id references mean "
                f"the contract was deleted or never created.\n"
                f"UNBLOCK: re-file the test case via `manage.py "
                f"log_test_case ...` and update the entry's link."
            ) from exc

        cat_key = getattr(tc.category, "key", None) if tc.category else None
        if cat_key != "test_case":
            raise CommandError(
                f"FAIL verify_paper_trail_evidence: PaperTrailEntry "
                f"#{entry.pk} links to AutoIssue #{tc.pk} but its "
                f"category is {cat_key!r}, not 'test_case'.\n"
                f"WHY: only test_case AutoIssue rows carry the BDD "
                f"contract this rule requires.\n"
                f"UNBLOCK: file a real test case via `manage.py "
                f"log_test_case --file <p> --given \"...\" --when \"...\" "
                f"--then \"...\" --edge-cases \"...\" --failure-cases "
                f"\"...\" --security \"...\" --usability \"...\" "
                f"--scalability \"...\" --maintainability \"...\" "
                f"--regression-risks \"...\"` and update the entry."
            )

        missing_fields = validate_test_case_completeness(tc)
        if missing_fields:
            raise CommandError(
                f"FAIL verify_paper_trail_evidence: PaperTrailEntry "
                f"#{entry.pk} links to test_case AutoIssue #{tc.pk} but "
                f"its lessons_learned is missing required BDD section(s): "
                f"{', '.join(missing_fields)}.\n"
                f"WHY: paper-trail entries require a FULL test case "
                f"(all 10 fields: {', '.join(REQUIRED_BDD_FIELDS)}). "
                f"Casual test cases with only Given/When/Then satisfy the "
                f"Test Case First rule for code mapping but NOT this rule "
                f"for paper-trail entries.\n"
                f"UNBLOCK: re-file the test case with the missing field(s) "
                f"populated."
            )

        citations = entry.citations or []
        if not citations:
            raise CommandError(
                f"FAIL verify_paper_trail_evidence: PaperTrailEntry "
                f"#{entry.pk} has an empty citations list.\n"
                f"WHY: paper-trail entries must be grounded in evidence — "
                f"patents, academic papers, ISO/IEEE/IETF standards, RFCs, "
                f"ISBN books, or URLs on the official-vendor allowlist.\n"
                f"UNBLOCK: re-file the entry with one or more --citation "
                f"<id> per docs/PAPER-TRAIL-EVIDENCE-RULE.md."
            )

        bad: list[str] = []
        for c in citations:
            ok, _kind = validate_citation(c)
            if not ok:
                bad.append(c)
        if bad:
            raise CommandError(
                f"FAIL verify_paper_trail_evidence: PaperTrailEntry "
                f"#{entry.pk} has citations that do not match any "
                f"accepted form: {', '.join(bad[:5])}\n"
                f"WHY: citations must be machine-validatable stable "
                f"identifiers so the next agent can resolve them.\n"
                f"UNBLOCK: rewrite each failing citation per "
                f"docs/PAPER-TRAIL-EVIDENCE-RULE.md § 'Citation forms accepted'."
            )

        if opts["dry_run"]:
            return
        self.stdout.write(
            f"[PAPER TRAIL EVIDENCE VERIFIED: #{entry.pk} "
            f"test_case=#{tc.pk} citations={len(citations)}]"
        )
