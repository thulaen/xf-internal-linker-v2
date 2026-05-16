# Claude Instructions

**ABSOLUTE — Self-Written Code Quality Gate:** Any code an agent writes must be fixed until it meets the coding guidelines, coverage target, mutation-test rule, and required test commands. If a required check cannot run, fix the check environment or command until it runs. Do not ask the user whether to fix code you wrote. Do not commit code with failing tests, unmet coverage, skipped mutation tests, missing tools, broken containers, or known guideline violations. If the machine itself cannot support the check after repair attempts, stop before committing and leave a clear status note. Do not commit. After `[GUIDELINES READ: ...]`, emit `[QUALITY GATE READ: self-written code must pass guidelines, tests, coverage, mutation tests, and required check setup before commit]`. Every code-changing handoff must include `[QUALITY GATE RESULT: guidelines=passed tests=passed coverage=met mutation=passed check_setup=passed]`.

**PARAMOUNT — Plain-English Communication Rule (all agents — Claude / Codex / Gemini / Antigravity / every future agent):** Read [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md) before composing any response — it contains the full glossary and the mandatory Before-You-Send checklist. Every response, commit message, error report, status update, and user-facing surface MUST be written in plain English the user can understand. The user is a vibe coder — they use AI exclusively and don't write code. Three required parts:
1. **What I'm doing / will do** — describe the action in everyday words. Define every technical term the moment it's used. No unexplained acronyms (FR-XXX, ISS-XXX, RPT-XXX, MMR, BGE-M3, FAISS, RSQVA, etc.) — use the plain-English substitutes from the glossary in [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md).
2. **What was accomplished** — at the end of every change, state in plain English what now works that didn't before, plus which files changed and why.
3. **What has issues or errors** — surface failures honestly. If something broke, say what broke, why, and what you'll do about it. Never bury errors in jargon. Never silently move on after a failure. Never claim success when something is partial. If a step was skipped, say so.
The rule applies to chat output, commit messages, PR descriptions, REPORT-REGISTRY entries, AGENT-HANDOFF entries, and any other surface a human reads. Skipping any of the three required parts is a protocol violation. Silence on errors is forbidden.
**Before sending any response, run the Before-You-Send checklist in [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md). If any of the four checklist questions is NO, rewrite the response before sending.**

**PARAMOUNT — THINK BEFORE YOU CODE (the upstream rule):** STOP and answer the 5 pre-write questions BEFORE typing any new function/class/view/service. (1) DRY — search the codebase first; reuse or refactor BOTH sites if a near-duplicate exists. (2) KISS — write the simplest thing that works; no premature abstraction. (3) Scaling — declare what happens at 10× and 100× input. (4) Extensibility — declare WHERE the next feature lands BEFORE shipping the first version. (5) Testability — pure functions + small classes that test in `SimpleTestCase` without Docker. Hard limits: ≤50 lines per function, ≤1500 per file, ≤10 cyclomatic complexity, ≤7 args, ≤4 nesting levels, no duplicated 6+ line blocks. **Leave every file in BETTER shape than you found it.** Read [`THINK-BEFORE-YOU-CODE.md`](THINK-BEFORE-YOU-CODE.md) before writing a single line — this is the upstream rule that prevents the messes the other paramount files clean up after.

**PARAMOUNT — Branch transparency: Never create, switch to, or push a new branch without telling the user in plain English first. Work done on a branch does not appear on `master` until merged. If the user did not ask for a branch, stay on `master`. Silence is forbidden.**
**PARAMOUNT — Strict no-duplicates rule: No persistent storage may pile up duplicate artefacts. Every per-content table follows the `(content_hash, signal_version)` skip-if-unchanged + supersede + retention pattern. Read [`NO-DUPLICATES.md`](NO-DUPLICATES.md) before adding any new artefact table.**
**PARAMOUNT — C++ first for hot paths: C++ extensions are the first-choice compute path. Python is fallback and reference only. Read [`CPP-FIRST.md`](CPP-FIRST.md) before adding or modifying any hot-path function.**
**PARAMOUNT — Docker-managed compiled languages: Read [`COMPILED-LANGUAGE-RULES.md`](COMPILED-LANGUAGE-RULES.md). Compiled-language builds, checks, runtime artifacts, coverage, mutation tests, and fuzz tests must use the Docker-managed path. Do not require host compilers and do not commit generated build output.**
**PARAMOUNT — Shared-library first: before creating any custom library, helper, wrapper, or hot-path module, search for existing shared code and reuse it. New compiled custom libraries must be dynamic libraries built through the Docker-managed artifact path unless a written exception is recorded in the standards marker and handoff entry.**
**ABSOLUTE — Claude/Codex BDD and TDD workflow:** In this repo, "agents" means Claude and Codex for this rule. Claude and Codex must use BDD, which means behavior-driven description, when talking to the user. Plans and behavior summaries use `Given / When / Then`. Claude and Codex must use TDD, which means test-driven development, when writing code. Before tests or code, read open AutoIssues and resolved lessons for the touched area. Then write or update a focused test before or alongside the code, run it, fix the code, and rerun until it passes. Code-changing handoffs must include `[BDD PROOF: Given ... When ... Then ...]`, `[TDD PROOF: before_or_alongside=yes tests=<commands> result=passed]`, and `[RESOLVED HISTORY: ...]` or `[AUTOISSUE LESSONS READ: ...]`. Temporary failing tests, generated fixtures, coverage files, mutation reports, and profile dumps must stay in ignored disposable paths. If a temporary test proves a real behavior rule, convert it into a small permanent regression test. The pre-commit hook blocks code commits when this proof is missing.
**ABSOLUTE — Standards opening and scoped self-review: before writing code, emit `[STANDARDS READY: ...]` with the coverage target, test commands, mutation and benchmark needs, reuse result, shared-library decision, and 10x / 100x scaling result. Before any summary, review only the task scope using real evidence from the diff, touched files, direct call sites, tests, and tool output. Do not invent findings or turn the review into a broad audit. Log every real bad practice found with `manage.py log_self_review_issue`, fix in-scope issues without behaviour change, state when nothing needed fixing, and emit `[SELF REVIEW RESULT: ...]`.**
**ABSOLUTE — Future-ready testing tools: new code is not complete unless the Docker-managed test, coverage, lint, mutation/fuzz, and benchmark tools can discover and check it. If a task adds a new language, folder, framework, runtime path, or build target, update the tool wiring in the same change. Host-only tools are forbidden.**
**PARAMOUNT — Hardware-aware defaults: Never hardcode batch sizes, parallelism, or FAISS configuration. Use `apps/pipeline/services/hardware_profile.py` so settings auto-scale per tier. Read [`HARDWARE-PROFILES.md`](HARDWARE-PROFILES.md).**
**PARAMOUNT — Disk-pressure circuit breaker: Pre-flight large writes via `apps/pipeline/services/disk_pressure.require_free_disk()`. Read [`DISK-PRESSURE-RULES.md`](DISK-PRESSURE-RULES.md).**
**PARAMOUNT — Deep-linking catalog: Every new route, tab, dialog, filter, or named scroll target MUST register itself in `frontend/src/app/core/routing/deep-link-catalog.ts` in the same commit. Read [`DEEP-LINKING-CATALOG.md`](DEEP-LINKING-CATALOG.md).**
**PARAMOUNT — Plain-English helpers: Every technical UI element MUST have a `peHelper` (or matTooltip) plain-English hover sourced from spec frontmatter. Read [`PLAIN-ENGLISH-HELPER-RULE.md`](PLAIN-ENGLISH-HELPER-RULE.md).**
**PARAMOUNT — Citations on every default: Every feature / setting / signal / meta / C++ optimisation / default value MUST have ≥1 specific citation (DOI / patent / RFC / stable URL) in `docs/specs/<id>.md`. Read [`CITATION-RULE.md`](CITATION-RULE.md).**
**PARAMOUNT — Tech-debt reduction is mandatory each session: every session must resolve ≥5 debt items AND include a "Tech-debt delta" line in the AGENT-HANDOFF entry. Read [`TECH-DEBT-MANDATE.md`](TECH-DEBT-MANDATE.md).**
**PARAMOUNT — Performance-safe defaults forbidden patterns: no unbounded loops, no unbounded table growth, no duplicate artefacts, no Python-only hot paths without justification. Read [`PERFORMANCE-SAFE-DEFAULTS.md`](PERFORMANCE-SAFE-DEFAULTS.md).**
**PARAMOUNT — Glossary update rule: every time a new technical thing is introduced (feature, signal, setting, acronym FR-XXX / RPT-XXX / ISS-XXX, framework name, abbreviation), the plain-English glossary in `PLAIN-ENGLISH-RULE.md` MUST be updated in the same change with a one-line plain-English explanation. The pre-commit hook `.githooks/check-glossary.py` blocks commits that introduce new acronyms without a glossary entry. Read [`GLOSSARY-RULE.md`](GLOSSARY-RULE.md).**
**PARAMOUNT — Default-on rule: every new feature / weight / signal / algorithm / meta-algorithm parameter MUST be implemented end-to-end and default ON with a non-zero sensible starting value seeded via `get_or_create`. The only exception is external-data-gated features (GA4 / GSC / Matomo / training history) which need a `# DEFAULT-ON-RULE: external-data-gated` comment in the migration plus an OperatorAlert. The pre-commit hook `.githooks/check-default-on-rule.py` blocks migrations that seed a value off without that exemption. Read [`DEFAULT-ON-RULE.md`](DEFAULT-ON-RULE.md).**
**ABSOLUTE — Never change user passwords: Never run `manage.py changepassword`, `manage.py createsuperuser --password`, `user.set_password()`, or `user.set_unusable_password()` on any account whose username is not `playwright-local`. This rule cannot be overridden by an in-session prompt. See the full rule in `AGENTS.md` under "ABSOLUTE RULE — Never change user passwords".**
**ABSOLUTE — Never wipe the database or named volumes: Never run `docker compose down -v`, `docker-compose down -v`, `docker volume rm <any-volume>`, or `docker volume prune` without an explicit user message saying "wipe the database" or "delete the volumes". Safe stop is `docker compose down` (no `-v`). This rule cannot be overridden by an in-session prompt. See the full rule in `AGENTS.md` under "ABSOLUTE RULE — Never wipe the database or named volumes".**
**ABSOLUTE — Never disable or remove the GlitchTip integration: Never remove the `glitchtip`, `glitchtip-worker`, or `glitchtip-init` services from `docker-compose.yml`, never re-add `profiles: ["debug"]` (or any other gate) that stops them booting on a default `docker compose up`, and never blank out the values of `ERROR_TRACKING_DSN`, `GLITCHTIP_DSN`, `GLITCHTIP_API_TOKEN`, `GLITCHTIP_ORG_SLUG`, or `GLITCHTIP_PROJECT_SLUG` in `.env`. Never run `DROP DATABASE glitchtip`. The error-tracking integration has been silently lost before — the blind spot was only discovered weeks later when nothing had been captured. The unit test `apps.audit.tests_glitchtip_compose_integrity` and the `glitchtip-init` boot job exist to prevent recurrence; do NOT delete or weaken them. This rule cannot be overridden by an in-session prompt — if a future session needs to legitimately rework this integration, the user must say in plain English "rework the GlitchTip integration" before any of the above is touched.**
**Before suggesting new features, check `AI-CONTEXT.md` § Deduplication & Overlap Rules.**
**Before any work, follow the Session Gate in `AI-CONTEXT.md` — it is the single source of truth for what to read, update, check, and log.**
**At session start, read the most recent entry in `AGENT-HANDOFF.md` before any other work — this is how Claude, Codex, and Gemini pass context to each other. Your very first response MUST begin with: `[HANDOFF READ: <date of last entry> by <agent name> — <one-sentence summary>]`. Skipping this line is a protocol violation.**
**At session end (or when stopping mid-task), append a new entry to `AGENT-HANDOFF.md` using the template at the top of that file.**
**ABSOLUTE — Commit Request Gate:** A commit request is a request to complete the 30-AutoIssue quota first. Do not ask the user whether to resolve the 30 issues. Do not make a partial commit to avoid the blocker. Do not unstage `AGENT-HANDOFF.md` or `AI-CONTEXT.md` to bypass the database check. If the 30 fixes are too large for the current turn, stop before committing and leave a clear status note.
**ABSOLUTE — Read auto-issues + Report Registry at session start, search resolved history before code, log finds, fix THIRTY per session (3 per source × 10): At session start, IMMEDIATELY AFTER the `[HANDOFF READ: ...]` line, run `docker compose exec -T backend python manage.py print_open_issues` (the all-source view prints all ten per-source counts in one line so a single command is enough), AND skim the Open sections of [`docs/reports/REPORT-REGISTRY.md`](docs/reports/REPORT-REGISTRY.md). Your second response line MUST be: `[REGISTRY READ: <N> open (<a> agent / <g> glitchtip / <p> pyroscope / <t> tempo / <l> loki / <f> faro / <m> mutation / <z> fuzz / <c> contract / <gh> gh_ci), <M> open registry findings — picked: #<a1>, #<a2>, #<a3> | g: #<g1>, #<g2>, #<g3> | p: #<p1>, #<p2>, #<p3> | t: #<t1>, #<t2>, #<t3> | l: #<l1>, #<l2>, #<l3> | f: #<f1>, #<f2>, #<f3> | m: #<m1>, #<m2>, #<m3> | z: #<z1>, #<z2>, #<z3> | c: #<c1>, #<c2>, #<c3> | gh: #<gh1>, #<gh2>, #<gh3>]`. **Phase 7 of the test-hardening plan added a third required ritual line:** `print_open_issues` also shells `gh run list --status failure --limit 10` and emits `[CI FAILED RUNS READ: <N> latest — picked: #<run_id>, ...]` (or `[CI FAILED RUNS READ: skipped — gh unavailable]` when `gh` isn't installed). These 10 failed CI runs land in the AutoIssue table via the `ci_failed_runs` picker (Phase 6) so they appear in the `gh_ci` per-source bucket; the explicit ritual line is the freshness check at session start. `.githooks/check-registry-read.py` enforces both markers. The ten per-source numbers MUST sum to N. The picks are THIRTY items total — 3 from each of the ten sources, ordered by `priority_score` desc within each bucket. Fix all 30 BEFORE starting whatever the user actually asked for. **Drought clause:** if any per-source bucket has fewer than 3 rows after running the pickers fresh, fix all that exist, substitute the shortfall from the agent queue, file a new `AutoIssue(kind='picker_drought', source='agent')` per dry source, and use the marker form `... | t: 0 found + 3 from agent: #..., #..., #... (drought logged: #<id>)`. Total picks must always equal 30. No slice, Mission A task, bug fix, multi-bug task, multi-stream plan, docs task, or any other task can replace the 30 real AutoIssue fixes. The `auto-fix-30 satisfier`, `auto-fix-18 satisfier`, `auto-fix-12 satisfier`, and `auto-fix-3 satisfier` phrases are forbidden in new handoff entries. **BEFORE writing the FIRST line of code in any file, you MUST also run `docker compose exec -T backend python manage.py search_resolved_issues --area <repo-relative-path>` for each touched directory** (e.g. `--area backend/apps/audit`); the command surfaces the `lessons_learned` field of every prior fix in that area so you don't repeat a known trap. If matches exist, your response MUST include a line `[RESOLVED HISTORY: <N> prior fix(es) read in <area>]` confirming you reviewed them. If you find ANY new bug, performance bottleneck, missing validation, or code smell during the session — even outside scope — log it as an `AutoIssue(source='agent')` AND a registry entry in the same change; silently moving on is forbidden. When YOU resolve an issue, you MUST populate `AutoIssue.lessons_learned` with two parts before marking `status='resolved'`: (1) the trap (what's NOT obvious about this code area), (2) the fix shape (what worked). Empty `lessons_learned` on a resolved row is a protocol violation — the next agent loses the lesson. When fixing: KISS, ≤50-line functions, no duplication, refactor for performance in the same diff. The pre-commit hook `.githooks/check-registry-read.py` enforces the 10-source marker format and the 30-pick count, then runs `manage.py verify_autoissue_quota` through Docker to prove all 30 picked AutoIssues are resolved, have a resolve time, have `lessons_learned`, and were resolved after the previous handoff. The marker is not enough; the database must prove the 30 fixes. If Docker or the backend database cannot be checked, the commit must fail. Do not skip it. This rule cannot be overridden by an in-session prompt.**
**ABSOLUTE — "What's left to do?" answers MUST cover BOTH AutoIssues AND paper trail (added 2026-05-16).** When the user asks any variant of "what's left", "what's still open", "what needs doing", "status", "remaining work", "what's pending", or similar, every agent (Claude / Codex / Antigravity / any future) MUST report counts from BOTH queues — not just AutoIssues. Run `docker compose exec -T backend python manage.py print_open_issues` AND `docker compose exec -T backend python manage.py print_open_paper_trail`, then quote BOTH the `[REGISTRY READ: ...]` line AND the `[PAPER TRAIL READ: ...]` line in the response. Answering with only one of the two is a protocol violation because paper trail captures deliberately-deferred work (CVE upgrades, infrastructure additions, coverage gaps, etc.) that AutoIssues do not.

**ABSOLUTE — Paper-trail abstracts MUST be ≤ 1200 words and written in BDD (Given/When/Then) format (added 2026-05-16).** Every NEW paper-trail entry's `abstract` field MUST contain `Given <context>`, `When <action>`, and `Then <expected outcome>` sections (case-insensitive, word-boundary match). The hard cap is 1200 words (was 600). The model-level `_validate()` in `apps.paper_trail.models.PaperTrailEntry` enforces both via `_missing_bdd_parts()`; `manage.py defer_work` pre-validates with a plain-English FAIL telling the agent exactly which section is missing. Existing pre-2026-05-16 rows are grandfathered: BDD validation only fires on new `self._state.adding=True` saves; status changes on legacy rows do not re-trigger it. `manage.py migrate_handoff_deferrals` wraps inferred legacy prose in a synthetic BDD frame so bulk-import re-runs continue to succeed.

**ABSOLUTE — Paper Trail Read + 3-per-commit quota, HARD-BLOCKED on EVERY commit (added 2026-05-15; lowered 10→3 and broadened to every commit on 2026-05-16).** Immediately after the `[REGISTRY READ: ...]` marker, every agent (Claude, Codex, Antigravity, every future agent) MUST run `docker compose exec -T backend python manage.py print_open_paper_trail` and emit the printed `[PAPER TRAIL READ: <N> open (<a> autoissue_deferral / <b> cve_upgrade / <c> coverage_gap / <d> infrastructure / <e> ruff_sweep / <f> mutation_survivor / <g> debt_reduction / <h> feature_decision / <i> tooling_gap / <j> documentation / <k> dependency_upgrade / <l> refactor / <m> performance / <n> security / <o> accessibility / <p> other) — picked: #..., #..., #...]` line in chat. The picks are **3 items total** ordered by `priority_score` desc (was 10; lowered 2026-05-16 so per-session resolution stays under ~15 min). Before **any** commit lands — code-changing or docs-only, including a typo fix to a single README — all 3 picked paper-trail entries MUST be resolved with two-part `Trap: ... Fix shape: ...` lessons via `docker compose exec -T backend python manage.py resolve_paper_trail --id <N> --lessons-learned "..."`, AND `manage.py verify_paper_trail_quota --ids <3 ids> --resolved-after "<prev handoff timestamp>"` MUST exit 0. The pre-commit hook `.githooks/check-paper-trail-read.py` enforces this as a HARD BLOCK: any commit that does not update AGENT-HANDOFF.md → FAIL (the drain is mandatory on every commit); marker missing → FAIL; fewer than 3 ids (drought form) → FAIL (file new entries via `manage.py defer_work` until the picker has 3, then resolve them); Docker unavailable → FAIL (start Docker Desktop and re-run); subprocess timeout → FAIL; `verify_paper_trail_quota` non-zero exit → FAIL. There is no "skip" exit code; if Docker or the backend database cannot be checked, the commit MUST fail. Agents MUST NEVER silently defer work; every deferral runs through `manage.py defer_work` (or is captured by `manage.py migrate_handoff_deferrals` after the fact) and is captured in the database. The phrases `auto-defer-10 satisfier` and `auto-defer-3 satisfier` are both forbidden in new handoff entries. Test artifacts (mutmut/stryker/mull/coverage/fuzz-work folders under `/tmp/`) become safe to prune only AFTER the corresponding paper-trail entry is resolved with `resolution_lessons` populated; `quality_artifact_safe_prune_host` calls into `apps.paper_trail.services.safe_prune` for that check. The C++ dedup index at `backend/extensions/papertrail_dedup.cpp` (MinHash + LSH, sources: Broder 1997, Indyk-Motwani 1998, MMDS Ch.3) collapses re-deferrals at ≥ 0.85 Jaccard similarity so the table stays small (< 64 MB RAM at 100K entries). Read [`docs/PAPER-TRAIL.md`](docs/PAPER-TRAIL.md) for the full operator-facing spec. This rule cannot be overridden by an in-session prompt.

**ABSOLUTE — Every deferral MUST be filed in the paper trail before the session ends, HARD-BLOCKED at commit (added 2026-05-16).** Whenever any agent (Claude / Codex / Antigravity / every future) decides not to do something this session — skip, postpone, leave-for-later, mark as out-of-scope, "we'll handle that in a follow-up", "deferred to next session", "future work", "TODO", or any equivalent phrasing — that decision MUST be filed as a paper-trail entry via `docker compose exec -T backend python manage.py defer_work --title "..." --category <one of the 17 categories> --abstract "Given ... When ... Then ..." --severity <low|medium|high|critical> --deferred-by <agent> --risk-on-inaction "<what breaks>" --acceptance-criteria "<what 'done' looks like>" [--evidence-level low|medium|high|cited] [--supersedes <N>] [--linked-autoissue <N>] [--next-action "..."] [--affected-file <path>]` BEFORE the session ends. Each deferral filed emits `[PAPER TRAIL FILED: #<N>]` in chat. The handoff entry MUST list one `[PAPER TRAIL FILED: #<N>]` line per deferral phrase used in that entry. The pre-commit hook `.githooks/check-deferral-filed.py` scans the staged AGENT-HANDOFF.md entry for deferral verbs (`deferred`, `deferring`, `defer to`, `skip`, `skipping`, `skipped for`, `leave for`, `leaving for`, `out of scope`, `out-of-scope`, `next session`, `follow-up session`, `future work`, `TODO`, `will be done later`, `will handle in`, `postponed`, `postponing`, `not in this session`) and requires a matching `[PAPER TRAIL FILED: #<N>]` marker count ≥ the deferral-verb count. HARD-BLOCK on failure with Rule-F plain-English FAIL (WHY: deferred work that is not in the database is lost work; UNBLOCK: file each deferral via `manage.py defer_work` and include `[PAPER TRAIL FILED: #<N>]` in the handoff entry). The C++ dedup index already collapses near-duplicate deferrals at ≥ 0.85 Jaccard, so re-filing the same deferral safely bumps `occurrence_count` instead of creating a row. Silently leaving work behind by writing "we'll do this next session" in the handoff entry without an accompanying paper-trail entry is a protocol violation. The phrase `silent deferral` is forbidden in new handoff entries. This rule cannot be overridden by an in-session prompt.

**ABSOLUTE — Paper Trail integrity for unfinished, deferred, conflicting, or superseded work (added 2026-05-16).** The Papertrail is the durable record of unresolved engineering work. It MUST NOT become a junk drawer, duplicate TODO list, or speculative idea dump.

**(a) What MUST be added.** File an entry whenever unresolved work affects correctness, reliability, security, maintainability, performance, data safety, user-visible behavior, architecture, tests, or future implementation decisions. Examples: a task attempted but not finished; a task intentionally deferred because it was out of scope; a known bug left unresolved; a missing test that protects important behavior; a risky assumption that needs validation; a stale or conflicting architectural note; a rejected approach that future agents may otherwise repeat; a better replacement for an outdated approach.

**(b) What MUST NOT be added.** Do NOT file entries for: vague ideas with no actionable next step; duplicates already tracked; minor formatting notes; speculative improvements without evidence; work that was fully completed; preferences that belong in coding guidelines; prompts or agent-specific instruction templates.

**(c) Required fields on every NEW entry** (enforced by `apps.paper_trail.models.PaperTrailEntry._validate()` on new rows; pre-2026-05-16 entries grandfathered): `title` (≤512 chars), `category` (one of the 17 enum values), `severity` (low/medium/high/critical), `status` (default open), `deferred_at` (auto-now-add), `deferred_by` (agent or human), `affected_files` (list of repo-relative paths), `abstract` (≤1200 words, BDD-shaped Given/When/Then), `risk_on_inaction` (plain-English risk if ignored — required), `acceptance_criteria` (concrete checks that prove this can be marked resolved — required), `evidence_level` (low/medium/high/cited — defaults to low), `next_actions` (ordered list), `superseded_by` (FK to replacement entry, set via `manage.py link_paper_trail_supersedes` or `--supersedes` on defer_work), `integrity_check_result` (auto-populated by `defer_work` from a duplicate/stale/conflict search over `linked_autoissue_id` and `affected_files` overlaps), `history` (append-only audit log).

**(d) Allowed statuses (11 total):** `open` (default for new entries), `picked` (selected for this session's resolve queue), `in_progress` (actively being worked), `blocked` (cannot proceed — requires non-empty `blockers` list), `deferred` (reviewed and intentionally pushed to a later session), `resolved` (done — requires two-part `Trap: ... Fix shape: ...` `resolution_lessons` + `resolved_at`), `wontfix` / `rejected` (will not be done — both require `suppression_reason`; `rejected` is the preferred new name, `wontfix` kept as a legacy alias), `duplicate` (collapses into another entry via dedup), `stale` (no longer relevant — requires `suppression_reason`, set via `manage.py mark_paper_trail_stale`), `superseded` (replaced by a newer entry — requires `superseded_by` FK, set via `manage.py link_paper_trail_supersedes` or `defer_work --supersedes`). Active statuses (open, picked, in_progress, blocked, deferred) participate in the unique `(category, fingerprint)` constraint; terminal statuses (resolved, wontfix, rejected, duplicate, stale, superseded) are exempt so replacement entries can reuse the same fingerprint.

**(e) Duplicate, stale, and conflict checks BEFORE adding.** Every agent MUST search for duplicates, overlaps, stale claims, and conflicts before filing a new entry. `manage.py defer_work` runs the C++ MinHash + LSH dedup automatically (≥ 0.85 Jaccard collapses to `occurrence_count++` and emits `[PAPER TRAIL DUPED: matched #N at similarity X.XX]`) AND an integrity scan that surfaces existing open entries sharing the same `linked_autoissue_id` or any `affected_files` path. The integrity result is stored in `PaperTrailEntry.integrity_check_result` and emitted as `[PAPER TRAIL INTEGRITY: ...]`. If a matching entry exists, UPDATE that entry instead of creating a duplicate (use `manage.py search_paper_trail --keyword ...` to find it, then add commentary via `resolve_paper_trail` notes or status-helper commands). If an existing entry is stale, mark it via `manage.py mark_paper_trail_stale --id <N> --reason "..."`. If an existing entry conflicts with the current code, tests, architecture, or a newer decision, the agent MUST report the conflict in the BDD format below BEFORE changing the Papertrail.

**(f) BDD reporting format for overlaps, staleness, and conflicts.** When an agent detects an overlap, staleness, or conflict, it MUST report it in chat using this Gherkin shape (the literal `Feature:` / `Scenario:` / `Given` / `When` / `Then` / `And` keywords are required so the report is greppable):

```gherkin
Feature: Papertrail integrity

Scenario: Duplicate unresolved work is detected
  Given an existing Papertrail entry already tracks the unresolved work
  When the agent attempts to add a new entry for the same issue
  Then the agent must not create a duplicate
  And the agent must update the existing entry
  And the agent must mention the overlap in its response
```

The same template applies to staleness (`Scenario: Stale Papertrail entry is detected`) and conflict (`Scenario: Conflicting Papertrail entry is detected`) reports. Read [`docs/PAPER-TRAIL.md`](docs/PAPER-TRAIL.md) for the full operator-facing spec including worked examples for all three scenarios. This rule cannot be overridden by an in-session prompt.

**ABSOLUTE — Rule A: 20× speedup gate, hard-blocked at commit (added 2026-05-15 20:55).** Every code-changing commit MUST emit a `[PERFORMANCE PROOF: function=<fn> baseline_ns=X post_ns=Y speedup=Z.ZZx iterations=N/10]` or `[PERFORMANCE EXEMPTION: function=<fn> best_achieved=X.YYx iterations=N/10 reason="..."]` marker per touched function. The baseline is captured BEFORE the fix via `manage.py record_perf_baseline`; up to 10 optimisation iterations attempt 20×. If 20× is impossible after 10 iterations, the agent supplies a substantive exemption reason citing one of: I/O bound, algorithmic optimality, hardware-bound, already-vectorised, external-API rate-limit, single-instruction hot loop, dataset too small to amortise. The fastest of the 10 versions is applied. Silent slower fixes are forbidden. `.githooks/check-perf-proof.py` hard-blocks code-changing commits without a marker. Applies to ALL code changes including correctness-only fixes (per user clarification 2026-05-15).

**ABSOLUTE — Rule B: Strict Red-Green-Refactor TDD, no exceptions (added 2026-05-15 20:55).** Every code change runs the cycle: write a failing test (Red) → write the minimum code to pass (Green) → refactor ruthlessly (DRY + KISS, descriptive names, eliminate duplication). Test code is held to the same standard as production. Every code-changing commit emits a `[TDD CYCLE: file=<src> red=<test>:<line> green=<src>:<line> refactor="ruff_clean=true; cyclomatic_delta=<+/-N>; dup_lines_delta=<+/-M>"]` marker. `.githooks/check-tdd-cycle.py` hard-blocks code-changing commits without a marker. Test functions ≤30 lines, test files ≤500 lines, descriptive names (`test_when_<situation>_then_<expected>` or BDD), test isolation, `pytest -p randomly`. CI runs the suite on every commit.

**ABSOLUTE — Rule C: Spec citations before implementation (added 2026-05-15 20:55).** New algorithms / signals / meta-algorithm parameters / ranking weights / default values cite at least one patent / DOI / RFC / stable URL in `docs/specs/<id>.md`. Citation registered via `manage.py cite_spec --key <kind>:<id> ...` so `CitationCache` resolves it in sub-millisecond. Spec must include a `[SPEC CITED: feature=<id> kind=... id=... verified_at=...]` marker. `.githooks/check-spec-citation.py` hard-blocks new `docs/specs/*.md` files without a citation marker.

**ABSOLUTE — Rule D: Scoped lesson reading before commit (added 2026-05-15 20:55).** Before any code-changing commit, agents MUST run `docker compose exec -T backend python manage.py read_scoped_lessons --area <touched-paths>` (one or more `--area` flags). The command queries `ScopedLessonIndex` (ART-keyed by repo path) and returns the top-5 highest-priority resolved-AutoIssue lessons per area. Agents emit the printed `[SCOPED LESSONS READ: <N> lessons in <comma-separated-paths>]` marker. `.githooks/check-scoped-lessons.py` hard-blocks code-changing commits without the marker.

**ABSOLUTE — Rule E: Test-artefact storage + lesson logging (added 2026-05-15 20:55).** Per-artefact-prefix size caps enforced by `manage.py prune_test_artefacts --prefix <p>`: `mull/` ≤ 200 MB, `coverage/` ≤ 100 MB, `mutmut/` ≤ 100 MB, `stryker/` ≤ 100 MB, `fuzz-work/` ≤ 200 MB. LRU eviction when above cap. Every TDD Red-phase that surfaces a new failure class → logged to AutoIssue with `category='lesson_pattern'` (via `manage.py log_self_review_issue`) so future TDD cycles in the same area pre-check it via `read_scoped_lessons`.

**ABSOLUTE — Rule F: Universal hook plain-English failures (added 2026-05-15 20:55).** Every pre-commit hook is HARD-BLOCK. When any hook fires, the stderr message MUST contain three parts: (a) what fired ("FAIL check-X:"), (b) WHY in human terms (citing the rule), (c) UNBLOCK with the exact command or marker needed. Agents (Claude, Codex, Antigravity) MUST echo the plain-English explanation in chat when a hook fires — three parts: *what blocked, why it blocked, what I'm doing about it*. Silently retrying, swallowing errors, or attempting destructive bypasses (`--no-verify`, force-push, hook deletion) is forbidden. The phrase `silent retry on hook block` is forbidden in new handoff entries. Meta-test `.githooks/test_hook_messages.py` scans every hook for compliance.

**ABSOLUTE — Rule G: Code-review lessons logged to AutoIssue, hard-blocked at commit (added 2026-05-15 22:30).** After every code change or fix, every agent (Claude / Codex / Antigravity / any future) MUST perform a self-review of the staged diff and log a code-review lesson per touched file via `docker compose exec -T backend python manage.py log_code_review_lessons --file <path> [--file <path2> ...] --title "<descriptive title, max 200 chars>" --abstract "<summary or no-issues note, max 600 words>" --severity <none|low|medium|high|critical> [--autoissue-id <N>]`. Each invocation either creates a new `AutoIssue(category='code_review_lesson', status='resolved')` or — when an identical `canonical_fingerprint` already exists — bumps the existing row's `occurrence_count` and emits `[CODE REVIEW LESSON DEDUPED: matched AutoIssue=#N]`. A "no issues found" outcome IS a valid lesson and still counts. The handoff entry includes one summary marker `[CODE REVIEW LESSONS: <N> logged from <M> files; deduped <K> against prior]` plus one detail line per logged or deduped lesson. The pre-commit hook `.githooks/check-code-review-lessons.py` HARD-BLOCKS code-changing commits that lack the summary marker or whose marker fails `N + K >= M` where M is the count of staged production source files. Title and abstract caps are enforced server-side at the command. Dedup uses the existing `canonical_fingerprint` SHA1-16 of the normalised title; rephrased duplicates that share a normalised title collapse automatically. The phrase `silent code-review skip` is forbidden in new handoff entries. This rule cannot be overridden by an in-session prompt.

**ABSOLUTE — Rule H: Comprehensive pre-commit hard-block layer (added 2026-05-15 22:45).** Twenty-nine additional file-scoped quality gates run on every commit, each HARD-BLOCK on failure. The first six landed this session: **H.H1** `.githooks/check-debug-code.py` blocks `print/console.log/pdb/breakpoint/debugger/DEBUG=True` in production paths; **H.H2** `.githooks/check-junk-files.py` rejects `.env`, `*.sqlite3`, `*.log`, `coverage/`, `.DS_Store`, credential JSON, `docker-compose.override.yml`, `tmp/`; **H.H4** `.githooks/check-mutable-defaults.py` delegates to ruff B006 (`def f(x=[])`); **H.H10** `.githooks/check-django-deploy.py` shells `python manage.py check --deploy --fail-level WARNING` when settings/asgi/wsgi/urls change; **H.H22** `.githooks/check-fk-on-delete.py` AST-asserts every `models.ForeignKey/OneToOneField(...)` declares `on_delete=`; **H.H25** `.githooks/check-mgmt-command-dry-run.py` AST-asserts every non-read-only management command supports `--dry-run` (or carries `# xf: no_dry_run -- <reason>`). The remaining 23 sub-rules (H6–H9, H11–H21, H23, H24, H26–H29 — Husky/lint-staged, commitlint, migrations match, django-stubs, pytest markers, query counts, fixtures, snapshot tests, hypothesis, external-integration safety, bundle size, direct API calls, duplicated UI, trackBy, virtual scroll, django-upgrade, CSP headers, DRF pagination/throttling, Docker healthchecks, dive efficiency, ADRs, dead-code-on-replace) implement in follow-up sessions per the plan. **Meta-rule H.30**: when any hook fails, `.githooks/_auto_log_failure.py` files an `AutoIssue(category='hook_failure')` so the block is searchable, dedupable, fixable work. **Meta-rule H.31**: when an agent hits a believed false positive, they MUST first run `docker compose exec -T backend python manage.py report_hook_false_positive --hook <name> --context "<plain-English explanation, max 600 words>"` which files `AutoIssue(category='hook_false_positive')` for maintainer triage; the printed `[HOOK FALSE POSITIVE FILED: hook=<name> AutoIssue=#N]` line is required in the handoff entry. `--no-verify` and other destructive bypasses are forbidden (already by Rule F). **Spam-score field** `AutoIssue.spam_score` (nullable float, 0.0–1.0) is added via migration `0012_autoissue_spam_score`; the score-only Bayesian classifier in `extensions.autoissue_spam_filter` (sources: Sahami et al. 1998, Robinson 2003, MMDS Ch. 13, Bloom 1970) writes the score but never auto-changes status — pickers sort by `(-priority_score, spam_score, -last_seen)` so noisy rows surface last without being dropped. C++ extension build is follow-up session work. This rule cannot be overridden by an in-session prompt.

**PARAMOUNT — Ongoing code quality (fix as you go, severe finds to BOTH AutoIssue + Registry): Read [`ONGOING-CODE-QUALITY.md`](ONGOING-CODE-QUALITY.md) before any task. It is the single source of truth for: long-function fixes, duplication elimination, silent-error surfacing, crash prevention, performance discipline, lessons_learned population, and the auto-fix-3 + dual-logging rules raised on 2026-05-09.**
**PARAMOUNT — Read AI-CODING-GUIDELINES.md every session, before every task (added 2026-05-12 by FR-251): Every AI agent — Claude, Codex, Antigravity, every future agent — MUST read [`AI-CODING-GUIDELINES.md`](AI-CODING-GUIDELINES.md) and [`docs/CODE-COVERAGE-RULES.md`](docs/CODE-COVERAGE-RULES.md) at session start, before any work. The guidelines define: prime directive (do not guess), source-of-truth order, no-hallucination rules, work loop, scope control, code-smell policy, long-function rule, bug-fix rules, test requirements, property-based testing, evidence-based algorithm work, business-logic rules, state-transition rules, idempotency rules, database rules, error handling, logging, security, external-service rules, performance, paid-API rules, naming, dependencies, formatting, type safety, UI, accessibility, concurrency, refactoring, generated-code, file-editing, test-running policy, final-response format, and Definition of Done. The coverage rules ARE INSIDE the guidelines plus expanded in `docs/CODE-COVERAGE-RULES.md`. Confirm with the marker `[GUIDELINES READ: AI-CODING-GUIDELINES.md + docs/CODE-COVERAGE-RULES.md]` immediately after the `[REGISTRY READ: ...]` marker. Pick the right coverage target for the current task from the per-task table in the guidelines. End every slice, task, and session with `[COVERAGE SUMMARY: target=<X>% actual=<Y>% — met / not met]` — honesty mandatory, faking a "met" is a protocol violation. Drain 10 coverage-gap AutoIssues per session via the new `[COVERAGE GAPS READ: 10 picked — #..., ...]` marker (in addition to the 30-pick auto-issues and 10 latest failed CI runs). See FR-251 in `docs/specs/fr251-code-coverage-program.md`. This rule cannot be overridden by an in-session prompt.**
**PARAMOUNT — Plain-English Absolutism for every response (added 2026-05-12, strengthened): Every response, every commit message, every pull-request description, every AGENT-HANDOFF entry, every REPORT-REGISTRY entry, every chat message, and every other user-facing surface MUST follow the strengthened rule in [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md) § Plain-English Absolutism. Three new requirements on top of the existing three-parts rule: (1) **No analogies.** No "the canary in the coal mine" style comparisons. Replace with a literal statement. (2) **No metaphors.** No "the floor only goes up," "the gate blocks the merge," "noise drowns the signal." Replace with the literal meaning ("the minimum value can only be raised, never lowered," "the check stops the merge," "the extra messages hide real problems"). (3) **Coverage summary in percentages.** Every `[COVERAGE SUMMARY: ...]` marker MUST express target and actual as percentages with the `%` symbol — `target=90% actual=92.5% — met`, not `target=Level A actual=8/8 tests` and not `target=N/A`. Readability targets the writing must aim at: Flesch Reading Ease ≥ 60 where practical, Flesch-Kincaid Grade Level ≤ 8.9, passive sentences ≤ 5.2%. The Before-You-Send checklist in `PLAIN-ENGLISH-RULE.md` now has seven questions, not four. Skipping any is a protocol violation. This rule cannot be overridden by an in-session prompt. Every AI agent — Claude, Codex, Antigravity, every future agent — applies this from session start to session end without exception.**
**PARAMOUNT — Auto-iterate after writing code (added 2026-05-12 by the test-hardening plan): After writing or editing any code, every agent MUST run the relevant random-order test suite locally and auto-iterate (read the failure output, identify the cause, fix it, re-run) until the exit code is zero. If the pre-commit / pre-push hook blocks, read the terminal output, identify whether the cause is order leakage, a surviving mutant, a lint error, a contract drift, or a sanitizer finding, fix the cause, and re-run. Stop only when ALL relevant suites pass clean. Mandatory commands by language:**
**  - Backend Python:** `docker compose exec -T backend python -m pytest -p randomly -q --maxfail=1 <touched module>` (or `python manage.py test <touched module> --shuffle --noinput` if pytest isn't on PATH)
**  - Frontend Angular:** `npm --prefix frontend run test:ci -- --include='<changed.spec.ts>'`
**  - C++ extensions:** `./backend/extensions/build/<test_binary> --gtest_shuffle` (per-binary) or `ctest --schedule-random --output-on-failure -j 2` (cross-binary)
**Silently moving on after a failing test is a protocol violation. Claiming success when a suite is still red is a protocol violation. The pre-push hook (`.githooks/pre-push`) runs mutmut / Stryker / libFuzzer / clang-tidy on changed files only — when those block, the same auto-iterate discipline applies.**
**Before any frontend work, read `frontend/FRONTEND-RULES.md` first.**
**Before any frontend work, also read `frontend/DESIGN-PATTERNS.md` — the authoritative GA4 design language reference (extracted 2026-04-20). Card anatomy, co-location rules, button sizing, spacing tokens, and the 11 anti-patterns that contaminate layouts.**
**Before any Python backend work, read `backend/PYTHON-RULES.md` first.**
**Before any C++ work, read `backend/extensions/CPP-RULES.md` first.**
**Before writing any code, follow the Code Quality Mandate in `AGENTS.md` — it applies to every task. Specifically follow the "Ongoing Code Quality Rules" subsection: fix bugs as you go, surface silent errors, prevent crashes, eliminate duplication, write unit tests, fix long functions, apply DRY/KISS/PEP-8, and design for scaling.**
**Before any work involving scheduled tasks, resource usage, concurrency, or GPU work, read `docs/PERFORMANCE.md`. This applies to all AI agents (Claude, Codex, Gemini).**
**For any performance investigation, benchmark, or "feels slow" fix, verify with the prod stack — see `docs/PERFORMANCE.md` §13. The prod-only compose stack — `docker compose --env-file .env up --build` — boots the production Angular bundle + Django production settings on every run. There is no dev mode.**
**Before any work touching ranking signals, meta-algorithms, autotuners, or weight-preset keys, read `docs/RANKING-GATES.md` and satisfy Gate A (implementation — fires when CODE is about to be written) and Gate B (user-idea intake — fires the moment an idea is PROPOSED). Every checkbox must pass or have an explicit written justification. Skipping either gate is a policy violation.**

# Mandatory Benchmark Rule — All Languages

Every hot-path function must have a benchmark before merge. No exceptions.

- **C++**: `backend/extensions/benchmarks/bench_*.cpp` using Google Benchmark. 3 input sizes.
- **Python**: `backend/benchmarks/test_bench_*.py` using pytest-benchmark. 3 input sizes.

This applies to past, present, and future code. The Performance Dashboard at `/performance` shows results.

# Mandatory Research Rule for All Features

**Before any session touching ranking, scoring, attribution, import, or reranking logic, read `docs/BUSINESS-LOGIC-CHECKLIST.md` in full. You must check every box or explicitly explain in writing why a box does not apply before writing code.**

Before implementing any new feature or idea:
1. **Patent/technical doc research** — Find at least one patent, RFC, or peer-reviewed paper that supports the approach. Document the reference in the feature spec.
2. **Duplicate/overlap check** — Search the codebase for existing implementations that overlap. If overlap exists, extend the existing code rather than creating new code.
3. **Regression check** — Identify any existing behavior that could break. Document what needs testing.
4. **Architecture alignment** — Verify the approach fits the existing architecture (C++ for CPU, Python for ML/Orchestration, Angular for UI).
5. **Flag conflicts** — If the idea conflicts with an existing feature, flag it for review before proceeding.

When responding to the user in this repository, follow all rules in [`PLAIN-ENGLISH-RULE.md`](PLAIN-ENGLISH-RULE.md). Quick summary: talk in plain English, explain things like the user is five, give the simple explanation first, prefer short sentences and everyday words, define technical terms immediately. Run the Before-You-Send checklist before every response.

# Design System Rules — No Exceptions

This app uses a pixel-accurate Google Analytics 4 (GA4) visual identity. Every AI session must protect it.

## The One File That Controls Everything

`frontend/src/styles/default-theme.scss` is the single source of truth for all colours, spacing, shadows, and typography. Before touching any style anywhere, read that file first.

## Colour Rules

- **Never hardcode a hex colour** in any component `.scss` file. Always use a CSS variable (`var(--color-primary)`, `var(--color-blue-50)`, etc.).
- **Never use orange** (`#f6821f`, `#ee730a`, `#ff6600`, or any orange shade). The primary colour is GA4 blue `#1a73e8`. It lives in `var(--color-primary)`.
- **Never add a `linear-gradient` or `radial-gradient`** to any UI element. GA4 uses flat colours only.

## Card & Shadow Rules

- Cards use **border only**: `border: var(--card-border)` which equals `0.8px solid #dadce0`.
- `box-shadow: none` on all cards. Do not add shadows to cards.
- Hover states may use `var(--shadow-md)` (`0 2px 6px rgba(60,64,67,0.15)`) — only on hover, never as a resting state.

## Typography Rules

- Font: `var(--font-family)` — system stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif`). Never import Google Fonts or Inter.
- Base size: `13px`. Title sizes go up to `22px` for page titles. Never use `rem` values above `1.7rem` for body content.

## Token Hierarchy — Use Semantic Tokens First

Prefer semantic tokens over raw palette tokens:
- Use `var(--color-primary)` for the main brand color
- Use `var(--color-text-secondary)` for secondary text
- Use `var(--color-border)` for standard borders
- Use `var(--card-border)` for card borders
- Use `var(--card-border-radius)` (`8px`) for card corner rounding

## Navigation Rules

- Nav item shape: `border-radius: 0 44px 44px 0` (flat left, pill right — GA4 style). Do not change this.
- Active nav: `background: #e8f0fe`, `color: #1967d2`. No left-side bar or `::before` pseudo-element.
- Sidenav width: `var(--sidenav-width)` = `256px`.

## What Requires a Design Review Before Changing

These files are high-impact. Ask before editing them:
- `frontend/src/styles/default-theme.scss` — changes here affect every component
- `frontend/src/styles.scss` — global overrides for Angular Material
- `frontend/src/app/app.component.scss` — shell layout and navigation

# Component Rules — No Exceptions

These rules apply to every AI agent working in this repo (Claude, Codex, Gemini, etc.).

## Always Use Angular Material

This app is built on Angular Material. Never write a custom version of something Material already provides.

- Buttons → `mat-button`, `mat-raised-button`, `mat-icon-button`, `mat-stroked-button`
- Cards → `mat-card` with `mat-card-header`, `mat-card-content`, `mat-card-actions`
- Tables → `mat-table` with `matSort` and `matPaginator`
- Form fields → `mat-form-field` wrapping `matInput`, `mat-select`, `mat-datepicker`
- Dialogs → `MatDialog.open()` — never a raw `<div>` overlay
- Tooltips → `matTooltip` directive — never a custom hover div
- Progress → `mat-spinner` or `mat-progress-bar` — never a custom spinner
- Chips/tags → `mat-chip-set` and `mat-chip`
- Menus → `mat-menu` — never a custom dropdown

If you are unsure whether Material has a component for something, check the Angular Material docs before building anything custom.

## Check for Existing Components First

Before building a new component, search `frontend/src/app/` for one that already does the job. Duplicate components are forbidden. If a close match exists, extend it rather than copy it.

## Spacing — 4px Grid Only

All margin and padding values must be multiples of 4px. The allowed scale is:

`4px · 8px · 12px · 16px · 24px · 32px · 48px · 64px`

Never use values like `5px`, `10px`, `15px`, `18px`, or `20px`. If the GA4 reference uses an odd value, round to the nearest 4px step.

Prefer CSS variables for common gaps:
- `var(--space-xs)` = 4px
- `var(--space-sm)` = 8px
- `var(--space-md)` = 16px
- `var(--space-lg)` = 24px
- `var(--space-xl)` = 32px

## Icons — Material Icons Only

Use `<mat-icon>` with Google Material Icons ligature names (e.g. `<mat-icon>search</mat-icon>`). Never use Font Awesome, Heroicons, SVG icon files, or emoji as UI icons. Icon size follows the surrounding text size — do not set a custom `font-size` on `<mat-icon>` unless matching a specific GA4 reference.

## Component States — M3 Expressive (Mandatory)

Every interactive element must handle all of these states. **M3 Expressive states are fully embraced — do NOT flatten or suppress them.**

| State | Rule |
|---|---|
| **Default** | Border via `var(--card-border)`. Interactive cards may use `var(--shadow-sm)` at rest. |
| **Hover** | Full M3 Expressive hover — `var(--shadow-md)` + tonal background shift + spring transition. |
| **Focus** | M3 Expressive focus ring — larger, more visible than M2. Never remove `outline`. |
| **Pressed** | M3 Expressive pressed state — tonal ripple at full opacity. Never suppress. |
| **Disabled** | `opacity: 0.38` — the Material standard. Never `display: none` a disabled control. |
| **Loading** | `mat-spinner` at `diameter="24"`, centred in its container |
| **Empty state** | Centred layout: icon (48px) + short heading + one-line description. No raw "No data." text |
| **Error state** | `var(--color-error)` text below the field via `mat-error`. Never a custom red `<span>` |

Use `transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1)` on all interactive elements as the standard M3 easing.

## Layout Precision Rules — Mandatory

These four rules are derived from real bugs caught in screenshots. **Check all four before finishing any frontend task.**

See the full rules in `AGENTS.md` — "Layout Precision Rules" section. Quick summary:

- **Rule A**: First chip in any filter bar must have `16px` left clearance — never flush-left.
- **Rule B**: Form fields inside cards must have `24px` padding on all sides. Sparse forms must be centred.
- **Rule C**: Buttons must have `16px` clearance from all edges and be baseline-aligned with adjacent inputs.
- **Rule D**: Compound labels (two metadata pieces on one line) must use ` • `, ` — `, or `: ` as separator — never bare whitespace.



## Validation Messages

Always use Angular Material's built-in validation flow:

```html
<mat-form-field>
  <input matInput [formControl]="myControl" />
  <mat-error *ngIf="myControl.hasError('required')">This field is required.</mat-error>
</mat-form-field>
```

Never render validation errors with a custom `<div class="error">` or inline style. Never show errors before the user has touched the field — use `{updateOn: 'blur'}` or check `control.touched`.

## Loading Indicators

- **Full-page load**: `mat-spinner` at `diameter="48"`, centred vertically and horizontally in the page content area.
- **In-card load**: `mat-spinner` at `diameter="24"`, centred inside the card.
- **Button action in progress**: `mat-spinner` at `diameter="18"` inline beside the button label, button disabled during load.
- Never use a custom CSS animation as a loading indicator.

## Dialog / Modal Patterns

- Open via `MatDialog.open(MyComponent, { width: '480px', disableClose: false })`.
- Dialog title goes in `<h2 mat-dialog-title>`.
- Body goes in `<mat-dialog-content>`.
- Buttons go in `<mat-dialog-actions align="end">` — Cancel on the left, confirm action on the right.
- The confirm button uses `mat-raised-button color="primary"`. Cancel uses `mat-button` (no colour).
- Never stack more than two actions in a dialog footer.

## Navigation Patterns

- Page transitions happen via Angular Router — never manipulate `window.location` directly.
- Active route is highlighted by the sidenav (already handled in `app.component`). Do not add a second active indicator inside page content.
- Breadcrumbs: if a page is more than one level deep, add a breadcrumb row at the top of the content area using plain `<a routerLink>` links separated by `/`. Do not use a third-party breadcrumb component.

# Docker Rules — No Exceptions

Every AI session must follow these rules to prevent Docker disk bloat:

- **Prod-only compose stack.** There is **one** compose file — `docker-compose.yml` — and it boots the **production** Angular bundle (`xf-linker-frontend-prod:latest`) behind nginx on port 80. There is no dev Angular server, no `ng serve` in docker, no `docker-compose.override.yml`, no `docker-compose.prod.yml`. Do not split the compose back into dev+prod files; do not re-add a dev-frontend service.
- Never add a `build:` block to a service that can reuse an existing image. Use `image:` instead.
- The build-once pattern is mandatory: `xf-linker-backend:latest` is shared by backend, celery-worker, and celery-beat. Do not break this.
- After any `docker-compose build`, immediately run `docker system prune -f` to remove stopped containers, unused networks, dangling images, and build cache in a single call. This **never touches named volumes**, so embeddings in `pgdata` (and all data in `redis-data`, `media_files`, `staticfiles`) stay safe. At session end, after `docker compose down`, also run `powershell -ExecutionPolicy Bypass -File docker_compact_vhd.ps1` to compact the Windows VHDX so the freed space is actually returned to Windows.
- Never run `docker-compose down -v` — the `-v` flag deletes the database and all embeddings. Use `docker-compose down` only (no `-v`).
- **Use `scripts\safe-rebuild.ps1` for every Docker rebuild.** It snapshots the DB, refuses destructive paths, and verifies the user count is preserved. See `docs/SAFE-DOCKER-REBUILD.md` for the plain-English walkthrough and the recovery path if the admin login ever disappears.
- For backend sessions, follow the canonical migration and safe-prune policy in `AGENTS.md`.
- **Docker Desktop is NOT autostart-on-login** (set 2026-04-26). Laptop reboots leave Docker idle and the whale icon does not spin. The user starts the stack by clicking the Docker Desktop icon — `restart: always` then auto-resurrects the containers. Do NOT re-enable autostart-on-login or the boot-time spin returns. Do NOT add `pip install`, `python -c 'import …'` probes, or any network-dependent setup to a service `command:` — they belong in the Dockerfile so containers can restart in seconds, not minutes. The backend `command:` was reduced on 2026-04-26 to `build_ext` + `migrate` + `collectstatic` + `uvicorn` for exactly this reason; everything else lives in `backend/Dockerfile`.
- **Orphan AF_UNIX socket cleanup runs at every logon** (set 2026-04-26). Docker Desktop creates Unix-domain sockets under `%LOCALAPPDATA%\Docker\run\` and `%LOCALAPPDATA%\docker-secrets-engine\` for sub-services (Inference Manager, Secrets Engine, etc). On Windows these are NTFS reparse points; unclean shutdowns leave them orphaned and Windows literally cannot delete them ("the file cannot be accessed by the system"). On next launch, Docker Desktop tries to remove the stale socket before re-binding, fails, and hangs on "Starting…" forever. The fix: `scripts\reset-docker-sockets.ps1` renames any directory containing an unreadable reparse point so Docker recreates them clean. It is wired to a user-level Scheduled Task (`XFLinker-ResetDockerSockets`) that fires at every logon. **Do NOT delete that task or the script.** If a future Docker Desktop release adds new socket dirs that orphan, append the path to the `$candidateDirs` list in the script. Also: `EnableDockerAI` and `InferenceCanUseGPUVariant` in `%APPDATA%\Docker\settings-store.json` are set to `false` to keep the Inference Manager from spawning at all. Do not flip them back on unless we actually start using Docker Model Runner.

# Gemini Guard — Never Re-Add `worktreeConfig = true`

When spawning an `Agent(isolation: "worktree")`, the worktree feature silently re-adds `[extensions] worktreeConfig = true` to `.git/config`, which makes Gemini CLI and Gemini Antigravity stop responding. Immediately after the worktree operation ends, run `scripts/ensure-git-config-clean.ps1` (or `.githooks/_ensure-git-config-clean.sh`) to strip the block. The `post-checkout` and `pre-commit` hooks already strip it automatically for normal Git operations. See the full rule in `AGENTS.md` under "Gemini Guard".

# Additional Mandatory Sections in `AGENTS.md`

These sections apply to every agent and must be read before the relevant work begins. They are defined in full in `AGENTS.md` — do not duplicate them here, just follow them.

- **Comments & Documentation — All Languages**: Follow the strengthened self-documenting-code rule in `AGENTS.md`. Claude and every other agent must prefer clear names and small functions over explanatory comments. Comments are allowed only for non-obvious reasons, risks, external constraints, fragile invariants, or citations. Comments that merely restate the code are forbidden. Includes a mandatory pre-finish comment check before every commit.
- **Native Runtime Policy**: Before changing native C++, Python fallback, runtime ownership, or operator-facing runtime diagnostics, read `docs/NATIVE_RUNTIME_POLICY.md`.
- **CI and Testing — Mandatory**: Run `git config core.hooksPath .githooks` once. Never use `--no-verify`. Before pushing: backend — `python manage.py test`; frontend — `npm run test:ci && npm run build:prod`.
- **Vibe-Coding Pre-Push Rules (28 automated checks)**: `scripts/lint-all.ps1` runs these automatically. They catch debug artifacts, placeholder stubs, function length, empty catches, hardcoded secrets, N+1 queries, hardcoded styles, and missing test files. Read the full table in `AGENTS.md`.
- **UX and Smart Navigation**: Every `mat-card`, `section`, or major UI block must have a unique `id`. Internal links must use `[routerLink]` with `fragment`. Components must auto-reveal content when a fragment is detected. Use `ScrollHighlightService` for visual feedback. Every error or health warning must include plain-English explanation and actionable fix.
