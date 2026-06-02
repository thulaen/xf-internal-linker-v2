# Code Validation Engine Guide

## Read This First

The Code Validation Engine, shortened to CVE here, is the app's pre-execution
code safety layer. In this repo, CVE means Code Validation Engine, not the
public vulnerability database with the same initials.

The engine checks code before it runs, before it is committed, and before it
passes the master gate. It is not a separate app, a separate dashboard, or a
new issue tracker. It is part of the existing XF Internal Linker app.

The short version:

- the engine lives under the governance module;
- findings appear as AutoIssues;
- high-confidence local failures block through the existing `.githooks` chain;
- uncertain security proof results go to the Review queue;
- the Lua advisor warns agents before they act;
- the React diagnostics page shows health, noisy rule packs, overrides, and
  recent runs;
- K8s, meaning Kubernetes, runs the local distributed subset as Bazel tests;
- AWS, meaning Amazon Web Services, CodeBuild runs the full master-gate suite.

The detailed source-backed spec is
`docs/specs/fr-code-validation-engine.md`. This guide explains the same design
from the operator's point of view.

## What It Is

CVE is a checker for the things the current observability stack cannot see.
Observability means the app's way of seeing what happened: errors, logs,
metrics, traces, and profiles. Those tools are already strong in this repo:
GlitchTip catches runtime errors, Pyroscope shows profiles, Tempo shows traces,
Loki stores logs, VictoriaMetrics stores metrics, SonarQube reports code smells,
and NewRelic reports CI failures.

CVE does not copy any of that. It checks the code before those systems would
ever see it.

Examples:

- an AI agent calls a method that does not exist;
- a Django migration drops a column without a safe backfill;
- a TypeScript interface, Pydantic model, and gRPC contract drift apart;
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

CVE has three main homes.

`apps/governance/code_validation_engine/` is the app-facing home. This is where
the Django models, serializers, REST endpoints, management commands, and
AutoIssue ingestion live. REST means Representational State Transfer, the common
HTTP shape used by web APIs. API means application programming interface: the
callable surface another part of the app can use. Other Python modules talk to
this area through the governance module's `api.py` public surface. A public
surface is the small file that says what another module is allowed to import.

`services/cve/` is the sidecar. A sidecar is a helper process that runs next to
the Django app and handles work better suited to another runtime. CVE's sidecar
is Haskell-led, with C++ kernels, Go worker-pool and transport code, measured
Rust hot paths only when benchmark proof says they are needed, and Lua rule
packs where the existing Lua rules say Lua owns the job.

`/diagnostics/code-validation/` is the planned React diagnostics page from the
Stream F2 rewrite. The current app still has Angular routes, including a
`diagnostics` route, but Plan #13 says new CVE UI work belongs in the React
rewrite. Until that page exists, CVE must still be visible through AutoIssues
and backend diagnostics endpoints.

## How A Local Edit Flows

Here is the normal local path.

1. An agent is about to edit code.
2. The Plan #41 Lua PreToolUse advisor receives the intent. PreToolUse means
   the advisory script runs before the tool call. The Lua rule pack may remind
   the agent that a workflow artifact is missing or that the intended file is
   sensitive. This layer advises only; it does not hard-block.
3. The agent edits the file.
4. The existing `.githooks` chain runs at commit time. CVE adds only 8 to 12
   thin hooks, not a large second hook system.
5. Those hooks call the CVE sidecar or a local rule-pack check.
6. Deterministic hard failures block the commit. Deterministic means the engine
   has enough evidence to say the rule was broken.
7. Uncertain findings become AutoIssues or Review queue items.
8. Every finding also has SARIF output. SARIF is a standard JSON format for
   static analysis results.

The local target is under two seconds for the incremental scan path on the
agent's working-directory diff.

## How Findings Show Up In The App

Every CVE rule pack gets its own AutoIssue source named
`cve_<rule_pack_name>`. A rule pack is a versioned set of checks with a declared
owner, runtime, budget, and lifecycle state.

This matters because noisy checks must be obvious. If `cve_prompt_injection`
creates too many false positives, the operator should see that source getting
noisy instead of seeing one mixed bucket called "validation."

The app integration has two required fixes before broad rollout:

- AutoIssue #2470: the backend AutoIssue source field is currently too short
  and fixed-choice for dynamic `cve_*` sources.
- AutoIssue #2471: the frontend AutoIssues client currently assumes a fixed
  source-name list.

Phase 1 fixes both. After that, CVE findings appear beside GlitchTip, Pyroscope,
Tempo, Loki, Faro, SonarQube, mutation, fuzz, contract, GitHub CI, and agent
findings. The operator does not need a new issue habit.

## What The Diagnostics Page Shows

The React page at `/diagnostics/code-validation/` should be a work surface, not
a brochure.

It shows:

- CVE availability: healthy, degraded, or unavailable;
- latest local runs and latest CodeBuild master-gate runs;
- rule-pack version, signature, lifecycle state, and owner runtime;
- p50, p95, and p99 latency per rule pack. These are the 50th, 95th, and 99th
  percentile timings;
- false-positive rate per rule pack, measured as operator override rate over
  the last 30 days;
- open AutoIssues grouped by `cve_<rule_pack_name>`;
- proof obligations that went to Review. A proof obligation is a small math
  problem the engine asked a solver to prove;
- K8s shard status for CVE Bazel targets;
- override markers and their linked OperatorOverride rows.

If the sidecar is down, the page shows a "CVE unavailable" chip. The pipeline
continues without CVE checks and files an AutoIssue. This follows the existing
Plan #19 error style and the Plan #25 explanation-library pattern.

## What It Checks

CVE checks fourteen gaps that the runtime stack cannot see early enough.

Gap A is pre-execution semantic checks. Semantic means the engine understands
enough code structure to catch meaning-level mistakes, such as missing methods.

Gap B is architectural boundaries. It extends the current module-boundary hook
to catch imports outside `api.py`, layer reversals, and sidecar bypass.

Gap C is breaking contract changes across REST, gRPC, Protocol Buffers,
OpenAPI, Pydantic, Django serializers, and TypeScript interfaces. gRPC is
Google's remote procedure call framework. Protocol Buffers are typed message
schemas often used with gRPC. A contract is the shape one part of the app
promises another part can call or read.

Gap D is database migration safety: drop columns, drop tables, irreversible
alters, missing defaults, missing NOT NULL backfills, and lock-risk patterns.

Gap E is security-critical proof work only. It uses SMT solvers, which are math
tools for proving richer formulas than plain true-or-false logic. Z3 and CVC5
cross-check small proof obligations. If they return UNKNOWN, the engine sends
the item to Review and does not reject the commit.

Gap F is test impact blast radius. Blast radius means the code paths or tests
affected by a change. CVE uses the Plan #36 GraphAnalyzer and Apache AGE graph
queries to decide what tests are invalidated.

Gap G is prompt injection inside comments. Prompt injection means text that
tries to trick an AI agent into ignoring project rules or leaking secrets. CVE
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

If CVE has a known false positive, the operator can override it in the commit
body:

`[CVE OVERRIDE: rule_pack=<name> rule_id=<id> reason="..."]`

The override is logged to OperatorOverride and counted in the rule pack's
30-day false-positive rate. The reason is required because the next agent needs
to understand whether the rule was wrong, the code was unusual, or the operator
accepted a one-time risk.

Overrides are not a way to hide engine failures. If CVE is unavailable, that is
a typed error and an AutoIssue. If the solver returns UNKNOWN, that goes to
Review. If a rule pack crashes, that is a rule-pack error and an AutoIssue.

## How K8s And CodeBuild Fit

Local K8s runs the incremental distributed subset. CVE checks become Bazel test
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
cross-language CVE checks. It must fit inside the 11:00 to 23:00 user-time
window and the Step 5 budget cap. If the CodeBuild budget reaches the 100
percent cap, the full CVE master-gate suite skips and files an AutoIssue. Local
K8s incremental CVE still runs.

## What Happens When It Breaks

CVE is strict about visibility, not about pretending every problem can be
solved locally.

If the sidecar crashes, Python raises `HaskellUnavailableError`, the pipeline
continues without CVE checks, the diagnostics page shows "CVE unavailable," and
an AutoIssue is filed.

If a solver times out or returns UNKNOWN, the change is not rejected. The proof
goes to Review.

If Tree-sitter changes upstream, the pinned version in `MODULE.bazel` protects
the repo. Version bumps need a paper-trail entry and golden-test updates.

If a rule pack causes production noise, it returns to shadow status. Its
override rate stays visible.

If AutoIssue filing fails locally, the existing findings buffer records the
finding and a later drain command files it. In CI, soft filing is not allowed,
so the check fails loudly.

## Implementation Order

The work is intentionally split.

Phase 1 creates the app skeleton, sidecar foundation, AutoIssue dynamic source
support, SARIF output, diagnostics API, and the first 10 high-impact rule packs.

Phase 2 builds the native parsing layer: Tree-sitter bindings, UAST mappers,
and CIR output for the first six implementation languages.

Phase 3 adds blast-radius computation through Apache AGE and GraphAnalyzer.

Phase 4 adds the security-critical proof path with Z3 and CVC5 budgets.

Phase 5 completes the rule-pack lifecycle: signatures, shadow, canary,
production, authoring guide, and override metrics.

Phase 6 expands to about 300 production rules, Docusaurus docs, full AutoIssue
picker integration, and trust dashboard calibration.

The full target is 18 to 24 months, 80 to 150 slices, and 300,000 to 500,000
lines across the locked language ownership matrix. That is large, but it is
app-shaped: every slice must ship a visible part of the product, not a hidden
research pile.
