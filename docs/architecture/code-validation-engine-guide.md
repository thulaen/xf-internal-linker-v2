# Code Validation Engine Guide

> **Plain-English guide.** This page is written for an operator, not a compiler
> engineer. It aims at Flesch Reading Ease 60 or higher and US grade level 8.9 or
> lower, defines every technical term the first time it is used, and uses no
> metaphors (which is why the engine has a literal name). The detailed,
> source-cited spec is `docs/specs/fr-code-validation-engine.md`.
>
> **Two-language note.** The backend is Python plus Rust only (the rule added
> 2026-06-06; see [ADR 0007](../adr/0007-python-rust-two-language.md)). PreGate's
> compute is a Rust extension that Python imports in-process through PyO3, the
> standard Rust-to-Python binding; there is no Haskell, C++, Go, or Lua, and no
> separate sidecar process.

## Read This First

PreGate is the app's pre-execution code-validation layer. It is named for *when*
it runs — before code is accepted. It is unrelated to the public security CVE
database (Common Vulnerabilities and Exposures); it was drafted earlier under the
working name "CVE" and renamed to PreGate to remove that collision.

The engine checks code before it runs, before it is committed, and before it
passes the master gate. It is not a separate app, a separate dashboard, or a
new issue tracker. It is part of the existing XF Internal Linker app.

The short version:

- the engine is Python (orchestration) plus a Rust extension (the hot-path
  engine, imported through PyO3); there is no Haskell, C++, Go, or Lua;
- the engine lives under the governance module;
- findings appear as AutoIssues;
- high-confidence local failures block through the existing `.githooks` chain;
- uncertain security proof results go to the Review queue;
- a Python advisor warns agents before they act;
- the Angular diagnostics page shows health, noisy rule packs, overrides, and
  recent runs;
- K8s, meaning Kubernetes, runs the local distributed subset as Bazel tests;
- AWS, meaning Amazon Web Services, CodeBuild runs the full master-gate suite.

The detailed source-backed spec is
`docs/specs/fr-code-validation-engine.md`. This guide explains the same design
from the operator's point of view.

## What It Is

PreGate is a checker for the things the current observability stack cannot see.
Observability means the app's way of seeing what happened: errors, logs,
metrics, traces, and profiles. Those tools are already strong in this repo:
GlitchTip catches runtime errors, Pyroscope shows profiles, Tempo shows traces,
Loki stores logs, VictoriaMetrics stores metrics, SonarQube reports code smells,
and NewRelic reports CI failures.

PreGate does not copy any of that. It checks the code before those systems would
ever see it.

Examples:

- an AI agent calls a method that does not exist;
- a Django migration drops a column without a safe backfill;
- a Pydantic model, a Django serializer, and a TypeScript interface drift apart;
- a comment contains prompt text trying to trick an AI agent;
- code reads a secret environment variable outside the allowlist;
- a replacement function leaves the old function behind;
- a hot-path edit has no benchmark proof;
- the commit skips the required research, BDD, TDD, review, AutoIssue, or
  handoff evidence.

BDD means behavior-driven description: writing the expected behavior in
Given/When/Then form. TDD means test-driven development: writing or updating the
focused test before or alongside the code and recording the Red-Green-Refactor
cycle.

## Where It Lives

PreGate has two code homes plus its UI page.

`apps/governance/pregate/` is the Python home. This is where the Django models,
serializers, REST endpoints, management commands, and AutoIssue ingestion live.
REST means Representational State Transfer, the common HTTP shape used by web
APIs. API means application programming interface: the callable surface another
part of the app can use. Other Python modules talk to this area through the
governance module's `api.py` public surface. A public surface is the small file
that says what another module is allowed to import.

The Rust extension is the second home. All of PreGate's compute — parsing, the
validators, dedup, the proofs — lives in a Rust crate built through the
Docker-managed maturin path. Python imports it in-process through PyO3, with no
Python fallback. There is no separate sidecar process; the earlier five-language
design (a Haskell/C++/Go/Lua sidecar) is retired under the Python + Rust rule.

`/diagnostics/pregate/` is the PreGate diagnostics page. The app is Angular 22
today — there is no React rewrite on disk, and the locked UI direction is Angular
CDK plus Tailwind (Plan #13's "remove Angular / move to React" framing is
superseded). So the page is an Angular page, built from the shared Angular
components. Until it exists, PreGate must still be visible through AutoIssues and
backend diagnostics endpoints.

## How A Local Edit Flows

Here is the normal local path.

1. An agent is about to edit code.
2. A Python PreToolUse advisor receives the intent. PreToolUse means the
   advisory script runs before the tool call. The advisor may remind the agent
   that a workflow artifact is missing or that the intended file is sensitive.
   This layer advises only; it does not hard-block. (The earlier Lua advisor is
   retired — Lua is a removed language.)
3. The agent edits the file.
4. The existing `.githooks` chain runs at commit time. PreGate adds only 8 to 12
   thin Python hooks, not a large second hook system.
5. Those hooks call the PreGate Rust extension or a local rule-pack check.
6. Deterministic hard failures block the commit. Deterministic means the engine
   has enough evidence to say the rule was broken.
7. Uncertain findings become AutoIssues or Review queue items.
8. Every finding also has SARIF output. SARIF is a standard JSON format for
   static analysis results.

The local target is under two seconds for the incremental scan path on the
agent's working-directory diff.

## How Findings Show Up In The App

Every PreGate rule pack gets its own AutoIssue source named
`pregate_<rule_pack_name>`. A rule pack is a versioned set of checks with a declared
owner, runtime, budget, and lifecycle state.

This matters because noisy checks must be obvious. If `pregate_prompt_injection`
creates too many false positives, the operator should see that source getting
noisy instead of seeing one mixed bucket called "validation."

The app integration has two required fixes before broad rollout:

- AutoIssue #2470: the backend AutoIssue source field is currently too short
  and fixed-choice for dynamic `pregate_*` sources.
- AutoIssue #2471: the frontend AutoIssues client currently assumes a fixed
  source-name list.

Phase 1 fixes both. After that, PreGate findings appear beside GlitchTip, Pyroscope,
Tempo, Loki, Faro, SonarQube, mutation, fuzz, contract, GitHub CI, and agent
findings. The operator does not need a new issue habit.

## What The Diagnostics Page Shows

The Angular page at `/diagnostics/pregate/` should be a work surface, not
a brochure.

It shows:

- PreGate availability: healthy, degraded, or unavailable;
- latest local runs and latest CodeBuild master-gate runs;
- rule-pack version, signature, lifecycle state, and owner runtime;
- p50, p95, and p99 latency per rule pack. These are the 50th, 95th, and 99th
  percentile timings;
- false-positive rate per rule pack, measured as operator override rate over
  the last 30 days;
- open AutoIssues grouped by `pregate_<rule_pack_name>`;
- proof obligations that went to Review. A proof obligation is a small math
  problem the engine asked a solver to prove;
- K8s shard status for PreGate Bazel targets;
- override markers and their linked OperatorOverride rows.

If the Rust extension fails to load, the page shows a "PreGate unavailable" chip.
The pipeline continues without PreGate checks and files an AutoIssue. This follows
the existing Plan #19 error style and the Plan #25 explanation-library pattern.

## What It Checks

PreGate checks fourteen gaps that the runtime stack cannot see early enough.

Gap A is pre-execution semantic checks. Semantic means the engine understands
enough code structure to catch meaning-level mistakes, such as missing methods.

Gap B is architectural boundaries. It extends the current module-boundary hook
to catch imports outside `api.py`, layer reversals, and sidecar bypass.

Gap C is breaking contract changes across REST APIs, OpenAPI schemas, Pydantic
models, Django serializers, and TypeScript interfaces. A contract is the shape
one part of the app promises another part can call or read. (gRPC and Protocol
Buffers are not targets, because `.proto` is a blocked file type under the
Python-plus-Rust rule, so the repo has none.)

Gap D is database migration safety: drop columns, drop tables, irreversible
alters, missing defaults, missing NOT NULL backfills, and lock-risk patterns.

Gap E is security-critical proof work only. It uses SMT solvers, which are math
tools for proving richer formulas than plain true-or-false logic. Z3 and CVC5
cross-check small proof obligations. If they return UNKNOWN, the engine sends
the item to Review and does not reject the commit.

Gap F is test impact blast radius. Blast radius means the code paths or tests
affected by a change. PreGate uses the Plan #36 GraphAnalyzer and Apache AGE graph
queries to decide what tests are invalidated.

Gap G is prompt injection inside comments. Prompt injection means text that
tries to trick an AI agent into ignoring project rules or leaking secrets. PreGate
uses fast multi-pattern search and Unicode confusable detection.

Gap H is hallucinated APIs: invented method or field names that do not exist.

Gap I is unauthorized environment-variable reads outside
`apps/governance/secret_allowlist.py`.

Gap J is cross-language contract drift, such as a backend model and frontend
interface describing different shapes.

Gap K is performance proof for hot-path edits. A hot path is code run often
enough that slowdown matters.

Gap L is dead-code-on-replace. If a new function replaces an old one, the old
one must be deleted in the same commit.

Gap M is workflow phase validation for the seven Plan #41 phases: research,
BDD, TDD, implement, review, AutoIssues, and commit.

Gap N is AI-agent identity drift. This checks that commit trailers and
`AGENT-HANDOFF.md` markers agree about which agent wrote the code.

## The Quality Bar: Test-First Plus Ten Metrics

PreGate does not just check other people's code; it raises a fixed quality bar
for the whole app, and holds itself to the same bar.

The bar starts with test-driven development (TDD): you write a small failing test
first, then the code that makes it pass, then you tidy up. No code ships without a
test written first. "Exhaustively tested" has a precise meaning here — the code
must hit the branch-coverage floor, hit the mutation-score floor, carry a
property-based test where the logic is generative, and cover the five test layers
(edge cases, resource cleanup, speed, smoke, and end-to-end).

On top of that, ten engineering metrics are enforced, each with a hard number and
an automatic block when it is broken:

1. Logical code size — function and file caps, and ELCV (below) for real size.
2. Production execution evidence — code must actually run in production, or it is
   flagged as dead and removed.
3. Cognitive complexity ceiling — no function may be too tangled to read.
4. Code churn isolation — one change should not thrash the whole codebase.
5. Defect density — bugs per unit of real code must stay low.
6. Branch coverage — tests must exercise the decision points.
7. Mutation score — the tests must actually catch deliberately broken code.
8. Module coupling — modules talk only through their public surface.
9. Code duplication — no copy-paste; identical logic counts once.
10. Build and test time — the feedback loop stays fast.

Each number lives in one config file (`config/quality-thresholds.yaml`) so a
change is reviewable and a downgrade is blocked. Breaking a metric blocks the
commit locally, blocks the push in CI, and blocks the release for the running app.
Every metric shows on the Code Quality page. These thresholds are absolute from
day one: when a gate is switched on, the existing code is first cleaned up to pass
it.

## Code Size The Honest Way: ELCV

Counting lines of code is easy to fake — add blank lines, copy a file, paste in
generated scaffolding, and the number rises while nothing real changes. PreGate
refuses to use raw lines as the size measure. It uses Effective Logical Code
Volume (ELCV), which counts only real, executed, distinct logic.

ELCV is built from four parts:

- LEU (Logical Execution Units) — the real decision points (branches, loops,
  state changes). Comments and boilerplate do not count.
- USO (Unique Semantic Operations) — distinct operations after removing
  duplicates, so copy-paste counts once.
- ARW (Active Runtime Coverage Weight) — a 0-to-1 weight that is 1 only if the
  code actually ran in production recently; dead code weighs 0.
- SCW (Structural Complexity Weight) — rewards healthy code and penalizes both
  trivial filler and over-complex code, so you cannot inflate size by writing
  messy code.

The formula is `ELCV = (LEU × ARW × SCW) + USO`, computed automatically in CI.

Five things are explicitly NOT allowed to raise ELCV: duplicated files, generated
boilerplate that never runs, vendored third-party code, formatting changes, and
empty wrapper code. If a commit pushes ELCV up without adding real, unique,
executed logic, the build fails.

The project's 5,000,000 target is expressed in ELCV — a cumulative, deduplicated,
runtime-validated whole-system number, not raw repository size. Progress is
tracked as ELCV growth each release. When ELCV drops because of healthy cleanup
(refactoring, removing duplicates, deleting dead code) that is recorded as good,
not punished; only a drop that loses real distinct operations without a
deprecation note is flagged for a look.

Why is 5 million such a big number? Because ELCV counts only real logic: a
comment, a blank line, a copy-pasted block, or code that never runs adds little or
nothing. So 5 million ELCV is worth far more than 5 million plain lines — it is the
scale of a large software platform. And you cannot fake your way there: duplicates
count once, unrun code counts zero, and messy code is penalized.

Is that doable? Not in one shot — no person and no AI model writes 5 million units
of real logic in a single go, and the plan never asks for that. It is built the
same way as the rest of the engine: as many small, tested slices over a long time.
A capable coding agent (such as the Opus and high-effort Codex agents this project
uses) finishes one slice in a session, the total grows a little each release, and
the quality gates make sure every increment is real. If the app genuinely needs
that much distinct behavior, the slices compound to 5 million over the years; if it
needs less, the number honestly levels off lower — and that is fine, because the
point is real functionality, not a vanity count.

One honest caveat: two of ELCV's four parts — which code actually ran in
production, and de-duplicated code structure — need new measuring tools that are
not built yet. Until those land, the Code Quality page shows ELCV as "pending"
rather than a made-up number. 5 million is a target to build toward, not a score
the app can display today.

## The Code Quality Page

A new page at `/diagnostics/code-quality` (under the SYSTEM menu, beside
Diagnostics) shows all of this in one place: an ELCV gauge with the trend toward
the 5,000,000 target, a tile for each of the ten metrics (pass or fail, the value,
and the threshold), a panel of recently-blocked gaming attempts, a list of dead
code, and a per-module table. Every tile has a plain-English hover that explains
what it means. If the engine is unavailable, the page says so plainly rather than
showing stale numbers.

## A Runtime Sibling: Observatory

PreGate checks code before it runs. Its sibling, **Observatory**, watches the app
*while* it runs and *after* it ships — errors, slow requests, profiles, real-user
experience, alerts, and automatic rollback if a release goes bad. Together, PreGate
and Observatory are called **Aegis** — the umbrella name for the whole code-health
platform. The two are separate but share one screen, one issue list, one "remove
duplicates" rule, and one settings registry. Most of Observatory already exists in
the app today (GlitchTip, Tempo, Pyroscope, Faro, VictoriaMetrics — and the
alerting and synthetic checkers are already built); the work is to put it all in
one tab, wire a few pieces together, and add the missing reliability layers. Its
full plan is in `docs/specs/fr-observatory.md`, and it gets its own sidenav tab
that shows what premium Sentry shows.

## More Checks: Correctness, Security, And How Findings Are Reviewed

PreGate also proves the math is right, not just that the code is tidy:

- A later phase (Phase 4) will add Rust proof tools (Kani, Creusot, Prusti, MIRAI)
  plus the Z3 and CVC5 solvers to prove security-critical and ranking code cannot
  break in specific ways. These tools are not installed yet, so this is a planned
  capability, not a current one. They prove things about the Rust hot paths only —
  the Python orchestration is checked by tests and lints, not proofs. Creusot and
  Prusti need a written contract on each function and can return "unknown" or time
  out on real code, which is why an unknown result goes to Review instead of
  blocking. (Lean 4 was asked for, but it does not run in Rust; these are the real
  Rust equivalents.)
- It keeps the business math at full 64-bit precision, bans risky float
  comparisons, and requires ranking to be reproducible.
- It runs security checks: secret detection, dependency-vulnerability scans, a
  bill of materials, license rules, and signed builds.

And findings are never blindly accepted. When PreGate or Observatory files an
issue it lands as "proposed." An agent then either approves and fixes it, rejects
it with a reason, or — when PreGate is wrong — corrects PreGate's own rule. A rule
that cries wolf too often is automatically demoted until it is fixed. Ten issue
slots are reserved just for improving the engine itself, and PreGate keeps its own
fast database so agents can check that it is not making mistakes.

## How Rule Packs Move To Production

Rule packs follow the existing Plan #18 lifecycle.

Shadow mode means the rule runs but does not affect decisions. Canary mode means
the rule affects a small controlled path. Production mode means the rule can
warn, review, or hard-block according to its decision policy.

Each pack must spend 24 hours in shadow and 24 hours in canary before
production. If it misbehaves, it returns to shadow status. It is not silently
deleted because the operator needs to see what happened.

Each pack declares:

- source name;
- version;
- signature;
- owner runtime;
- budget tier;
- local or CodeBuild eligibility;
- AutoIssue category;
- SARIF rule id;
- override policy;
- citations for named algorithms or data structures.

## How Overrides Work

If PreGate has a known false positive, the operator can override it in the commit
body:

`[PREGATE OVERRIDE: rule_pack=<name> rule_id=<id> reason="..."]`

The override is logged to OperatorOverride and counted in the rule pack's
30-day false-positive rate. The reason is required because the next agent needs
to understand whether the rule was wrong, the code was unusual, or the operator
accepted a one-time risk.

Overrides are not a way to hide engine failures. If PreGate is unavailable, that is
a typed error and an AutoIssue. If the solver returns UNKNOWN, that goes to
Review. If a rule pack crashes, that is a rule-pack error and an AutoIssue.

## How K8s And CodeBuild Fit

Local K8s runs the incremental distributed subset. PreGate checks become Bazel test
targets. Bazel is the build and test runner used by the K8s plan.

The K8s path reuses:

- the source snapshot from K8S.17, which captures tracked, staged, unstaged, and
  untracked files;
- the coverage adapters from K8S.18;
- the mutation adapters from K8S.19;
- the shard formula from K8S.20;
- the coordinator preflight gates from K8S.21;
- the shard job wrapper from K8S.22;
- the final merge job from K8S.23.

AWS CodeBuild runs the full master-gate suite: mutation, coverage, and the
cross-language PreGate checks. It must fit inside the 11:00 to 23:00 user-time
window and the Step 5 budget cap. If the CodeBuild budget reaches the 100
percent cap, the full PreGate master-gate suite skips and files an AutoIssue. Local
K8s incremental PreGate still runs.

## What Happens When It Breaks

PreGate is strict about visibility, not about pretending every problem can be
solved locally.

If the Rust extension fails to load or errors, Python raises
`RustUnavailableError`, the pipeline continues without PreGate checks, the
diagnostics page shows "PreGate unavailable," and an AutoIssue is filed.

If a solver times out or returns UNKNOWN, the change is not rejected. The proof
goes to Review.

If Tree-sitter changes upstream, the `tree-sitter` crate version pinned in
`Cargo.toml` protects the repo. Version bumps need a paper-trail entry and
snapshot-test updates.

If a rule pack causes production noise, it returns to shadow status. Its
override rate stays visible.

If AutoIssue filing fails locally, the existing findings buffer records the
finding and a later drain command files it. In CI, soft filing is not allowed,
so the check fails loudly.

## Implementation Order

The work is intentionally split.

Phase 1 creates the app skeleton, the Rust PyO3 extension foundation, AutoIssue
dynamic source support, SARIF output, the diagnostics API, and the first 10
high-impact rule packs.

Phase 2 builds the native parsing layer in Rust: Tree-sitter parsing through the
Rust `tree-sitter` crate, UAST mappers, and CIR output for the repo's languages
(Python, Rust, TypeScript, JavaScript).

Phase 3 adds blast-radius computation through Apache AGE and GraphAnalyzer.

Phase 4 adds the security-critical proof path with Z3 and CVC5 budgets.

Phase 5 completes the rule-pack lifecycle: signatures, shadow, canary,
production, authoring guide, and override metrics.

Phase 6 expands to about 300 production rules, Docusaurus docs, full AutoIssue
picker integration, and trust dashboard calibration.

The full target is 18 to 24 months, 80 to 150 slices, and a minimum of
**5,000,000 ELCV** (Effective Logical Code Volume — real, deduplicated, executed
logic, never raw lines) across the two locked backend languages, Python and Rust.
That is large, but it is app-shaped: every slice must ship a visible part of the
product, not a hidden research pile.
