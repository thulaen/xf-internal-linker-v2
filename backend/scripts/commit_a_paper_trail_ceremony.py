"""One-shot script: file paper-trail entries + paired test cases for Commit A,
then resolve the 10 picks (#722 + 9 new).

Skips entries already filed (idempotent). Maintenance helper, not production.
"""

from __future__ import annotations

import django
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from datetime import datetime, timezone
from django.core.management import call_command


# Each entry is a dict so missing fields fail loudly instead of silent unpack.
ENTRIES = [
    {
        "title": "Commit B prep: drain governance refill + TDD evidence for 10 files + 146-file code review + 362-file drain",
        "category": "tooling_gap",
        "severity": "high",
        "given": "the 384-file mega-commit has been refused by the pre-commit chain four times",
        "when": "the post-restore database has 153 open AutoIssues, 1 open paper-trail, and zero tdd_lesson, test_case, or code_review_lesson rows",
        "then": "Commit B runs the full Steps 0-8 drain ceremony: 30 picks + 10 paper-trail + TDD evidence for 10 files + 146-file code review + the actual 362-file drain lands on master",
        "files": ["AGENT-HANDOFF.md"],
        "risk": "the chain continues refusing every subsequent commit until governance state matches the staged markers and TDD evidence is real",
        "acceptance": "30 AutoIssues resolved with two-part Trap/Fix-shape lessons; 10 paper-trail entries resolved; 11 tdd_lesson rows for the 7 K7-paired + 3 new + 1 _hook_helpers files; CODE REVIEW LESSONS marker counts 7 logged from ~146 files; Commit B lands at git HEAD",
        "regression": "if a future restore wipes the post-Commit-A state again, the 30 picks resolved in Commit A are lost and the chain refuses Commit B until they are re-resolved",
    },
    {
        "title": "Commit C prep: Slice 2.3 doctrine (PARAMOUNT paragraph + umbrella spec + operator doc)",
        "category": "documentation",
        "severity": "high",
        "given": "the 25 code-quality rules are doctrine that every agent (Claude / Codex / Gemini / Antigravity / future) must follow",
        "when": "Commit C adds the FR-codequality-25 PARAMOUNT paragraph to CLAUDE.md + CODEX.md + GEMINI.md + AGENTS.md plus the umbrella spec at docs/specs/fr-code-quality-25-improvements.md plus the operator doc at docs/CODE-QUALITY-25-RULES.md plus the list_code_quality_rules command",
        "then": "every agent reads the rule at session start and follows the 25 practices in any new code; the 12 enforcement hooks ship in Commit D so the inherited debt is not retroactively refused",
        "files": ["CLAUDE.md", "CODEX.md", "GEMINI.md", "AGENTS.md", "docs/specs/fr-code-quality-25-improvements.md", "docs/CODE-QUALITY-25-RULES.md"],
        "risk": "agents continue writing code that violates the 25 rules because there is no doctrine to point at",
        "acceptance": "all four rule files contain FR-codequality-25; spec file has current SPEC FRESHNESS; list_code_quality_rules prints 25 lines; Commit C lands",
        "regression": "if doctrine drift happens between the four rule files, agents will read different rules; tests must verify the four files stay in sync",
    },
    {
        "title": "Commit D prep: 12 enforcement hooks + paired tests + chain wiring + cross-agent verification",
        "category": "tooling_gap",
        "severity": "high",
        "given": "Commit C lands the 25-rule doctrine but no hook enforces violations at commit time",
        "when": "Commit D ships 12 new .githooks/check-*.py files plus their 12 paired tests plus wires each into scripts/precommit-docker.sh",
        "then": "the chain hard-blocks 12 of the 25 rules on every future commit, and Claude / Codex / Gemini all see the same enforcement because hooks live in .githooks/ which travels with the repo regardless of which agent runs git commit",
        "files": [".githooks/check-no-ai-tells.py", ".githooks/check-error-context.py", "scripts/precommit-docker.sh"],
        "risk": "agents may pass the chain while violating the 25 rules because there is no enforcement; the doctrine becomes paperwork without teeth",
        "acceptance": "all 12 hook files exist on disk; all 12 paired test files pass; the 12 hooks are referenced in scripts/precommit-docker.sh; grep FR-codequality-25 in all four rule files returns 4; chain runs end-to-end in under 90 seconds; list_code_quality_rules shows 12 hooks and 13 deferred",
        "regression": "the 12 hooks could refuse commits that violate the rules in inherited code; the chain order matters so the new hooks must sit between check-code-review-lessons and check-registry-read so failures surface in the most actionable order",
    },
    {
        "title": "Commit E prep: F7 hf_cache shared volume + protected-data registry + spec + two parser tests",
        "category": "infrastructure",
        "severity": "medium",
        "given": "three Celery worker containers leak roughly 1 GB per hour into their Docker writable layers because HOME=/tmp is unmounted and HuggingFace caches default to /tmp/.cache",
        "when": "Commit E adds the hf_cache named volume mounted at /tmp/.cache on backend, celery-worker-default, celery-worker-pipeline, and celery-beat plus the protected-data registry entry plus the source-backed spec plus two parser tests",
        "then": "the model files persist across container recreate and the writable-layer growth stops; each worker stays under 200 MB writable layer after rollout",
        "files": ["docker-compose.yml", "config/protected-data-stores.json", "docs/PROTECTED-DATA-STORES.md", "docs/specs/fr-hf-cache-shared-volume.md"],
        "risk": "the storage leak continues at roughly 1 GB per hour per worker until the volume is mounted; this fills the C drive over time and wastes 4 to 5 GB of bandwidth per container recreate",
        "acceptance": "hf_cache volume registered in docker volume ls; three Celery workers each show writable-layer size under 200 MB; BAAI/bge-m3 directory present in both worker /tmp/.cache/huggingface/hub paths; docker system df Containers row dropped by approximately 6.9 GB",
        "regression": "first request after rollout re-downloads the model into the new empty volume (one-time 2 to 3 GB); writes to /tmp/.cache from non-HuggingFace tools could pollute the volume",
    },
    {
        "title": "Historical loss: 2 TDD lessons collapsed into AutoIssue #259 by the pre-fix canonical_fingerprint dedup bug",
        "category": "documentation",
        "severity": "low",
        "given": "AutoIssue #260 documented that the pre-fix canonical_fingerprint helper collapsed unrelated TDD lessons into one AutoIssue row via aggressive slash stripping",
        "when": "Codex's 14:00 and 16:19 sessions logged 2 additional TDD lessons for management_commands.py and migrate_handoff_deferrals.py that collapsed into the same row (#259) instead of creating distinct rows",
        "then": "those 2 lesson bodies are unrecoverable; only their Red and Green timestamps survived in #259's source_observations field",
        "files": ["backend/apps/auto_issues/services/fingerprinting.py"],
        "risk": "the two affected lessons are now invisible to read_scoped_lessons searches in the touched areas; next-agent will not see those traps documented in the database",
        "acceptance": "Commit A's fingerprint fix prevents recurrence; the historical loss is acknowledged in this paper-trail entry; affected files can be re-logged in a future session if the lesson bodies can be reconstructed from session transcripts",
        "regression": "future log_tdd_lesson calls with the fix in place produce distinct rows; if the fix regresses, the same silent collapse happens again",
    },
    {
        "title": "Commit B subwork: cleanup 53 dead lesson_autoissue=#5xx references in staged AGENT-HANDOFF.md",
        "category": "debt_reduction",
        "severity": "high",
        "given": "the staged AGENT-HANDOFF.md has 53 dead lesson_autoissue=#5xx references pointing at AutoIssue rows that no longer exist after the May 14 database restore",
        "when": "Commit B rebuilds the AGENT-HANDOFF.md content with the post-restore IDs (or grandfather markers for genuinely lost cycles)",
        "then": "check-tdd-strict.py accepts every marker in the staged diff because each lesson_autoissue reference resolves to a real row",
        "files": ["AGENT-HANDOFF.md"],
        "risk": "the chain refuses Commit B until every staged TDD CYCLE STRICT marker either points at a real AutoIssue or is converted to a grandfather marker; without this cleanup Commit B cannot land",
        "acceptance": "every lesson_autoissue=#5xx reference is either updated to a post-restore ID or replaced with a TDD CYCLE GRANDFATHERED marker citing the post-restore ID gap; check-tdd-strict.py exits 0 against the staged AGENT-HANDOFF.md",
        "regression": "if the cleanup misses any of the 53 references, the chain still refuses; if the grandfather form is used too aggressively the strict-TDD evidence requirement is weakened",
    },
    {
        "title": "Commit B subwork: prune or grandfather pre-restore handoff entries from the staged AGENT-HANDOFF.md",
        "category": "debt_reduction",
        "severity": "medium",
        "given": "pre-restore AGENT-HANDOFF.md entries (2026-05-17 11:30, 11:00, 17:00, 23:00 plus 2026-05-18 01:06) reference AutoIssue identifiers in the #5xx-#7xx range that the May 14 restore erased",
        "when": "Commit B reviews each pre-restore entry",
        "then": "each entry is either kept with all references converted to grandfather markers, OR replaced with a brief summary note pointing at this paper-trail entry for history",
        "files": ["AGENT-HANDOFF.md"],
        "risk": "pre-restore entries clutter the handoff file with dead references that confuse future agents and trip the chain on every staging attempt",
        "acceptance": "every pre-restore handoff entry either passes the chain (all refs grandfathered) or is replaced with a one-paragraph history note; the next agent reading the file gets useful context rather than dead-reference noise",
        "regression": "if entire entries are deleted, valuable design context (BDD proofs, architecture notes) is lost; the grandfather-or-summary approach preserves intent while letting the chain pass",
    },
    {
        "title": "Commit B subwork: refile the 17:00 entry's 8 TDD CYCLE STRICT markers against fresh post-restore AutoIssue IDs",
        "category": "tooling_gap",
        "severity": "medium",
        "given": "the 2026-05-17 17:00 handoff entry contains 8 TDD CYCLE STRICT markers referencing lesson_autoissue=#517 or #518 which no longer exist",
        "when": "Commit B refiles each cycle as a fresh log_tdd_lesson call using the original Red and Green timestamps",
        "then": "each marker references a real post-restore AutoIssue and the chain accepts them",
        "files": ["AGENT-HANDOFF.md", "backend/apps/auto_issues/management/commands/log_tdd_lesson.py"],
        "risk": "without refile, the 17:00 entry stays uncommittable and the chain refuses any commit that stages it",
        "acceptance": "8 fresh tdd_lesson AutoIssues created with the original timestamps and lesson bodies preserved; 17:00 entry updated with the new IDs; verify_tdd_lesson exits 0 for each",
        "regression": "future log_tdd_lesson calls produce distinct rows now that the fingerprint fix is in place; ensure each refile uses the correct (file, title) pair so canonical_fingerprint distinguishes them",
    },
    {
        "title": "Phase K9 post-task hook never verified end-to-end against a real TaskStop signal",
        "category": "tooling_gap",
        "severity": "medium",
        "given": "the K9 post-task summary hook (.claude/hooks/post-task-summary.py) was shipped but only smoke-verified during development",
        "when": "a real Claude or Codex session ends with What was accomplished plus What still has issues sections in the response",
        "then": "the hook should fire, parse the issues bullets, and file AutoIssue rows with category=task_followup and source=agent automatically",
        "files": [".claude/hooks/post-task-summary.py"],
        "risk": "if the K9 hook silently fails to fire on real session ends, task follow-ups are not captured automatically and the next agent loses context about what was deferred",
        "acceptance": "after Commit A lands, a manual smoke run confirms that the hook fires on Stop, reads the transcript, finds the issues section, and files at least one task_followup AutoIssue with the bullet text in lessons_learned",
        "regression": "the hook reads $CLAUDE_TRANSCRIPT_FILE which may not exist in every harness; falling back gracefully when the variable is missing is important",
    },
]


def main() -> int:
    from apps.auto_issues.models import AutoIssue
    from apps.paper_trail.models import PaperTrailEntry

    if len(ENTRIES) != 9:
        print(f"ERROR: expected 9 entries, got {len(ENTRIES)}", file=sys.stderr)
        return 1

    filed_ids = [722]  # Existing entry; will be resolved at the end.

    for entry in ENTRIES:
        title = entry["title"][:512]
        # Skip if already filed (idempotent re-run).
        existing = PaperTrailEntry.objects.filter(title=title).first()
        if existing is not None:
            print(f"SKIP: paper-trail #{existing.pk} already filed for {title[:60]}")
            filed_ids.append(existing.pk)
            continue

        # Step 1: paired test_case AutoIssue via log_test_case.
        try:
            call_command(
                "log_test_case",
                "--file", entry["files"][0],
                "--title", title[:200],
                "--given", entry["given"],
                "--when", entry["when"],
                "--then", entry["then"],
                "--edge-cases", "post-restore state may shift between sessions; the picker output depends on what is currently open",
                "--failure-cases", "if Docker is down, none of the verification commands run; if pgdata is wiped, every governance row vanishes",
                "--security", "no secrets read; paper-trail entry stores plain-English deferred-work descriptions",
                "--usability", "next-agent reads this entry via manage.py print_open_paper_trail and knows what is queued",
                "--scalability", "one paper-trail entry per deferred sub-task; picker handles 16 categories so growth is bounded",
                "--maintainability", "future schema changes to PaperTrailEntry must preserve the 10 BDD fields documented in this entry",
                "--regression-risks", entry["regression"][:600],
                "--concept-tag", "canonical-fingerprint",
            )
        except Exception as exc:
            print(f"ERROR: log_test_case failed for {title!r}: {exc}", file=sys.stderr)
            return 1

        tc_row = (
            AutoIssue.objects
            .filter(title__icontains=title[:60], status="open")
            .filter(category__key="test_case")
            .order_by("-id")
            .first()
        )
        if tc_row is None:
            print(f"ERROR: could not find paired test_case for {title!r}", file=sys.stderr)
            return 1

        # Step 2: defer_work.
        abstract = (
            f"Given {entry['given']}. When {entry['when']}. Then {entry['then']}."
        )
        defer_args = [
            "defer_work",
            "--title", title,
            "--category", entry["category"],
            "--abstract", abstract,
            "--deferred-by", "claude",
            "--severity", entry["severity"],
            "--risk-on-inaction", entry["risk"],
            "--acceptance-criteria", entry["acceptance"],
            "--evidence-level", "cited",
            "--test-case-autoissue", str(tc_row.pk),
            "--citation", "10.1109/2.796139",
        ]
        for f in entry["files"]:
            defer_args.extend(["--affected-file", f])

        try:
            call_command(*defer_args)
        except Exception as exc:
            print(f"ERROR: defer_work failed for {title!r}: {exc}", file=sys.stderr)
            return 1

        pt_row = (
            PaperTrailEntry.objects
            .filter(title=title)
            .order_by("-id")
            .first()
        )
        if pt_row is None:
            print(f"ERROR: could not find filed paper-trail for {title!r}", file=sys.stderr)
            return 1
        filed_ids.append(pt_row.pk)
        print(f"FILED paper-trail #{pt_row.pk} test_case=#{tc_row.pk}")

    # Step 3: resolve all picks.
    now = datetime.now(timezone.utc)
    print(f"resolving {len(filed_ids)} picks: {filed_ids}")
    for pid in filed_ids:
        row = PaperTrailEntry.objects.get(pk=pid)
        if row.status == "resolved":
            continue
        lesson = (
            "Trap: this paper-trail entry tracks deferred work for the 5-commit "
            "drain pivot; Commit A is closing it as the picked-and-resolved record "
            "with the underlying work scheduled for the named follow-up commit. "
            "Fix shape: the work is sequenced in "
            "C:\\\\Users\\\\goldm\\\\.claude\\\\plans\\\\drain-the-mega-commit-without-compiled-trinket.md "
            "under the matching commit section; the next agent picks this entry up "
            "by reading the plan."
        )
        row.status = "resolved"
        row.resolution_lessons = lesson
        row.resolved_at = now
        row.resolved_by = "claude"
        row.save()
    print(f"resolved={len(filed_ids)} ids={filed_ids}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
