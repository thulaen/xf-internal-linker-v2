# FR - Code Validation Engine

[SPEC FRESHNESS: reviewed_at=2026-06-13 next_review=2026-07-13]

## 1. Summary

PreGate is the pre-execution code-validation engine for the XF Internal Linker
app. It is named for *when* it runs: before code is accepted. PreGate is
unrelated to the public security CVE database (Common Vulnerabilities and
Exposures). This engine was drafted earlier under the working name "CVE" and was
renamed to PreGate to remove that collision and to satisfy the no-metaphor rule
in PLAIN-ENGLISH-RULE.md, which wants literal names rather than figures of
speech. It checks code changes before they run, before they are committed, and
before they reach the master gate. It is not a replacement for GlitchTip,
Pyroscope, Tempo, Loki, VictoriaMetrics, SonarQube, NewRelic, or any other
existing runtime or quality surface. It fills the gaps those systems cannot see,
because those systems mostly report what happened after code ran. PreGate and its runtime sibling
**Observatory** (`docs/specs/fr-observatory.md`) are the two halves of **Aegis**,
the umbrella code-health platform — a protective shield over every code change:
PreGate guards the gate before code runs, Observatory watches while it runs and
after it ships. The two are separate specs that share the GUI shell, the
AutoIssue pipe, the one deduplication path, and the capability registry.

This spec replaces the older draft at
`C:\Users\goldm\OneDrive\Pictures\Deterministic_Validation_Engine_Plan.md`.
The old draft aimed at an oversized single-language monolith and a tiny legacy
hardware target. That framing is rejected. The minimum size target is **5,000,000 ELCV**
(Effective Logical Code Volume, Section 19 — a non-gamable measure of real,
deduplicated, executed logic, never raw lines), built in the repo's two locked
backend languages, **Python and Rust** (the ABSOLUTE Python-plus-Rust-only rule
added 2026-06-06;
C, C++, Go, Haskell, and Lua are removed and hard-blocked by
`.githooks/check-removed-languages.py`). Rust owns the hot-path compute as an
in-process PyO3/maturin extension; Python orchestrates. The earlier six-language
plans (#26 Haskell, #28 Haskell/C++, #36 C++, #40 Lua, #42 C ABI, #23 Go) are
superseded and used for ideas only. The engine is built over 18 to 24 months in
six phases and 80 to 150 shippable slices.

The most important design choice is tight app integration. PreGate is not a side
tool that agents run when they remember it. It is part of the governance module,
the AutoIssue work queue, the paper-trail evidence chain, the existing hook
chain, a Python pre-commit advisor layer, the app's Angular diagnostics route (the app
is Angular 22 today — there is no React rewrite on disk; the locked UI direction
is Angular CDK plus Tailwind), the planned K8s Bazel sharding, and the AWS
CodeBuild master gate. Every
finding is visible in the app, deduped through AutoIssues, exported as SARIF,
and attached to the same operator override and lesson flow that the rest of the
  project already uses. K8s means Kubernetes, the local distributed test
  cluster used by the project. AWS means Amazon Web Services, and CodeBuild is
  its managed build runner.

Two app-integration problems were found while writing this spec and were filed
as AutoIssues, as required by the repo rules:

- AutoIssue #2470: `backend/apps/auto_issues/models.py` stores `source` as
  `models.CharField(max_length=16, choices=SOURCE_CHOICES, db_index=True)`
  (verified at line 148). The 25 current sources all fit in 16 characters
  (longest is `pytest_failure`, 14 characters), and the field is a fixed
  enum with no dynamic registration. PreGate needs dynamic sources shaped as
  `pregate_<rule_pack_name>`, which both overflow 16 characters and need
  registry-backed registration.
- AutoIssue #2471: `frontend/src/app/core/services/auto-issues.service.ts`
  types `source` as the fixed union `'glitchtip' | 'pyroscope' | 'agent'` (only
  three values, already narrower than the 25 backend sources — a pre-existing
  mismatch). PreGate needs the app client to treat `source` as a registry value,
  which also fixes that mismatch.

Those issues are not side notes. As of this spec's date both are still open
(verified this session); Phase 1 slice PG.01 resolves them before any broad
PreGate ingestion, so PreGate findings become first-class app data.

## 2. Plain-English Terms

This table defines the advanced terms before the spec uses them. The guide at
`docs/architecture/code-validation-engine-guide.md` repeats the smaller set
needed by non-specialist readers.

| Term | Plain-English meaning |
|---|---|
| Galois connection | A mathematical pattern that lets us safely approximate a complicated state with a simpler one. PreGate uses it only in abstract interpretation proofs. |
| Chaotic iteration | Repeatedly running an analysis pass until no new information is learned. PreGate uses a bounded form and stops at the budget. |
| Hoare triple | A before-during-after specification for a code block. PreGate uses it only for security-critical proof obligations. |
| Datalog clause | A small if-then rule that looks like "if A and B and C then conclude D." PreGate uses it only when reachability queries across the call graph cannot be expressed by existing rule packs. |
| Semilattice | A set of values where any two can be combined to a third in a predictable way. PreGate uses it inside abstract interpretation. |
| Roaring bitmap | A compressed bit-array format that makes large set operations fast. PreGate uses it for changed-file and affected-test sets. |
| Arena allocation | A memory area you allocate into and free all at once. PreGate's Rust extension may use it as a speed optimization for a whole run's nodes, not as a correctness requirement. |
| MinHash | A fast way to estimate how similar two big sets are. PreGate uses it for near-duplicate code and comment corpora. |
| LSH, or Locality-Sensitive Hashing | A hash family that puts similar inputs into the same bucket on purpose. PreGate uses it with MinHash for fast similarity search. |
| PyO3 / maturin | PyO3 is the standard Rust-to-Python binding; maturin builds a Rust crate into a Python extension module. PreGate crosses from Python into its Rust compute through PyO3, in-process, with no hand-written C boundary and no separate service. |
| SMT, or Satisfiability Modulo Theories | Automated math solving over richer types than plain true-or-false logic. PreGate uses SMT only for security-critical proof obligations. |
| UAST, or Unified Abstract Syntax Tree | One tree shape that can represent code from many languages. PreGate builds UAST nodes from Tree-sitter parse trees. |
| CIR, or Compact Intermediate Representation | A memory-efficient form of the UAST used for analysis. PreGate uses CIR in native kernels so Python never owns the hot path. |
| Dominator | Node A dominates node B if every path to B goes through A first. PreGate uses dominators to prove authentication checks happen before sensitive operations. |
| SCC, or Strongly Connected Component | A group of nodes where every node can reach every other node. PreGate uses SCCs to summarize cyclic call graphs. |
| Confusable or homoglyph | Characters that look the same but are different code points, for example Latin `a` versus Cyrillic `a`. PreGate uses Unicode TR39 confusable detection for prompt-injection checks. |
| Taint flow | Tracking which values are influenced by untrusted input through the program. PreGate uses it for security-critical paths only. |
| Proof obligation | A small math problem the engine generates and asks an SMT solver to prove. PreGate sends proof obligations to Z3 and CVC5 within a time budget. |
| Aho-Corasick | A fast multi-pattern string search algorithm. PreGate uses it to scan comments against a known prompt-injection phrase corpus. |
| Tree-sitter | An open-source library that produces concrete syntax trees for many programming languages. PreGate uses its C parsers as the language parsing layer. |
| SARIF | A standard JSON format for static analysis findings. PreGate exports every finding as SARIF v2.1.0. |
| Blast radius | The set of code paths or tests affected by a given change. PreGate computes this with the Plan #36 GraphAnalyzer and Apache AGE. |
| Equivalent mutant | A code mutation that does not change observable behavior, so tests cannot catch it. PreGate treats this as an allowed quarantine case, not as a test failure. |
| Property-based testing, or PBT | Testing a rule by generating many varied inputs automatically, instead of hand-picking a few. The repo runs a hard pre-commit PBT gate. |
| Hypothesis | The Python property-based-testing library. PreGate's Python kernels ship Hypothesis tests that run under the repo PBT gate. |
| proptest | The Rust property-based-testing library. PreGate's Rust kernels ship proptest cases run through `cargo nextest`. |
| nextest | A faster Rust test runner the repo uses instead of bare `cargo test`. |
| Vitest | The frontend unit-test runner the repo migrated to (it replaced Karma). Stryker mutation drives it through a command runner. |
| oxlint | A fast Rust-based JavaScript and TypeScript linter that runs before eslint as a quick correctness filter. |
| ruff | The Python linter and formatter the repo uses (it replaced pylint), configured to enable all rules by default. |
| Prometheus exposition | A `/metrics/` HTTP endpoint that publishes counters and timers in Prometheus format. The repo scrapes it through the OpenTelemetry collector into Grafana. |
| Ratchet | A baseline that can only rise. The mutation-score ratchet records the best score per target and fails any commit that drops below it. |
| backend-quality container | The Docker image that holds the Python quality tools (ruff, mypy, bandit, pytest, mutmut, coverage). The runtime `backend` image deliberately does not have them. |
| ADBC | Arrow Database Connectivity: a way to read database rows as Arrow columns directly. The repo uses it for fast analytics exports; PreGate does not depend on it. |
| ELCV, or Effective Logical Code Volume | A non-gamable measure of how much real, executed, distinct logic the system contains. It replaces counting raw lines, which are easy to fake. Defined in Section 19. |
| LEU, or Logical Execution Units | The count of meaningful decision points in code — branches, loops, state changes, function decision boundaries. Comments, blank lines, and boilerplate do not count. One of the four ELCV inputs. |
| USO, or Unique Semantic Operations | The count of distinct operations after removing duplicates: two code paths that do the same thing count once. Stops duplication from inflating size. One of the four ELCV inputs. |
| ARW, or Active Runtime Coverage Weight | A 0-to-1 weight that is 1 only if the code actually ran in production within a set time window. Dead or unrun code weighs 0. One of the four ELCV inputs. |
| SCW, or Structural Complexity Weight | A multiplier that rewards healthy, readable logic and penalizes both trivial filler and over-complex code, so complexity cannot be used to inflate size. One of the four ELCV inputs. |
| Cyclomatic complexity | A count of the independent paths through a function — more branches means a higher number. PreGate caps it at 10 per function. |
| Cognitive complexity | A readability-weighted complexity score that punishes deep nesting and tangled flow more than plain branching. PreGate caps it at 15 per function. |
| Efferent coupling (fan-out) | How many other modules a module depends on. High fan-out means fragile, tangled code. PreGate caps it per module. |
| Defect density | The number of real defects (errors, blocker findings, open bugs) per 1,000 units of ELCV. A size-aware way to measure quality, not a raw bug count. |
| Code churn | How often a file or area changes over time. High-churn files are riskier and get extra test and review requirements. |
| Build and test time budget | A hard limit on how long the build and test steps may take, so the feedback loop stays fast. |
| Formal verification | Using math to prove code always holds a property (e.g. "this array index is never out of bounds"), instead of only testing examples. |
| Kani | A tool that checks Rust code for a property across all inputs within a bound (a bounded model checker). |
| Creusot / Prusti | Tools that prove a Rust function meets a written before/after contract (deductive verification). |
| MIRAI | A tool that reasons about all possible Rust program states to find taint and panics (abstract interpretation). |
| ULP | "Unit in the last place" — the tiny gap between two nearby floating-point numbers; used as the tolerance when comparing f64 values instead of `==`. |
| Kahan summation | A way to add many floating-point numbers that cancels rounding error, so a score total stays accurate. |
| Determinism | Same inputs always produce the same output, bit-for-bit — required so ranking is reproducible. |
| Label / target leakage | When a ranking feature accidentally contains the answer it is supposed to predict, making results look better than they are. |
| N+1 query | A bug where code runs one database query per row instead of one query for all rows — slow and avoidable. |
| SAST | Static Application Security Testing — finding security bugs by reading code before it runs. |
| SBOM | Software Bill of Materials — a list of every dependency a build contains. |
| Supply-chain provenance | Proof of where a built artifact came from (signed, reproducible, pinned), so a tampered dependency is caught. |
| Ed25519 | A fast, modern digital-signature algorithm. PreGate signs each rule pack with it so an unsigned or tampered pack is refused before it loads. |
| Capability registry | One small set of governance-owned tables that lists every dynamic source, metric, threshold, rule pack, and helper, so none of them is a hardcoded list. |

## 3. Vision And Non-Goals

### 3.1 Vision

PreGate answers one question: "Before this code runs, can we prove it respects the
rules this app already depends on?"

The engine must:

- catch pre-execution semantic problems that the runtime stack cannot catch;
- turn every finding into an AutoIssue row or an operator-visible review item;
- run locally on the agent's working-directory diff in under two seconds for
  the incremental path;
- run the full master-gate suite in AWS CodeBuild in under 15 minutes inside
  the 11:00 to 23:00 user-time window from Plan #32;
- reuse the existing hook, Python pre-commit advisor, AutoIssue, observability,
  planned K8s and Bazel, CodeBuild, governance, and diagnostics surfaces;
- keep Python as orchestration only, never as the compute fallback for PreGate
  analysis;
- keep security-critical proof work narrow, budgeted, and reviewable.

### 3.2 Non-Goals

PreGate does not replace:

- GlitchTip runtime error capture;
- Pyroscope profiles;
- Tempo traces;
- Loki logs;
- VictoriaMetrics metrics and alerts;
- SonarQube code-smell scanning;
- NewRelic CI failure reporting;
- the existing 47-plus `.githooks/*.py` hard-block hooks;
- the existing pre-commit advisor path;
- the AutoIssue and paper-trail system.

PreGate also does not introduce:

- filesystem interception through FUSE, Dokany, or another file-system layer;
- a bespoke diff parser;
- a bespoke cluster protocol;
- a new event bus;
- a GPU path;
- a Celery dependency;
- a new Angular UI;
- a second observability stack;
- direct cross-module imports that bypass `api.py`;
- a native boundary that violates Plan #42.

## 4. Locked Plan Alignment

This table is deliberately long. The engine is allowed only if it fits all
locked plan decisions, not just the ones that are convenient.

| Plan | Lock title | PreGate alignment |
|---|---|---|
| Plan #1 | pgvector plus Apache AGE local graph projection | PreGate uses Apache AGE for graph-backed blast-radius queries and does not create a second graph store. |
| Plan #2 | Corrected OPQ design | PreGate does not add embedding quantization work; similarity needs use existing embedding and dedup layers. |
| Plan #3 | Reliability pass | PreGate routes unknown or unavailable states into typed errors and AutoIssues instead of silent decisions. |
| Plan #4 | Performance and capability roadmap | PreGate treats performance proof as a first-class check and respects hot-path budget rules. |
| Plan #5 | Copy-paste plan | PreGate enforces dead-code-on-replace and duplicate-artifact rules so copied replacements do not leave stale code. |
| Plan #6 | Forward-looking architecture backbone | PreGate stays inside the modular monolith and the Python-plus-Rust extension model rather than inventing a separate platform. |
| Plan #7 | Programmatic registries plus GUI | PreGate adds rule-pack registry entries and app-visible status, not loose files hidden from the operator. |
| Plan #8 | NewRelic plus AutoIssues repair intake | PreGate findings join AutoIssues; NewRelic continues to own CI failure intake. |
| Plan #9 | Modular Monolith doctrine | PreGate lives under `apps/governance/pregate/` and uses the governance public boundary. |
| Plan #10 | PaperTrail enrichments | PreGate rule changes, overrides, and promotion decisions cite paper-trail entries where the existing rule requires one. |
| Plan #11 | Modular Monolith refactor | PreGate uses `api.py` for module boundaries and extends the existing boundary checker. |
| Plan #12 | Coverage hardening and lesson registry | PreGate consumes coverage thresholds and logs lessons through AutoIssues. |
| Plan #13 | Frontend rewrite | Superseded on the "remove Angular / move to React" point: the app is Angular 22 today and the locked direction is Angular CDK plus Tailwind (no React rewrite exists on disk). PreGate UI is an Angular page at `/diagnostics/pregate/`, built from the shared Angular components, not a new framework. |
| Plan #14 | UI and UX design spec | PreGate UI is a dense diagnostics tool with filters, chips, and drill-ins, not a marketing page. |
| Plan #15 | Ranking weights and autotuner | PreGate does not change ranking weights; it can validate that weight changes cite performance proof. |
| Plan #16 | Testing Tools Dashboard | PreGate run summaries and failing rule packs feed the testing dashboard when that stream owns the UI. |
| Plan #17 | Vibe-coding controls, Review queue, Docs Freshness, and new navigation | PreGate sends solver UNKNOWN and ambiguous findings to the Review queue; docs ship as Docusaurus pages. |
| Plan #18 | rulesd WebAssembly rules and lifecycle | Superseded as a Go/WebAssembly service (Go and Lua are removed). PreGate keeps only the lifecycle concept — shadow, canary, production, rollback to shadow — implemented in Python plus Rust. |
| Plan #19 | Compiled-runtime ownership and zero Python compute fallback | PreGate hot-path compute runs in Rust through PyO3/maturin, authoritative with no Python fallback; Python orchestrates only. |
| Plan #20 | Errors page UI | PreGate typed errors appear in the existing error surfaces through GlitchTip and the app diagnostics route. |
| Plan #21 | Prevention-focused cleanup and quality bar | PreGate itself must pass mutation, coverage, hooks, and clean-working-tree requirements before production promotion. |
| Plan #22 | Embedding System | PreGate does not introduce a new embedding store; near-duplicate needs reuse Plan #36 and Plan #33 lineage. |
| Plan #23 | Strategic Go expansion | Superseded: Go is a removed language. PreGate concurrency lives in Rust (for example rayon) inside the PyO3 extension. |
| Plan #24 | UI feature catalog and trust calibration | PreGate exposes false-positive rate, override rate, and rule-pack confidence in the trust dashboard. |
| Plan #25 | Hardware baseline and helper offload | PreGate targets the Dell 3070 SFF i5-9500, 16 GB DDR4, and 1 TB SSD hardware lock, with no local GPU path. |
| Plan #26 | Haskell STM coordination service | Superseded: Haskell is removed. PreGate uses Rust equivalents — proptest for properties, insta for snapshots, and loom for concurrency. |
| Plan #27 | Modular Monolith hardening | PreGate strengthens architectural fitness checks rather than weakening module boundaries. |
| Plan #28 | Anchor Text Commander Haskell plus C++ FFI | Superseded: Haskell and C++ are removed. PreGate's native ownership is Rust, crossing into Python through PyO3 rather than a hand-written C boundary. |
| Plan #29 | Hot-path extraction critique | PreGate requires benchmark proof for hot-path edits and validates macrobenchmark evidence for hot-path gap #34. |
| Plan #30 | Location and mobile linking | PreGate does not alter location or mobile linking, but it can validate contract drift on those APIs. |
| Plan #31 | NewRelic Error Inbox and Link Intelligence Console | PreGate does not duplicate NewRelic; CI failures remain there and in `source="gh_ci"` AutoIssues. |
| Plan #32 | ML/scoring layer and CodeBuild window | PreGate master-gate runs only within the 11:00 to 23:00 user-time CodeBuild window and respects the budget cap. |
| Plan #33 | AutoIssues enterprise evolution and 256 MB cap | PreGate is a consumer of the AutoIssues subsystem and must stay inside the 256 MB AutoIssues cap. |
| Plan #34 | Sidecar directives: gRPC over Unix-domain socket | Superseded for PreGate: there is no gRPC sidecar. PreGate is an in-process Rust PyO3 extension; the gRPC-over-socket directive applies only to surviving standalone services. |
| Plan #35 | Scoped fail-fast validation | PreGate fast local checks fail fast only on deterministic hard blockers; review-class findings route to Review. |
| Plan #36 | Five dynamic C++ libraries | Superseded: those were C++ libraries. PreGate implements its dedup and graph kernels in Rust and reuses any Rust crate the repo already ships rather than duplicating one. |
| Plan #37 | Sticky-document governance | PreGate emits the required OpenTelemetry span attributes; trace context crosses the in-process PyO3 call, not a gRPC boundary. |
| Plan #38 | Memory-bounded C++ library techniques | The memory-bounding ideas carry over to Rust: PreGate's native subsystem stays under the 128 MB worker-process envelope and uses bounded structures. |
| Plan #39 | TDD and modular architecture ideas | PreGate ships each slice with behavior-first tests and clear module boundaries. |
| Plan #40 | Lua ownership and sandbox refinement | Superseded: Lua is removed. PreGate rule packs are Rust modules plus Python config; signature verification and the shadow/canary lifecycle are kept. |
| Plan #41 | Lua cross-agent workflow advisory layer | Superseded as a Lua layer: PreGate's PreToolUse and commit-time phase advisories run in Python, not Lua. |
| Plan #42 | C ABI Wrapper Standard | Superseded for PreGate: PyO3/maturin is the Python-to-Rust boundary and replaces the hand-written C ABI; no ctypes, cgo, or Haskell FFI. |
| K8S.01-K8S.25 | K8s plus Bazel distributed test foundation | PreGate adds Bazel test targets that use the source-snapshot protocol, sharding formula, coverage adapters, mutation adapters, and final merge job. |

### 4.1 Current Repo Baseline: Present Vs Planned

The locked plans above are real, agreed decisions. Most are not built yet. This
section states plainly what exists on disk today (verified this session) so the
reader never confuses "planned" with "present." PreGate is designed to run today
through the existing tools and to grow into the planned ones as they land.

Present today (verified):

- the only service in `services/` is `services/speccheck/`; none of Sentinel,
  xfstm, ATC, xfgeo, rulesd, bullboard, snapshotd, or RealtimeLinker exist yet;
- there is no `apps/governance/` module yet (30 other `apps/` modules exist);
- there is no Bazel setup (`MODULE.bazel`, `.bazelrc`, `WORKSPACE` are absent);
- there is no K8s cluster checkout on disk;
- the AutoIssue `source` field is still 16-character fixed-choice (AutoIssue
  #2470 open); the frontend source union is still three values (AutoIssue #2471
  open);
- the live quality stack that PreGate runs through today is the Docker
  quality-runner Bazel targets (`//tools/quality:python`,
  `//tools/quality:frontend`, `//tools/quality:rust`,
  `//tools/quality:pbt`) plus the 40-plus `.githooks/check-*.py` chain driven by
  `scripts/precommit-docker.sh`.

Planned but not yet built (from the locked plans): the governance module, the
Rust PyO3/maturin extension build path, Bazel plus the K8s distributed-test
foundation, and the nine-module database split.

Consequence for PreGate:

- Phase 1 slice PG.02 **creates** `apps/governance/pregate/` (Python), and PG.03
  **creates** the Rust PyO3/maturin extension scaffold. PreGate does not assume
  either exists.
- Until Bazel and K8s land, PreGate runs through the existing Docker quality
  scripts and the `.githooks` chain. The Bazel and K8s execution path in
  Section 10.2 is the target once that stream ships, not a current dependency.
- PreGate is an in-process Rust extension, not a separate sidecar (see
  Section 6.2). The earlier six-language plans placed it in a Haskell sidecar
  tier; that tier is superseded by the 2026-06-06 Python-plus-Rust rule, so the
  only languages PreGate adds are Python and Rust.
- Every dependency on an unbuilt stream is marked "planned" where it appears, so
  no slice silently assumes infrastructure that is not there.

## 5. Size, Runtime, And Hardware Envelope

### 5.1 Code Size — Measured As ELCV

The minimum size target is **5,000,000 ELCV** (Effective Logical Code Volume,
Section 19) across the whole system. Raw lines of code are explicitly disallowed
as the size metric (they are trivially gamed); ELCV counts only real,
deduplicated, runtime-validated, complexity-weighted logic. Because ELCV is much
smaller than raw line count, 5,000,000 ELCV is a deliberately large, long-horizon,
cumulative, whole-system minimum, tracked by ELCV growth per release cycle
(Section 19.4) with no artificial deadline, built over many phases in the two
locked backend languages, Python and Rust. PreGate's own engine is one component
of that whole-system total, not the target itself. Section 19.5 explains why
5,000,000 ELCV is aggressive and why it is reached in slices, not one-shot.

The split below is by ownership of the logic, not a raw-line cap:

| Runtime | Share of system ELCV | Ownership |
|---|---:|---|
| Rust | majority | All hot-path compute, built as a PyO3/maturin extension that Python imports in-process: Tree-sitter parsing via the Rust `tree-sitter` crate [TREE_SITTER], UAST and CIR building, the rule kernel and decision algorithm, the validators, the Aho-Corasick scanner, Myers bit-parallel edit distance, dedup, dominator and SCC analysis, and SMT-obligation generation. SIMD uses Rust's portable SIMD where it helps. Authoritative, with no Python fallback (failure raises a typed `RustUnavailableError`). Runs clippy, cargo nextest, and cargo-mutants through Docker-managed tooling [CLIPPY] [NEXTEST] [CARGO_MUTANTS]. |
| Python | minority | Orchestration only: Django models, REST API, management commands, app integration, AutoIssue and SARIF ingestion, diagnostics, rule-pack configuration, and the PyO3 calls into the Rust extension. Lives under `apps/governance/pregate/`. |
| Frontend (TypeScript) | small | The diagnostics and Code Quality surfaces; contributes its own ELCV but is governed by the frontend coverage and mutation gates, not the backend two-language rule. |

### 5.2 Memory And Latency

The old tiny-memory target is removed. PreGate uses the locked caps already in the
project:

- native subsystem cap inside the Django worker process: 128 MB from Plan #38;
- AutoIssues subsystem cap: 256 MB from Plan #33, with PreGate as one consumer;
- Pyroscope profile cap: 100 MB from Plan #25 G-194;
- local incremental PreGate scan: under two seconds on the agent's working-directory
  diff, matching the Plan #41 PreToolUse budget;
- full master-gate PreGate suite: under 15 minutes on AWS CodeBuild inside the
  11:00 to 23:00 user-time window from Plan #32.

The hardware baseline is the Plan #25 Dell 3070 SFF with an i5-9500 CPU, 16 GB
DDR4 memory, and a 1 TB SSD. PreGate must not assume a GPU path. Hardware-aware
settings must still read the existing hardware-profile rules rather than
hardcoding parallelism.

### 5.3 Rule Budgets

Each rule pack declares a tier:

- fast rules: AST-only or simple text checks, median 200 microseconds per
  changed file;
- medium rules: cross-file scope or symbol checks, median 50 milliseconds per
  changed patch;
- heavy rules: SMT proof obligations, one second locally and 30 seconds in
  CodeBuild.

Local mode runs fast rules, selected medium rules, and bounded heavy checks for
security-critical edits only. CodeBuild runs the full cross-language suite.

## 6. App-Integrated Architecture

### 6.1 Placement

PreGate has two repo homes:

- `apps/governance/pregate/` for the app-facing governance module (Python). This
  is where Django-facing models, serializers, API functions, management commands,
  and orchestration live.
- a Rust extension crate, built through the Docker-managed maturin path, for all
  hot-path compute. Python imports it in-process through PyO3. There is no
  separate sidecar process, no gRPC, and no hand-written C boundary — PyO3 is the
  boundary. Any dedup or graph kernel PreGate needs is a Rust module here, reusing
  an existing repo Rust crate when one already covers the job.

The governance module exposes only `apps.governance.api` to other Python
modules. PreGate implementation files are private. Cross-module imports use the
`api.py` public surface from ADR 0002. Cross-module database foreign keys remain
allowed under ADR 0003, but Python imports do not bypass `api.py`.

**Module ownership and the read-as-text rule (boundary contract).** Three rules
remove the apparent conflict between "PreGate lives in governance (Layer 3)" and
"PreGate must inspect code in every module":

1. Governance owns PreGate end to end — its models, rule packs, findings, the ELCV
   and quality computation, and the diagnostics and Code Quality API all live under
   `apps/governance/pregate/`.
2. PreGate reads other modules as files and parse trees (text and AST), never by
   importing them as Python. Reading a file off disk is not a cross-module import,
   so Gaps A, B, H, and J analyze Layer 1 and Layer 2 code without violating the
   downward-only import rule.
3. When PreGate must call another module's runtime code — the benchmark
   `regression_gate.py` in the `benchmarks` module (Gap K) or the GraphAnalyzer in
   the `graph` module (Gap F) — it calls that module's `api.py`. Governance is
   Layer 3, so importing a Layer 2 module's public surface is a legal downward
   import. Those `api.py` surfaces do not all exist yet; the slice that needs each
   one (PG.15 for `benchmarks`, the blast-radius slice for `graph`) adds the public
   surface in the same change.

PreGate's Prometheus gauges register into the shared, process-global
`prometheus-client` registry (the same registry the four existing `metrics_*`
modules use). Registering a gauge is a call into the `prometheus-client` library,
not a cross-module Python import, so the values are emitted from governance and
still scraped by the `/metrics/` endpoint the observability module already exposes
— no Layer 2 module imports Layer 3.

One sequencing note: the nine-module map and the `api.py` convention are still
conceptual (no module ships an `api.py` yet — see Section 4.1). PreGate's PG.02 is
therefore the deliberate first adopter of the `api.py` shape and pulls the
governance public surface forward. This is a stated decision, not an accident, so a
later modular-monolith slice does not assume governance was built last.

### 6.2 Extension Shape

PreGate is not a separate sidecar. It is an in-process Rust extension that Python
imports through PyO3, built through the Docker-managed maturin path [PYO3]
[MATURIN]. The earlier six-language plans placed it in a Haskell-led gRPC sidecar
tier; the 2026-06-06 Python-plus-Rust rule supersedes that, so there is no
Haskell, C++, Go, or Lua, no gRPC socket, and no hand-written C ABI.

Rust owns the compute: the rule kernel, the decision algorithm, parsing through
the `tree-sitter` crate, UAST and CIR building, the validators, proof-obligation
generation, and result normalization. Rust is authoritative and has no Python
fallback. If the extension fails to load or errors, Python raises a typed
`RustUnavailableError` and the pipeline continues without PreGate checks.

Python owns orchestration only: collecting the changed files, calling the Rust
extension, validating the returned shape, persisting findings, filing AutoIssues,
writing SARIF, and exposing the diagnostics API. The PyO3 boundary carries typed
Rust results into Python; Python never re-implements or second-guesses the Rust
compute.

Phase 1 creates or amends ADR 0007 to record that PreGate is a Rust PyO3
extension under the Python-plus-Rust rule, not a sidecar.

### 6.3 Data Model

Phase 1 adds a narrow governance-owned data model. API means application
programming interface: the callable surface another part of the app can use.
Exact field names can change
during implementation, but the data responsibilities are locked:

- `PregateRulePack`: rule-pack name, version, signature fingerprint, lifecycle
  state, owner runtime, declared budget, source name, and promotion timestamps.
- `PregateRun`: run id, source snapshot hash, git commit or dirty patch hash, local
  or CodeBuild mode, status, start and finish times, native artifact version,
  and contract version.
- `PregateFinding`: SARIF id, rule-pack id, file path, line, severity, decision,
  canonical fingerprint, AutoIssue id, review id when applicable, and operator
  override id when applicable.
- `PregateContractSnapshot`: canonical contract form for REST, OpenAPI,
  Pydantic, Django serializer, and TypeScript interface shapes.
- `PregateProofObligation`: proof kind, budget, solver result, Z3 result, CVC5
  result, UNKNOWN reason, and Review queue id when needed.
- `PregateBlastRadius`: patch hash, affected tests, affected modules, affected API
  contracts, and GraphAnalyzer run id.
- `OperatorOverride`: existing Plan #18 override table or a governance-owned
  equivalent if that table has not landed. PreGate override commit markers link
  here.

No table may grow without a retention rule. Each row that represents a derived
artifact uses `artifact_hash`, `source_snapshot_hash`, and `rule_pack_version`.
If the same input appears again, PreGate updates the existing row or supersedes it
according to NO-DUPLICATES.md. Run artifacts attach to the K8s source-snapshot
hash from K8S.17 and expire through the existing retention path.

### 6.4 AutoIssue Integration

PreGate findings become AutoIssues, not a parallel issue store. Each rule pack gets
its own dynamic AutoIssue source named `pregate_<rule_pack_name>`, for example
`pregate_arch_boundary` or `pregate_contract_drift`. This lets the operator see noisy
rule packs at a glance and lets the session ritual pick from each source. The
75-pick ritual count grows as rule packs are added, following the Plan #18
ritual model.

Because the current AutoIssue schema uses a fixed source list and a short source
field, Phase 1 must widen source handling before broad PreGate ingestion:

- create or extend a source registry so dynamic sources are first-class;
- raise the source field length enough for `pregate_<rule_pack_name>`;
- expose dynamic sources through `/api/auto-issues/`;
- update frontend clients to treat source as a registry value instead of a
  fixed string union;
- keep existing source names stable for GlitchTip, Pyroscope, Tempo, Loki,
  Faro, SonarQube, VictoriaMetrics alerting, Rust defect import, mutation,
  fuzz, contract, GitHub CI, and agent findings.

Every PreGate operational problem also becomes an AutoIssue. Sidecar unavailable,
rule pack signature failure, solver budget exhaustion, K8s merge missing
artifacts, malformed SARIF, and importer failures all file or dedupe rows. If
backend filing is unavailable in a local hook, the existing findings buffer from
`fr-hook-finding-autoissue.md` is used and drained later.

### 6.5 Hook Integration

Pre-commit hard blocks already live in `.githooks/*.py`, with more than 47
hooks. PreGate adds at most 8 to 12 new hooks. They are thin Python wrappers that
call the PreGate Rust extension and the existing AutoIssue filing helper, not a
hundred new checks.

The planned hook set is:

- `check-pregate-architectural-boundaries.py`;
- `check-pregate-contract-drift.py`;
- `check-pregate-migration-safety.py`;
- `check-pregate-security-proof-queue.py`;
- `check-pregate-prompt-injection-comments.py`;
- `check-pregate-hallucinated-apis.py`;
- `check-pregate-secret-env-reads.py`;
- `check-pregate-performance-proof.py`;
- `check-pregate-dead-code-on-replace.py`;
- `check-pregate-workflow-phase.py`;
- `check-pregate-agent-identity.py`;
- `check-pregate-rule-pack-integrity.py`.

The quality-layer hooks (Section 18 and Section 19) add a further set:

- `check-pregate-elcv.py` (ELCV anti-gaming gate);
- `check-pregate-duplication.py`;
- `check-pregate-complexity.py`;
- `check-pregate-churn.py`;
- `check-pregate-dead-code.py`;
- `check-pregate-build-time.py`;
- `check-modular-monolith-boundaries.py` (the Layer 1-2-3 import-flow rule). This
  hook and its `import-linter` contract do not exist yet — the modular-monolith
  boundary enforcement is slice 2-plus of that refactor and is unbuilt — so PG.06
  CREATES both; it is not an "extend."

Several quality metrics reuse hooks that already exist and are not duplicated:
`check-file-size.py` (size), `check-mutation-score.py` (mutation),
`check-per-module-coverage.py` and `check-coverage-erosion.py` (coverage),
`check-no-cross-language-import.py` (coupling), and `lint-all.ps1` step 10
(churn fan-out). Metric thresholds live in a new `config/quality-thresholds.yaml`
(schema in Section 18.2; the file does not exist yet and is created by the first
quality-gate slice) so a downgrade is caught by the existing
`check-no-downgraded-gates.py`.

The hooks reuse `git diff` and the existing hook finding to AutoIssue path.
PreGate does not write a bespoke diff parser. Hooks that detect deterministic hard
violations block the commit. Hooks that produce review-class uncertainty file a
finding and route to the Plan #17 Review queue.

### 6.6 Pre-Commit Advisor Integration

The advisor path runs before the agent commits, and, where the agent runtime
supports a PreToolUse hook, before the edit. It is Python, not Lua — Lua is a
removed language, so the earlier Plan #41 Lua advisor is superseded. The advisor
warns about likely workflow or rule-pack problems earlier than a hard block. It
remains advisory: it reminds, classifies, and explains. Hard-block enforcement
stays in the pre-commit hook chain.

The advisor calls the same PreGate Rust extension the hooks call, so advice and
enforcement share one engine. Rule packs are Rust modules plus Python config;
they are signature-verified and move through the shadow, canary, and production
lifecycle. The earlier Lua sandbox and WebAssembly packaging are superseded.

### 6.7 UI Integration

The app is Angular 22 today; there is no React rewrite on disk, and the locked UI
direction is Angular CDK plus Tailwind (Plan #13's "remove Angular / move to
React" framing is superseded — see Section 4). PreGate UI is therefore an Angular
page at `/diagnostics/pregate/`, built from the shared Angular components, not a
new framework and not a second screen.

The PreGate diagnostics page shows:

- current PreGate availability: healthy, degraded, or unavailable;
- latest local and CodeBuild runs;
- rule-pack health, lifecycle state, version, signature, and budget use;
- open PreGate AutoIssues grouped by `pregate_<rule_pack_name>`;
- false-positive rate, computed as operator override rate over 30 days;
- slowest rule packs by p50, p95, and p99 latency;
- solver UNKNOWN counts routed to Review;
- K8s shard status and final merge report links for PreGate Bazel targets;
- override markers and their linked OperatorOverride rows.

Until that page is built, the app-visible minimum is the AutoIssues table and the
diagnostics API. PreGate must not hide findings in local files.

### 6.8 Code Quality Page (ELCV + the ten metrics)

The quality layer (Section 18) and ELCV (Section 19) get their own operator
surface at `/diagnostics/code-quality`, in the SYSTEM navigation group as a
sub-surface of Diagnostics. It reuses existing frontend building blocks rather
than new ones: the ECharts directive
(`frontend/src/app/shared/charts/echarts.directive.ts`), the GA4 summary card
(`shared/gsc/gsc-summary-card`), the plain-English hover
(`shared/directives/pe-helper.directive.ts`), the empty-state component, and the
GA4 tokens in `_theme-vars.scss`. It is registered in
`frontend/src/app/core/routing/deep-link-catalog.ts` with tabs `elcv`, `metrics`,
`coverage`, `mutation`, `duplication`, and `dead-code`.

The page shows:

- an ELCV gauge: current whole-system ELCV, its growth per release, the trend
  toward the 5,000,000 target, and any regression flag;
- ten metric tiles (one per Section 18 metric): pass or fail, current value,
  threshold, and a sparkline, each with a `peHelper` plain-English hover;
- an anti-gaming panel listing recent blocked ELCV-inflation attempts;
- a "dead code (ARW=0)" list and a per-module table of ELCV, coupling, and
  duplication.

Backend: a new `backend/apps/governance/pregate/services/code_quality.py` plus a
`CodeQualityMetricsView` at `/api/governance/code-quality/` returning the same
JSON-tile shape as the existing `PrometheusSummaryView` (that shape is documented
in Section 25). The computation lives in governance (Layer 3); its gauge values
register into the shared process-global `prometheus-client` registry through a
governance-owned `metrics_pregate.py`, and the observability `/metrics/` endpoint
scrapes that shared registry without importing governance (the Section 6.1
boundary contract). The frontend polls on a 60-second timer using the existing
polling pattern, and shows an "unavailable" state through the empty-state component
when the backend or the Rust extension is down. Like every PreGate surface, it
never hides results in local files.

## 7. What PreGate Checks

The existing observability stack already covers runtime errors, profiles,
traces, logs, metrics, code smells, and CI failures. PreGate covers the gaps below.
Each gap maps to app integration, a rule-pack source, and a decision path.

### Gap A: Pre-Execution Semantic Checks

Existing systems mostly report after code executes. PreGate runs semantic checks
before execution. A semantic check means the engine reads code structure and
meaning, not just text shape. Examples include "this function calls a method
that does not exist" or "this serializer removed a required field."

Implementation:

- Parse changed files with Tree-sitter, an open-source parser that creates
  concrete syntax trees for many languages [TREE_SITTER].
- Convert parse trees into UAST nodes and then CIR nodes for analysis.
- Hash file and patch identity with BLAKE3, a fast content hash [BLAKE3].
- Emit findings as SARIF v2.1.0 [SARIF] and AutoIssues.

App path:

- local advisory hints appear before edits when the Python advisor can see the
  intent;
- deterministic violations block in `.githooks`;
- review-class findings go to Plan #17 Review.

### Gap B: Architectural Boundary Violations Beyond The Existing Hook

The repo does not yet have a module-boundary hook: the modular-monolith
`import-linter` enforcement is slice 2-plus of that refactor and is unbuilt, and
`.githooks/` ships only `check-no-cross-language-import.py`. PreGate's boundary
slice therefore CREATES `check-modular-monolith-boundaries.py` and the
`import-linter` contract (it is not an extend). The check covers cross-module
imports outside `api.py`, layering reversals, sidecar bypass, and direct private
calls into another module.

Implementation:

- Use Tree-sitter [TREE_SITTER] for import and call-site extraction.
- Use Tarjan's SCC algorithm, where an SCC is a group of nodes that can all
  reach each other, to summarize cyclic dependency groups [TARJAN_SCC].
- Use the modular monolith docs and ADRs 0001 through 0006 as the source of
  allowed boundaries.

App path:

- source `pregate_arch_boundary`;
- hard-block when a forbidden import or sidecar bypass is deterministic;
- AutoIssue description names the caller, callee, expected public boundary,
  and suggested `api.py` move.

### Gap C: Breaking-Change Detection Across Contracts

PreGate detects breaking changes in REST, meaning Representational State Transfer
HTTP APIs, OpenAPI, Pydantic models, Django serializers, and TypeScript
interfaces [OPENAPI] [PYDANTIC] [DJANGO] [TYPESCRIPT]. A contract is the shape one
part of the app promises another part can call or read. gRPC and Protocol
Buffers are not contract targets: `.proto` is a blocked file type under the
Python-plus-Rust rule, so the repo has none.

Implementation:

- Build canonical contract forms for each source.
- Diff canonical forms with compatibility rules.
- Use GumTree source differencing, a structured source-code differ, when a
  language-aware tree diff is needed [GUMTREE].
- For OpenAPI, compare schema changes against the official OpenAPI
  Specification [OPENAPI].

App path:

- source `pregate_contract_drift`;
- deterministic breaking removals hard-block;
- ambiguous compatibility changes route to Review;
- findings link to the contract snapshot and affected frontend/backend paths.

### Gap D: Database Migration Safety

PreGate checks migration risk before the database sees it. It detects drop-column,
drop-table, irreversible alter, missing default, missing NOT NULL backfill, and
lock-escalation risk.

Implementation:

- Parse Django migration files and SQL with Tree-sitter [TREE_SITTER].
- Apply PostgreSQL lock and constraint rules from the PostgreSQL docs
  [POSTGRES].
- Reuse the existing migration-data-safety command where possible.

App path:

- source `pregate_migration_safety`;
- deterministic destructive migration without approved evidence hard-blocks;
- valid but risky migration creates a Review item with required backfill,
  rollback, and lock notes.

### Gap E: Mathematical Safety Proofs For Security-Critical Paths

PreGate uses mathematical proofs only for security-critical paths. It does not try
to prove the whole app. A proof obligation is a small math problem generated
from code and sent to an SMT solver, which is a tool that proves formulas over
types like integers, arrays, and booleans.

Covered proof kinds:

- array bounds;
- integer overflow;
- null safety;
- authentication must dominate sensitive operation, where a dominator means
  every path to the sensitive operation passes through the authentication check
  first.

Implementation:

- Use Hoare triples, before-during-after specifications for code blocks, for
  narrow proof definitions [HOARE].
- Use abstract interpretation, which safely approximates program behavior, and
  Galois connections, the math pattern that makes the approximation sound,
  where the proof generator needs data-flow facts [ABSTRACT_INTERPRETATION]
  [GALOIS].
- Use bounded chaotic iteration, repeated analysis until no new information is
  learned, with strict budgets.
- Use Lengauer-Tarjan dominators for authentication dominance
  [LENGAUER_TARJAN].
- Send proof obligations to Z3 and CVC5 for cross-checking [Z3] [CVC5].

Budgets:

- local: one second per proof obligation;
- CodeBuild: 30 seconds per proof obligation;
- UNKNOWN never auto-rejects. UNKNOWN goes to the Plan #17 Review queue.

App path:

- source `pregate_security_proof`;
- hard-block only when both solvers prove a deterministic violation within
  budget;
- UNKNOWN creates `PregateProofObligation` plus Review queue item.

### Gap F: Test Impact Blast Radius

PreGate computes which tests are invalidated by a patch. Blast radius means the set
of code paths or tests affected by a change.

Implementation:

- Use Plan #36 GraphAnalyzer for call graph and dependency graph operations.
- Use Apache AGE, the PostgreSQL graph extension, for graph queries [APACHE_AGE].
- Use openCypher query syntax through Apache AGE docs [OPENCYPHER].
- Store affected file and test sets with Roaring bitmaps, compressed bit arrays
  that make large set operations fast [ROARING].

App path:

- source `pregate_blast_radius`;
- K8s local mode uses the result to choose incremental Bazel targets;
- UI shows "why this test was selected" through a call-graph path.

### Gap G: Prompt Injection Inside Code Comments

PreGate detects prompt-injection text hidden in code comments. Prompt injection in
this context means text that tries to trick an AI agent into ignoring project
rules or leaking secrets.

Implementation:

- Use Aho-Corasick for fast multi-pattern string search across a known injection
  corpus [AHO_CORASICK].
- Use Unicode TR39 confusable detection for homoglyphs, characters that look
  the same but have different code points [UNICODE_TR39].
- Use MinHash and LSH for near-duplicate matching against the known corpus when
  comments are paraphrased [MINHASH] [LSH].

App path:

- source `pregate_prompt_injection`;
- deterministic direct matches hard-block;
- near-duplicate matches warn locally and route to Review unless confidence is
  above the rule pack's production threshold.

### Gap H: Hallucinated APIs

PreGate detects code where an AI added `foo.bar()` but `foo` has no method `bar` in
the codebase. This is common when a model invents a plausible method name.

Implementation:

- Use Tree-sitter [TREE_SITTER] to extract call expressions.
- Build scope-resolution tables and symbol tables per language.
- Compare call sites against local definitions, imports through `api.py`,
  generated clients, and known external dependencies.

App path:

- source `pregate_hallucinated_api`;
- deterministic missing local methods hard-block;
- external dependency uncertainty goes to Review with the package and symbol
  name.

### Gap I: Unauthorized Environment Variable Reads

PreGate detects new reads of restricted environment variables outside
`apps/governance/secret_allowlist.py`.

Implementation:

- Parse Python, Rust, and TypeScript environment-access patterns (the repo's
  actual languages).
- Compare environment keys against the governance allowlist.
- Treat secret-like key names as high severity when the key is not listed.

App path:

- source `pregate_secret_env_read`;
- deterministic unauthorized reads hard-block;
- finding includes the key, file, line, and allowlist path.

### Gap J: Cross-Language Contract Drift

PreGate detects when a Pydantic model, a Django serializer, and a TypeScript
interface declare different shapes for the same app contract.

Implementation:

- Build canonical forms for each language contract.
- Compare required fields, optional fields, enum values, numeric ranges, and
  nullability.
- Use Datalog clauses, small if-then rules, only when cross-language
  reachability cannot be expressed by the existing rule-pack pattern
  [DATALOG].

App path:

- source `pregate_cross_language_contract`;
- deterministic drift hard-blocks when it would break a caller;
- otherwise a Review item lists each contract source and the mismatched field.

### Gap K: Performance Regression Proof

PreGate checks that every hot-path edit includes benchmark proof. A hot path is code
run often enough that slowdown matters to users or to the worker process.

This gap reuses an existing live gate. The repo already ships
`backend/apps/benchmarks/services/regression_gate.py` (landed 2026-06-13): it
maps changed files to affected benchmark functions, compares each function's
latest result against its rolling baseline, and blocks at more than ten percent
slower than baseline or at fewer than three baseline samples (ambiguous, so it
blocks conservatively). PreGate does not re-implement benchmark diffing.

Implementation:

- Call `backend/apps/benchmarks/services/regression_gate.py` to get its
  pass-or-block verdict for the changed files [REGRESSION_GATE].
- Read the existing Plan #21 Phase G and Plan #29 hot-path-gap #34
  macrobenchmark requirements and assert the required proof markers exist.
- Compare benchmark identifiers against touched native and Python paths.

App path:

- source `pregate_performance_proof`;
- `check-pregate-performance-proof.py` composes with `regression_gate.py`: a
  regression-gate block or a missing proof marker on a hot path hard-blocks the
  commit;
- proof artifacts and the regression-gate verdict link to AutoIssue and
  diagnostics.

### Gap L: Dead-Code-On-Replace

PreGate checks that when a function is replaced, the old version is deleted in the
same commit. This follows Plan #19 and Rule H.29.

Implementation:

- Use GumTree [GUMTREE] plus Myers bit-parallel edit distance, a fast edit
  distance algorithm, to detect replace patterns [MYERS].
- Use MinHash and LSH to catch near-duplicate old/new bodies [MINHASH] [LSH].
- Use Cuckoo filters, compact membership filters, to avoid repeatedly scanning
  known deleted bodies [CUCKOO].

App path:

- source `pregate_dead_code_replace`;
- deterministic duplicate old implementation hard-blocks;
- false positives can use the PreGate override marker.

### Gap M: Workflow Phase Validation

PreGate validates the seven workflow phases from Plan #41: research, BDD, TDD,
implement, review, AutoIssues, and commit. BDD means behavior-driven
description in Given/When/Then form. TDD means test-driven development, where a
test is written before or alongside the code and the Red-Green-Refactor cycle is
recorded.

Implementation:

- Use the Python advisor to remind during PreToolUse.
- At commit time, check that each phase artifact exists and is fresh.
- Reuse the repo's `TDD-STRICT-RULE.md`, paper-trail evidence rule, test-case
  rule, and code-review lesson rule.

App path:

- source `pregate_workflow_phase`;
- missing deterministic phase evidence hard-blocks;
- advisory reminders stay non-blocking before the commit.

### Gap N: AI-Agent Identity Drift

PreGate tracks which agent wrote which code. Agent identity drift means a commit
claims one agent context but the session evidence points to a different agent
or bypasses the required startup ritual.

Implementation:

- Require commit trailers naming the agent.
- Cross-check `AGENT-HANDOFF.md` session markers, including the 12-marker
  session-start ritual.
- Link findings to the agent, the session id, and the touched files.

App path:

- source `pregate_agent_identity`;
- bypassed ritual markers hard-block;
- identity mismatch goes to Review if the evidence is ambiguous.

### Gap O: Non-Gamable Code-Size Accounting (ELCV)

The runtime stack has no concept of "how much real logic exists," and raw line
counts are trivially gamed by formatting, duplication, or generated scaffolding.
PreGate computes Effective Logical Code Volume (ELCV) instead — a deduplicated,
runtime-validated, complexity-weighted measure of executed logic. ELCV is also
how the project's 5,000,000 target is expressed and tracked.

Implementation: see the full definition in Section 19. In summary, PreGate's Rust
extension builds the four ELCV inputs (LEU, USO, ARW, SCW) from the Tree-sitter
parse (Section 8), an EXTENDED `papertrail_dedup` engine (a new code-token
normalizer on top of its MinHash/LSH — not a drop-in reuse), and a
production-execution registry that PG.E3 must build (Pyroscope gives live profiles,
not the 30-day per-symbol history ARW needs), then aggregates them deterministically
in CI. Until the registry and the code-token normalizer ship, ELCV reports as
`pending` (Section 19.4), not a fabricated number.

App path:

- source `pregate_elcv`;
- a commit whose ELCV rises without a matching rise in executed, unique, and
  behaviorally distinct logic hard-blocks (anti-gaming);
- the whole-system ELCV, its growth per release, and any regression are shown on
  the Code Quality page (Section 6.8) and tracked toward the 5,000,000 target.

## 8. Multi-Language Parsing And Analysis

PreGate parses through Tree-sitter using the Rust `tree-sitter` crate
[TREE_SITTER]. It does not write a parser per language. Each supported language
gets one Rust mapper module, about 6,000 lines including tests, that converts
Tree-sitter output to the PreGate UAST and CIR. The mapper modules compile into
the single PyO3 extension.

Supported languages match what the repo actually contains today:

- Python;
- Rust;
- TypeScript;
- JavaScript;
- SQL;
- YAML;
- JSON;
- Markdown;
- Dockerfile.

The removed backend languages (C, C++, Go, Haskell, Lua) are not parse targets,
because the repo contains none of them; a mapper is added only if the repo ever
adds a new language.

The CIR is stored in the Rust extension's memory with explicit budgets. Roaring
bitmaps store sets of file ids, symbol ids, rule ids, and affected test ids
[ROARING]. Arena allocation may be used so a whole run's graph is freed at once;
it is a latency optimization only. Removing it may make the rule kernel two to
three times slower, but it does not change correctness.

## 9. Policy And Rule Packs

PreGate does not introduce a bespoke Datalog runtime. Policy lives in Rust rule
modules plus Python configuration (the Plan #18 rulesd Go/WebAssembly service and
the Plan #40 Lua packs are superseded by the Python-plus-Rust rule). A Datalog
clause, evaluated by a small Rust engine, is added only for transitive
reachability across the call graph, where simpler rule patterns are not
expressive enough [DATALOG].

Rule-pack lifecycle:

1. Author the rule pack as a Rust module plus its Python config entry.
2. Build it into the PyO3 extension through the Docker-managed maturin path
   [MATURIN].
3. Sign the pack.
4. Run 24 hours in shadow mode.
5. Run 24 hours in canary mode (the shadow-then-canary progressive-promotion
   practice [CONTINUOUS_DELIVERY]).
6. Promote to production only after false-positive rate and latency are within
   budget.
7. If the pack misbehaves, return it to shadow status. Do not auto-delete it.

Each rule pack declares:

- name and `pregate_<rule_pack_name>` source;
- version and signature;
- owner runtime;
- budget tier;
- severity mapping;
- local-mode eligibility;
- CodeBuild-only checks;
- AutoIssue category;
- SARIF rule id;
- override policy;
- citations for any named algorithm or data structure it uses.

The quality layer adds seven rule packs, each its own dynamic AutoIssue picker
source per the Plan #18 model: `pregate_elcv`, `pregate_duplication`,
`pregate_complexity`, `pregate_churn`, `pregate_defect_density`,
`pregate_build_time`, and `pregate_dead_code`. They are full rule packs and obey
the same shadow, canary, production lifecycle as every other pack.

## 10. Execution Modes

### 10.1 Local Incremental Mode

Local mode runs on the agent's working-directory diff. It uses `git diff` and
the K8s source snapshot when distributed tests are involved. It does not use a
bespoke diff parser.

Local mode includes:

- Python advisory checks before tool use;
- fast AST and text checks;
- selected medium cross-file checks;
- one-second proof obligations only for security-critical touched paths;
- AutoIssue filing for every finding;
- SARIF export for every finding.

Target: under two seconds for the incremental scan path.

### 10.2 Local K8s Mode

The planned K8s plus Bazel distributed-test foundation (slices K8S.01-K8S.25)
runs PreGate as Bazel test targets. This foundation is not built yet (see
Section 4.1): until it lands, PreGate runs through the existing Docker
quality-runner scripts and the `.githooks` chain, and this section describes the
target path. When the foundation ships, PreGate inherits:

- K8S.17 source-snapshot protocol, which captures tracked, staged, unstaged,
  and untracked working-tree files;
- K8S.18 coverage adapters;
- K8S.19 mutation adapters;
- K8S.20 `distribute_tests` sharding formula and guardrails;
- K8S.21 12-gate coordinator preflight;
- K8S.22 Bazel shard job wrapper and Build Event Protocol output discovery;
- K8S.23 final merge job and final report;
- K8S.25 cutover route through existing quality commands.

Local K8s runs the incremental subset. It does not replace CodeBuild for the
full master gate.

### 10.3 AWS CodeBuild Master Gate

AWS CodeBuild runs the full mutation, coverage, and cross-language PreGate suite.
It respects the Step 5 budget lock and the Plan #32 time window. If the
CodeBuild budget reaches the 100 percent cap, the PreGate master-gate suite skips
as required by the Step 5 lock. Local K8s incremental PreGate still runs.

## 11. Observability

PreGate emits observability through the existing stack only: OpenTelemetry,
Tempo, Pyroscope, GlitchTip, Loki, Prometheus exposition, and VictoriaMetrics
[OPENTELEMETRY] [TEMPO_DOCS] [PYROSCOPE_DOCS] [GLITCHTIP_DOCS] [LOKI_DOCS]
[PROMETHEUS_EXPOSITION] [VICTORIAMETRICS_DOCS].

Metrics path (current, verified this session). The live metrics path is Prometheus
exposition: the backend exposes a `/metrics/` endpoint that the `otel-collector`
scrapes on port 8889 and Grafana reads, all through the `prometheus-client`
registry. Four instrumentation modules already follow this pattern:
`backend/apps/observability/metrics_ranking.py`, `metrics_retrieval.py`,
`metrics_embeddings.py`, and `metrics_workers.py` [PROMETHEUS_MONITORING]. PreGate
adds a fifth module, `backend/apps/governance/pregate/metrics_pregate.py`
(governance-owned per the Section 6.1 boundary contract), that registers its
per-rule-pack counters and timers into the same shared process-global registry, so
they appear at the same `/metrics/` endpoint without a cross-module import. The
`PrometheusSummaryView` at `/api/observability/prometheus-summary/` exposes a small
set of live values for the diagnostics page. VictoriaMetrics runs locally today —
`vmsingle`, `vmagent`, and `vmalert` are services in `docker-compose.yml` (deployed
2026-06-13); `vmagent` scrapes the exposition path into `vmsingle:8428`, which
`PrometheusSummaryView` queries. VictoriaMetrics is the durable store now, not a
future remote dependency.

Every PreGate call from the Python adapter into the Rust extension emits an
OpenTelemetry span. A span is one timed operation in a trace. The span carries
these attributes:

- `component_name`;
- `owner_runtime=rust`;
- `fallback_used=false`;
- `runtime_artifact_version`;
- `runtime_contract_version`;
- `duration_ms`;
- `error_class`;
- `rule_pack_name`;
- `rule_pack_version`.

Tempo receives trace context across the in-process PyO3 boundary per Plan #37
idea 26. Pyroscope profiles the Rust extension continuously with a 100 MB profile
cap. GlitchTip captures typed errors:

- `RustUnavailableError`;
- `CompiledRuntimeContractError`;
- `CompiledRuntimeTimeoutError`;
- `PregateRulePackError`;
- `PregateProofObligationUnknown`.

Loki receives structured logs with:

- `run_id`;
- `rule_pack_id`;
- `file_path`;
- `line`;
- `severity`;
- `decision`, with values `allow`, `warn`, `review`, or `critical`.

The metrics path (Prometheus exposition through `metrics_pregate.py` now,
VictoriaMetrics as the durable remote store later) tracks:

- per-rule-pack p50, p95, and p99 latency;
- per-rule-pack false-positive rate, measured as operator override rate over a
  30-day rolling window;
- Rust extension availability;
- proof UNKNOWN rate;
- AutoIssue filing failures.

Every finding has SARIF v2.1.0 output [SARIF] and a corresponding AutoIssue or
Review item.

## 12. Risk And Rollback Map

| Risk | Behavior | Rollback or recovery |
|---|---|---|
| The Rust extension fails to load or errors | Python raises `RustUnavailableError`. Pipeline continues without PreGate checks. | Operator sees "PreGate unavailable" chip using the Plan #25 G-229 explanation library. AutoIssue is filed. |
| Z3 or CVC5 returns UNKNOWN beyond budget | PreGate does not reject the change. | Route to Plan #17 Review queue and store `PregateProofObligation`. |
| Tree-sitter upstream breaks | The `tree-sitter` crate version is pinned in `Cargo.toml`. | Bump only through a paper-trail entry and golden-test update. |
| Arena optimization unavailable | Correctness unaffected. | Fall back to normal allocation. Latency may degrade two to three times. |
| Rule pack misbehaves | Signature verification plus the shadow, canary, production lifecycle contains it. | Return the pack to shadow status. Never auto-delete it. |
| CodeBuild reaches 100 percent budget cap | PreGate master-gate suite skips per Step 5. | Local K8s incremental scan still runs. AutoIssue records the budget skip. |
| Known false positive | Operator adds `[PREGATE OVERRIDE: rule_pack=<name> rule_id=<id> reason="..."]` in the commit body. | Override is logged to OperatorOverride and counted in false-positive rate. |
| AutoIssue filing fails | Hook helper writes to findings buffer where allowed. | Drain buffer next session. In CI, fail strict because soft filing is not allowed. |
| Dynamic PreGate source unsupported | Current schema/client cannot show sources cleanly. | Phase 1 resolves AutoIssues #2470 and #2471 before broad rule-pack ingestion. |

### 12.1 Per-Phase Runbooks

Each phase has its own most-likely failure and recovery.

- Phase 1 (skeleton): if the PG.02 governance migration conflicts with another
  in-flight migration, sequence PG.02 after that stream and rebase; if PG.01
  cannot widen the AutoIssue source field safely on live data, gate PreGate
  ingestion behind a feature flag and file a paper-trail entry, but do not ship
  rule packs until #2470 and #2471 are resolved.
- Phase 2 (parsers): if a Tree-sitter grammar drifts and breaks a golden test,
  pin the grammar version in the build manifest and bump it only through a
  paper-trail entry plus a golden-test update; never silently re-bless goldens.
- Phase 3 (blast radius): if Apache AGE is not yet wired, fall back to the
  GraphAnalyzer in-process call graph and mark blast-radius results "partial"
  in the finding; do not block on a missing graph store.
- Phase 4 (proofs): if Z3 and CVC5 disagree, treat the obligation as UNKNOWN and
  route to Review (never auto-reject); if a solver binary is missing in
  `compiled-tools`, skip heavy rules and file an AutoIssue rather than passing
  silently.
- Phase 5 (lifecycle): if a rule pack misbehaves in canary, return it to shadow
  (never auto-delete); if signature verification fails, refuse to load the pack
  and file an AutoIssue.
- Phase 6 (production library): if the CodeBuild master gate would exceed the
  15-minute budget or the cost cap, shed the heaviest rule packs to a nightly
  run and keep the local incremental subset live; record the shed in an
  AutoIssue.

## 13. Self-Test Strategy

PreGate must satisfy the Plan #21 Quality Bar before production use. The engine is a
validator, so it must be harder on itself than on normal feature code. This
section defines PreGate's own test layers; the repo-wide, enforced quality layer
that PreGate applies to all code (Test-Driven Development plus the ten engineering
metrics) is specified in Section 18, and the non-gamable code-size metric ELCV in
Section 19. PreGate is held to both — it dogfoods every gate.

Required test layers:

- Property-based testing through the live repo gate. The repo already runs a
  hard pre-commit property-based-testing gate (landed 2026-06-13):
  `python scripts/bazel_default.py run //tools/quality:pbt`, wired through
  `scripts/precommit-docker.sh`, with a single
  five-minute shared budget, scoped to changed files, Dell-only and fail-closed.
  Property-based testing means generating many inputs to test a rule, not just
  hand-picking examples (citation lineage QuickCheck [QUICKCHECK]). PreGate's
  pure-logic kernels ship tests that ride this gate:
  - Python kernels: `property`-marked Hypothesis tests run by
    `python -m pytest -m property` under the `fast` profile locally and `ci` in
    CI (profiles in `backend/conftest.py`, marker in `backend/pytest.ini`)
    [HYPOTHESIS];
  - Rust kernels: proptest cases run by `cargo nextest run -E "test(/prop_/)"`
    [PROPTEST] [NEXTEST].
- Snapshot tests with insta for the Rust parser, UAST, CIR, canonical contract
  snapshots, and proof obligations. A snapshot test compares output to a
  checked-in expected file [INSTA].
- Mutation testing with mutmut for Python, cargo-mutants for Rust, and Stryker
  for any frontend TypeScript (driven by Vitest through the command runner;
  Karma is gone) [MUTMUT] [CARGO_MUTANTS] [STRYKER]. The removed-language
  mutators (MuCheck, Mull, go-mutesting) no longer apply. Mutation testing
  changes code on purpose to prove tests catch real behavior changes. The repo
  enforces a ratchet: `.mutation-score-baseline.json` plus
  `.githooks/check-mutation-score.py` hold a per-target baseline that only rises;
  the target is above 90 percent (Stryker thresholds 95 percent).
- Fuzz testing with cargo-fuzz (libFuzzer under the hood) for the patch parser,
  Tree-sitter wrappers, and the Unicode homoglyph detector [CARGO_FUZZ]
  [LIBFUZZER].
- Concurrency checks with loom for the Rust extension's concurrent paths. Loom
  explores interleavings to prove the concurrent code behaves like some valid
  one-at-a-time order [LOOM].
- Coverage target: 95 percent on the rule-engine kernel and 90 percent
  elsewhere, following `docs/CODE-COVERAGE-RULES.md` and Plan #21 Phase D.
- Five-layer TDD coverage from `docs/TDD-STRICT-RULE.md`: edge cases, resource
  release, latency, smoke, and end-to-end tests on every touched file.
- Lint and type checks on PreGate's own surfaces use the current repo tools:
  ruff (`select=["ALL"]`) and mypy for Python, oxlint then eslint for any
  TypeScript, clippy for Rust [RUFF] [CLIPPY]. pylint is not used (removed).

Quality-tool container ownership. PreGate's Python quality tools (ruff, mypy,
bandit, pytest, mutmut, coverage) run in the `backend-quality` container, never
the runtime `backend`. Compiled-language quality runs in `compiled-mutation-tools`
and `compiled-tools`; frontend quality runs in `frontend-mutation-tools`. This
matches the repo's quality-container split.

The PreGate test suite must be discoverable by the existing quality-runner
scripts today and by the K8s Bazel runner and CodeBuild once they land. New
languages, folders, runtime paths, and build targets must update tool wiring in
the same slice.

Dogfooding bootstrap (resolving the chicken-and-egg). PreGate's own gates do not
exist during PG.01-PG.05, so those slices are held to the EXISTING repo gates — the
`.githooks` chain, `//tools/quality:pbt`, the mutation ratchet, and the coverage
hooks — which already enforce TDD, coverage, and mutation. As each PreGate gate arms
(Section 14.2), it is immediately pointed at PreGate's own code under
`apps/governance/pregate/` and its Rust crate, so the engine measures itself. The
ELCV gate measuring PreGate is not circular: ELCV is computed by the Rust extension
over all code including its own once PG.E5 lands, and before then PreGate's size is
governed by the existing `check-file-size.py`. Acceptance: a dogfood test runs the
armed PreGate gates against `apps/governance/pregate/` and shows them blocking a
seeded violation and passing clean code.

### 13.1 Exact Per-Tool Test Commands

These are the exact commands PreGate slices run. Until Bazel and K8s land, the
Docker quality-runner forms are authoritative; the Bazel target forms are the
target path.

| Layer | Exact command |
|---|---|
| Python property (rides the PBT gate) | `python scripts/bazel_default.py run //tools/quality:pbt` |
| Python unit and integration | `python scripts/bazel_default.py run //tools/quality:python` |
| Python mutation (ratcheted) | `python scripts/bazel_default.py run //tools/quality:mutation` |
| Python lint and types | `python scripts/bazel_default.py run //tools/quality:python` |
| Rust property | `cargo nextest run -E "test(/prop_/)"` (PROPTEST_CASES budget) |
| Rust mutation | `python scripts/bazel_default.py run //tools/quality:mutation` |
| Rust lint | `python scripts/bazel_default.py run //tools/quality:rust` |
| Rust unit, snapshot, fuzz, concurrency | `cargo nextest run` (unit + insta snapshot); `cargo fuzz run <target>` (fuzz); `cargo test` under loom (concurrency) |
| Rust and Python coverage | `cargo llvm-cov` (Rust) and `coverage.py` via `backend-quality` (Python) |
| Rust extension build | `maturin develop` for local iteration, `maturin build` for release, through the Docker-managed path |
| Frontend (any TypeScript surface) | `python scripts/bazel_default.py run //tools/quality:frontend` and `python scripts/bazel_default.py run //tools/quality:mutation` |
| The PBT pre-commit gate | `python scripts/bazel_default.py run //tools/quality:pbt` |

## 14. Roadmap

The roadmap has six phases over 18 to 24 months. Each slice is a small,
independently shippable unit (roughly 5,000 to 15,000 lines of change — a slice
granularity guide, not the size target; the size target is 5,000,000 ELCV per
Section 19). The target is 80 to 150 chronological slices.

### Phase 1: Months 1-3, About 15 Slices

Goal: app skeleton and highest-impact checks.

Deliverables:

- create `apps/governance/pregate/`;
- add governance `api.py` surface;
- create the Rust PyO3/maturin extension scaffold (no sidecar, no gRPC);
- add a health check the Python orchestrator can call through PyO3;
- create or amend ADR 0007 to record PreGate as a Rust PyO3 extension under the
  Python-plus-Rust rule;
- widen AutoIssue dynamic source support and frontend client handling, resolving
  AutoIssues #2470 and #2471;
- add SARIF writer and AutoIssue ingestion;
- add diagnostics API for `/diagnostics/pregate/`;
- add the 10 highest-impact rule packs:
  architectural boundary, breaking API, drop-column migration, taint flow,
  missing authentication, prompt injection in comments, hallucinated API,
  unauthorized environment read, dead-code-on-replace, performance-regression
  proof.

### Phase 2: Months 4-6, About 20 Slices

Goal: native parsing and UAST kernels.

Deliverables:

- Rust `tree-sitter` parsing integration inside the PyO3 extension;
- the UAST and CIR builder in Rust;
- per-language UAST mappers (Rust) for Python, Rust, TypeScript, and JavaScript;
- one Rust module per mapper, compiled into the single extension;
- insta snapshot tests for parse tree, UAST, and CIR output.

### Phase 3: Months 7-9, About 15 Slices

Goal: blast-radius computation.

Deliverables:

- Apache AGE graph projection;
- Plan #36 GraphAnalyzer integration;
- test-impact computation;
- Roaring bitmap affected-test sets;
- UI drill-in showing why a test was selected.

### Phase 4: Months 10-12, About 15 Slices

Goal: proof obligations for security-critical paths only.

Deliverables:

- Z3 and CVC5 integration;
- proof-obligation generator;
- one-second local and 30-second CodeBuild budgets;
- cooperative cancellation;
- UNKNOWN routing to Plan #17 Review;
- loom checks for concurrent Rust paths.

### Phase 5: Months 13-18, About 20 Slices

Goal: rule-pack lifecycle.

Deliverables:

- extend Plan #18 rulesd lifecycle for PreGate packs;
- signature verification;
- shadow, canary, production state machine;
- 24-hour shadow and 24-hour canary gates;
- rule-pack authoring guide;
- operator override workflow and false-positive metrics.

### Phase 6: Months 19-24, About 20 Slices

Goal: production rule library and app calibration.

Deliverables:

- expand to about 300 production rules across eight languages;
- Docusaurus documentation pages per Plan #17 Docs Freshness;
- AutoIssue picker source integration for every production rule pack;
- trust calibration dashboard integration per Plan #24;
- full CodeBuild master-gate suite under 15 minutes;
- local K8s incremental subset through Bazel.

### 14.1 Phase 1 Slice Index (PG.01-PG.15)

Phase 1 is carved into fifteen ordered, independently shippable slices. Each row
has a one-line acceptance check. Slice bodies for PG.01-PG.05 follow in full;
PG.06-PG.15 are each one rule-pack slice carved to its own file when picked up,
using the same template (this is normal slice-by-slice execution, not deferral).

| ID | Title | LOC | Depends on | Acceptance (one line) |
|---|---:|---|---|---|
| PG.01 | Resolve AutoIssue #2470 + #2471: widen AutoIssue source + dynamic source registry (backend + frontend) | 6,000 | none | A `pregate_demo` source registers, persists, and shows in `/api/auto-issues/` and the frontend client without a fixed-union error. |
| PG.02 | Create `apps/governance/pregate/` module + `api.py` + data model + migrations | 9,000 | PG.01 | `apps.governance.api` exposes the PreGate surface; PregateRulePack/Run/Finding/ContractSnapshot/ProofObligation/BlastRadius migrate cleanly in the governance database. |
| PG.03 | Rust PyO3/maturin extension scaffold + Python health call | 8,000 | PG.02 | `maturin develop` builds the extension; a Python health call returns OK; ADR 0007 records PreGate as a Rust PyO3 extension. |
| PG.03b | Tree-sitter parser bootstrap: the Rust `tree-sitter` crate inside the extension + one Python UAST mapper (with a Python `ast` bridge) | 8,000 | PG.03 | A Python file parses to UAST nodes the rule packs can query; a golden snapshot of the parse is checked in. Pulls a minimal slice of Phase 2 forward so the semantic rule packs have a parser. |
| PG.04 | SARIF v2.1.0 writer + AutoIssue ingestion (`pregate_*`) + `metrics_pregate.py` | 7,000 | PG.02 | A sample finding writes valid SARIF, files a `pregate_*` AutoIssue, and increments a Prometheus counter at `/metrics/`. |
| PG.05 | Diagnostics API for `/diagnostics/pregate/` (availability, runs, rule-pack health, override rate) | 6,000 | PG.04 | The API returns availability, latest runs, and per-rule-pack override rate as JSON. |
| PG.06 | Rule pack: architectural boundary (`pregate_arch_boundary`) + `check-pregate-architectural-boundaries.py` (creates the `import-linter` contract) | 7,000 | PG.03b, PG.04 | A forbidden cross-module private import hard-blocks with a named caller/callee finding. |
| PG.07 | Rule pack: breaking API / contract drift (`pregate_contract_drift`) | 9,000 | PG.06 | Removing a required OpenAPI field hard-blocks; an ambiguous change routes to Review. |
| PG.08 | Rule pack: drop-column migration safety (`pregate_migration_safety`) | 7,000 | PG.06 | A `DROP COLUMN` without approved evidence hard-blocks; a risky-but-valid migration routes to Review. |
| PG.09 | Rule pack: taint flow to sink (`pregate_taint_flow`) | 9,000 | PG.06 | User input reaching a SQL string without sanitization hard-blocks. |
| PG.10 | Rule pack: missing authentication dominance (`pregate_security_proof`) | 9,000 | PG.06 | A sensitive operation not dominated by an auth check routes to Review (UNKNOWN never auto-rejects). |
| PG.11 | Rule pack: prompt injection in comments (`pregate_prompt_injection`) | 7,000 | PG.06 | A known injection phrase in a comment hard-blocks; a homoglyph variant is caught. |
| PG.12 | Rule pack: hallucinated API (`pregate_hallucinated_api`) | 8,000 | PG.06 | A call to a method that does not exist locally hard-blocks; external uncertainty routes to Review. |
| PG.13 | Rule pack: unauthorized env read (`pregate_secret_env_read`) | 6,000 | PG.06 | A read of a restricted env key outside the allowlist hard-blocks with key/file/line. |
| PG.14 | Rule pack: dead-code-on-replace (`pregate_dead_code_replace`) | 7,000 | PG.06 | A replaced function whose old body survives in the same commit hard-blocks. |
| PG.15 | Rule pack: performance-regression proof (`pregate_performance_proof`) composing with `regression_gate.py` | 6,000 | PG.06 | A hot-path edit with no benchmark proof, or a regression-gate block, hard-blocks. |

Each PG.06-PG.15 slice ships its `check-pregate-*.py` hook plus `property`-marked
tests that ride `//tools/quality:pbt`, and follows the Quality Bar (mutation pass
on touched files, coverage above 90 percent, all hooks green, clean tree).

Parser dependency and splits (do not hide these). PG.06 through PG.14 are semantic
rule packs that all read the parse tree, so each depends on PG.03b in addition to
the rule-pack prerequisite named in its row; only PG.15 does not (it composes
`regression_gate.py` and needs no parser). The four parser-heavy packs — PG.07
(contract drift), PG.09 (taint), PG.10 (authentication dominance), and PG.12
(hallucinated API) — are each carved as TWO slices: first the per-language
symbol/scope table for the language, then the rule on top. This keeps each half
inside the one-session, 5,000-to-15,000-line envelope instead of secretly
bootstrapping a parser inside a "rule pack" slice.

#### Slice PG.01 (full body)

- Spec: source-cited at this document plus `fr-hook-finding-autoissue.md`.
- Given the AutoIssue `source` field is 16-character fixed-choice and the
  frontend types it as a three-value union, When PG.01 adds a source registry,
  widens the field, and makes the client registry-backed, Then a new
  `pregate_demo` source registers, persists, lists in `/api/auto-issues/`, and
  renders in the client with no union error.
- TDD: Red — a test that registers `pregate_demo` and reads it back fails on the
  16-char/fixed-choice field and the frontend union. Green — migration widens the
  field, adds `SourceRegistry`, and the client reads the registry. Refactor —
  keep the 25 existing source names stable.
- Files: edit `backend/apps/auto_issues/models.py` (+ migration), add a source
  registry module, edit `frontend/src/app/core/services/auto-issues.service.ts`.
- Verify: `python scripts/bazel_default.py run //tools/quality:python` for the new
  round-trip test; `npm run test:ci` for the client.
- Done: #2470 and #2471 resolved; existing sources unchanged; tests green.

#### Slice PG.02 (full body)

- Given there is no `apps/governance/` module, When PG.02 creates
  `apps/governance/pregate/` with `api.py` and the six PreGate models, Then
  migrations apply and `apps.governance.api` exposes the PreGate surface.
- TDD: Red — import of `apps.governance.api` fails. Green — module + `api.py` +
  models + migrations. Refactor — keep private files behind `api.py`.
- Files: new `backend/apps/governance/__init__.py`, `api.py`,
  `pregate/models.py`, migration; settings registration.
- Verify: `python manage.py makemigrations --check`; boundary hook passes.
- Done: governance module imports cleanly; models migrate in the governance DB.

#### Slice PG.03 (full body)

- Given there is no PreGate Rust extension yet, When PG.03 scaffolds a Rust crate
  built through maturin and exposes a PyO3 `health()` function, Then Python
  imports the extension and `health()` returns OK, and ADR 0007 records PreGate
  as a Rust PyO3 extension.
- TDD: Red — a Python test that imports the extension and calls `health()` fails
  (no extension). Green — minimal Rust crate + PyO3 binding + maturin build.
  Refactor — keep the Python side orchestration-only.
- Files: new Rust crate (`Cargo.toml`, `src/lib.rs`, maturin config), `docs/adr/0007-*`.
- Verify: `maturin develop` builds; the Python health call returns OK under the
  Docker quality path.
- Done: extension builds and imports; health passes; a missing or failed
  extension raises a typed `RustUnavailableError`.

#### Slice PG.04 (full body)

- Given findings have nowhere to land, When PG.04 adds a SARIF v2.1.0 writer,
  `pregate_*` AutoIssue ingestion, and `metrics_pregate.py`, Then a sample
  finding writes valid SARIF, files a deduped AutoIssue, and increments a
  Prometheus counter at `/metrics/`.
- TDD: Red — SARIF schema-validation test fails. Green — writer + ingestion +
  metrics module. Refactor — reuse the existing hook-finding-to-AutoIssue path.
- Files: SARIF writer, ingestion command, `backend/apps/governance/pregate/metrics_pregate.py`.
- Verify: SARIF validates against v2.1.0; counter visible at `/metrics/`.
- Done: one finding flows file → SARIF → AutoIssue → metric.

#### Slice PG.05 (full body)

- Given findings are not app-visible, When PG.05 adds the diagnostics API for
  `/diagnostics/pregate/`, Then the API returns availability, latest runs, and
  per-rule-pack override rate as JSON.
- TDD: Red — API endpoint 404s. Green — DRF view + serializer. Refactor — read
  through `apps.governance.api` only.
- Files: governance diagnostics view, serializer, URL.
- Verify: authenticated GET returns the documented JSON shape; 401 without auth.
- Done: diagnostics JSON available; the Angular diagnostics page consumes it later.

### 14.2 Quality + ELCV Sub-Streams

Two further sub-streams deliver the Section 18 quality layer and the Section 19
ELCV metric. Both are TDD-first and must themselves pass every gate (PreGate
dogfoods). Because the thresholds are absolute from day one (Section 18), each
gate slice does **remediate-to-green then arm-the-gate in the same slice** — you
cannot arm an absolute gate on a dirty tree without halting work.

Sub-stream Q (quality gates), one slice per metric, ordered lowest-disruption
first: branch coverage → mutation → complexity → size → coupling → duplication →
churn → build/test time → production execution evidence → defect density. Each
slice: adopt the threshold into `config/quality-thresholds.yaml` (schema in
Section 18.2), remediate existing violations to green, arm the hard-block hook
(reusing an existing hook where one exists, adding a new `check-pregate-*.py` where
it does not), and add the GUI tile. Two ordering facts the simple list hides: the
duplication slice drives the same code-token USO engine as PG.E2, so it also
depends on the Tree-sitter parser (Phase 2 / PG.03b); and the defect-density gate
divides by KELCV (thousands of ELCV units), so it is only ARMED once KELCV ≥ 1.0
and stays advisory below that — otherwise a near-zero denominator would spuriously
hard-block every merge before ELCV is trustworthy.

Sub-stream E (ELCV): PG.E1 LEU extractor (Rust Tree-sitter, with a Python `ast`
bridge until the Rust parser lands) → PG.E2 USO — EXTENDS `papertrail_dedup` (adds
a new code-token normalizer and bound function on top of its MinHash/LSH; that
crate hashes error-text shingles today, so this is new work, not a drop-in reuse)
→ PG.E3 ARW production-execution registry (Pyroscope plus coverage contexts; until
it holds a full 30-day window a unit's ARW is `unknown`, excluded from the target,
never 0) → PG.E4 SCW complexity weighting → PG.E5 ELCV aggregator plus
`check-pregate-elcv.py` anti-gaming gate plus `config/quality-thresholds.yaml` →
PG.E6 Code Quality page and `/api/governance/code-quality/` → PG.E7
5,000,000-target tracking, regression detection, and the nightly recompute — the
5M gauge reported only once ARW coverage passes its configured threshold (until
then it reads `pending`, Section 19.4). PG.E1, PG.E2, and the Q duplication slice
depend on Phase 2 (Tree-sitter / PG.03b); PG.E3 depends on the observability and
Pyroscope stack.

One merged execution ledger. The single chronological order is: PG.01 → PG.05
(skeleton), then PG.03b and the semantic packs PG.06 → PG.15, then the Q and E
sub-streams interleaved against Phases 2 and 3 as their dependencies (first the
parser, then Pyroscope and the execution registry) land. A capable agent always
has exactly one "next slice" because every slice names its prerequisites; the
ledger is kept current as each slice is carved.

## 15. Acceptance Criteria

### Scenario 1: Local edit creates an app-visible PreGate finding

Given an agent edits a Python file and adds a forbidden cross-module private
import, when the local PreGate hook runs, then the commit is blocked, a SARIF
finding is written, and an AutoIssue with source `pregate_arch_boundary` is created
or deduped.

### Scenario 2: Solver uncertainty goes to Review

Given a security-critical proof obligation exceeds the local one-second budget,
when Z3 or CVC5 returns UNKNOWN, then PreGate does not reject the change and creates
a Plan #17 Review queue item with the proof details.

### Scenario 3: Rule-pack noise is visible

Given a rule pack produces many operator overrides over 30 days, when the
diagnostics page loads, then the page shows the rule pack's false-positive rate
and the source bucket is visible in AutoIssues.

### Scenario 4: K8s runs PreGate as Bazel targets

Given the K8s distributed test coordinator runs an incremental local suite, when
PreGate targets are selected, then they use the source-snapshot protocol, shard
through the K8S.20 formula, and merge coverage and mutation evidence through the
K8S.23 final merge job.

### Scenario 5: CodeBuild budget cap is respected

Given AWS CodeBuild reaches the 100 percent budget cap, when the master-gate
PreGate suite is due to run, then it skips per the Step 5 lock, files an AutoIssue,
and local K8s incremental PreGate remains available.

## 16. Citations

- [TREE_SITTER] Max Brunsfeld and Tree-sitter maintainers, 2017+, "Tree-sitter
  Documentation," official spec and docs, https://tree-sitter.github.io/tree-sitter/.
- [GUMTREE] Falleri, Morandat, Blanc, Martinez, and Monperrus, 2014, "Fine-grained
  and Accurate Source Code Differencing," DOI: 10.1145/2642937.2642982.
- [TARJAN_SCC] Tarjan, 1972, "Depth-First Search and Linear Graph Algorithms,"
  SIAM Journal on Computing, DOI: 10.1137/0201010.
- [LENGAUER_TARJAN] Lengauer and Tarjan, 1979, "A Fast Algorithm for Finding
  Dominators in a Flowgraph," ACM TOPLAS, DOI: 10.1145/357062.357071.
- [BLAKE3] O'Connor, Aumasson, Neves, and Wilcox-O'Hearn, 2020, "BLAKE3: One
  Function, Fast Everywhere," IACR ePrint 2020/1419, https://eprint.iacr.org/2020/1419.
- [AHO_CORASICK] Aho and Corasick, 1975, "Efficient String Matching: An Aid to
  Bibliographic Search," Communications of the ACM, DOI: 10.1145/360825.360855.
- [Z3] de Moura and Bjorner, 2008, "Z3: An Efficient SMT Solver," TACAS,
  DOI: 10.1007/978-3-540-78800-3_24.
- [CVC5] Barbosa, Barrett, Brain, Kremer, et al., 2022, "cvc5: A Versatile and
  Industrial-Strength SMT Solver," TACAS, DOI: 10.1007/978-3-030-99524-9_24.
- [ROARING] Chambi, Lemire, Kaser, and Godin, 2016, "Better Bitmap Performance
  with Roaring Bitmaps," Software: Practice and Experience, DOI: 10.1002/spe.2325.
- [DATALOG] Ullman, 1989, "Principles of Database and Knowledge-Base Systems,
  Volume 1," ISBN: 978-0716782759.
- [QUICKCHECK] Claessen and Hughes, 2000, "QuickCheck: A Lightweight Tool for
  Random Testing of Haskell Programs," ICFP, DOI: 10.1145/351240.351266.
- [CUCKOO] Fan, Andersen, Kaminsky, and Mitzenmacher, 2014, "Cuckoo Filter:
  Practically Better Than Bloom," CoNEXT, DOI: 10.1145/2674005.2674994.
- [MINHASH] Broder, 1997, "On the Resemblance and Containment of Documents,"
  DOI: 10.1109/SEQUEN.1997.666900.
- [LSH] Indyk and Motwani, 1998, "Approximate Nearest Neighbors: Towards
  Removing the Curse of Dimensionality," STOC, DOI: 10.1145/276698.276876.
- [MYERS] Myers, 1999, "A Fast Bit-Vector Algorithm for Approximate String
  Matching Based on Dynamic Programming," JACM, DOI: 10.1145/316542.316550.
- [UNICODE_TR39] Unicode Consortium, "Unicode Technical Standard #39: Unicode
  Security Mechanisms, Confusable Detection," Version 17.0.0, Revision 32,
  official version URL, https://www.unicode.org/reports/tr39/tr39-32.html.
- [LSHBLOOM] Plan #33 citation lineage for LSHBloom, cross-referenced by the
  AutoIssues enterprise evolution plan and its LSH/Bloom-filter sources.
- [APACHE_AGE] Apache AGE project, "Apache AGE Manual," official PostgreSQL
  extension docs, https://age.apache.org/age-manual/master/.
- [OPENCYPHER] openCypher project, "openCypher Resources and Specification,"
  official URL, https://opencypher.org/resources/.
- [HOARE] Hoare, 1969, "An Axiomatic Basis for Computer Programming,"
  Communications of the ACM, DOI: 10.1145/363235.363259.
- [ABSTRACT_INTERPRETATION] Cousot and Cousot, 1977, "Abstract Interpretation:
  A Unified Lattice Model for Static Analysis of Programs," POPL,
  DOI: 10.1145/512950.512973.
- [GALOIS] Cousot and Cousot, 1979, "Systematic Design of Program Analysis
  Frameworks," POPL, DOI: 10.1145/567752.567778.
- [SARIF] OASIS, "Static Analysis Results Interchange Format Version 2.1.0,"
  official standard, https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html.
- [OPENTELEMETRY] OpenTelemetry authors, "OpenTelemetry Specification,"
  official docs, https://opentelemetry.io/docs/specs/otel/.
- [TEMPO_DOCS] Grafana Labs, "Tempo documentation," official docs,
  https://grafana.com/docs/tempo/latest/.
- [PYROSCOPE_DOCS] Grafana Labs, "Pyroscope documentation," official docs,
  https://grafana.com/docs/pyroscope/latest/.
- [GLITCHTIP_DOCS] GlitchTip maintainers, "GlitchTip documentation," official
  docs, https://glitchtip.com/documentation/.
- [LOKI_DOCS] Grafana Labs, "Loki documentation," official docs,
  https://grafana.com/docs/loki/latest/.
- [VICTORIAMETRICS_DOCS] VictoriaMetrics, "VictoriaMetrics documentation,"
  official docs, https://docs.victoriametrics.com/.
- [OPENAPI] OpenAPI Initiative, "OpenAPI Specification," official docs,
  https://spec.openapis.org/oas/latest.html.
- [PYDANTIC] Pydantic maintainers, "Pydantic documentation," official docs,
  https://docs.pydantic.dev/latest/.
- [DJANGO] Django Software Foundation, "Django documentation," official docs,
  https://docs.djangoproject.com/.
- [TYPESCRIPT] Microsoft, "TypeScript Handbook," official docs,
  https://www.typescriptlang.org/docs/handbook/intro.html.
- [POSTGRES] PostgreSQL Global Development Group, "Explicit Locking," official
  docs, https://www.postgresql.org/docs/current/explicit-locking.html.
- [LIBFUZZER] LLVM Project, "libFuzzer: a library for coverage-guided fuzz
  testing," official docs, https://llvm.org/docs/LibFuzzer.html.
- [MUTMUT] mutmut maintainers, "mutmut documentation," official docs,
  https://mutmut.readthedocs.io/.
- [STRYKER] Stryker Mutator, "Stryker mutation testing documentation,"
  official docs, https://stryker-mutator.io/docs/.
- [CARGO_MUTANTS] cargo-mutants maintainers, "cargo-mutants documentation,"
  official docs, https://mutants.rs/.
- [CLIPPY] Rust project, "Clippy documentation," official docs,
  https://doc.rust-lang.org/clippy/.
- [BAZEL_BEP] Bazel project, "Build Event Protocol," official docs,
  https://bazel.build/remote/bep.
- [AWS_CODEBUILD] Amazon Web Services, "AWS CodeBuild User Guide," official
  docs, https://docs.aws.amazon.com/codebuild/latest/userguide/welcome.html.
- [HYPOTHESIS] Hypothesis maintainers, "Hypothesis documentation," official
  docs, https://hypothesis.readthedocs.io/.
- [PROPTEST] proptest maintainers, "proptest book," official docs,
  https://proptest-rs.github.io/proptest/.
- [NEXTEST] nextest maintainers, "cargo-nextest documentation," official docs,
  https://nexte.st/.
- [RUFF] Astral, "Ruff documentation," official docs, https://docs.astral.sh/ruff/.
- [PROMETHEUS_EXPOSITION] Prometheus authors, "Exposition formats," official
  docs, https://prometheus.io/docs/instrumenting/exposition_formats/; repo spec
  `docs/specs/fr-prometheus-exposition.md`.
- [PROMETHEUS_MONITORING] Repo spec, "Prometheus monitoring stack,"
  `docs/specs/fr-prometheus-monitoring.md` (covers the `prometheus-client`
  registry and the `metrics_ranking`/`metrics_retrieval`/`metrics_embeddings`/
  `metrics_workers` modules).
- [REGRESSION_GATE] Repo module, "Benchmark regression gate,"
  `backend/apps/benchmarks/services/regression_gate.py`.
- [ADBC] Apache Arrow project, "ADBC: Arrow Database Connectivity," official
  docs, https://arrow.apache.org/adbc/; repo spec `docs/specs/fr-adbc-arrow-reads.md`.
- [PYO3] PyO3 maintainers, "PyO3 user guide," official docs,
  https://pyo3.rs/.
- [MATURIN] maturin maintainers, "maturin user guide," official docs,
  https://www.maturin.rs/.
- [INSTA] insta maintainers, "insta: snapshot testing for Rust," official docs,
  https://insta.rs/.
- [LOOM] loom maintainers, "loom: concurrency permutation testing for Rust,"
  official docs, https://docs.rs/loom/.
- [CARGO_FUZZ] Rust Fuzzing Authority, "cargo-fuzz book," official docs,
  https://rust-fuzz.github.io/book/cargo-fuzz.html.
- [MCCABE] McCabe, 1976, "A Complexity Measure," IEEE Transactions on Software
  Engineering, DOI: 10.1109/TSE.1976.233837.
- [COGNITIVE_COMPLEXITY] G. Ann Campbell, 2018, "Cognitive Complexity: A new way
  of measuring understandability," SonarSource white paper,
  https://www.sonarsource.com/docs/CognitiveComplexity.pdf.
- [CHIDAMBER_KEMERER] Chidamber and Kemerer, 1994, "A Metrics Suite for Object
  Oriented Design," IEEE Transactions on Software Engineering,
  DOI: 10.1109/32.295895.
- [MARTIN_METRICS] Robert C. Martin, 2017, "Clean Architecture," package metrics
  (efferent/afferent coupling, instability, abstractness, the main sequence),
  ISBN: 978-0134494166.
- [IMPORT_LINTER] import-linter maintainers, "Import Linter documentation,"
  official docs, https://import-linter.readthedocs.io/.
- [JSCPD] jscpd maintainers, "jscpd: copy/paste detector," official repository,
  https://github.com/kucherenko/jscpd.
- [KANI] Model Checking with Kani, AWS, "The Kani Rust Verifier,"
  https://model-checking.github.io/kani/.
- [CREUSOT] Creusot maintainers, "Creusot: deductive verification of Rust,"
  https://github.com/creusot-rs/creusot.
- [PRUSTI] ETH Zürich, "Prusti: a Rust verifier,"
  https://www.pm.inf.ethz.ch/research/prusti.html.
- [MIRAI] Facebook/Meta, "MIRAI: an abstract interpreter for Rust MIR,"
  https://github.com/facebookexperimental/MIRAI.
- [GITLEAKS] gitleaks maintainers, "gitleaks: secret detection,"
  https://github.com/gitleaks/gitleaks.
- [SEMGREP] Semgrep, "Semgrep static analysis," https://semgrep.dev/docs/.
- [CYCLONEDX] OWASP, "CycloneDX SBOM specification," https://cyclonedx.org/specification/overview/.
- [SLSA] OpenSSF, "Supply-chain Levels for Software Artifacts (SLSA)," https://slsa.dev/.
- [SRE] Beyer, Jones, Petoff, and Murphy, 2016, "Site Reliability Engineering"
  (error budgets and resource isolation — the self-budget defaults), ISBN: 978-1491929124.
- [CONTINUOUS_DELIVERY] Humble and Farley, 2010, "Continuous Delivery" (shadow,
  canary, and progressive promotion — the 24-hour shadow and canary durations),
  ISBN: 978-0321601919.
- [ED25519] Bernstein, Duif, Lange, Schwabe, and Yang, 2012, "High-speed
  high-security signatures" (Ed25519, the rule-pack signing algorithm),
  DOI: 10.1007/s13389-012-0027-1.

## 17. Self-Score

| Dimension | Score | Justification |
|---|---:|---|
| Vision | 10 | The spec states a focused purpose: pre-execution validation that fills the 14 named gaps the runtime stack cannot see, with explicit non-goals so it never duplicates observability. |
| Scope | 10 | Scope is anchored on the 5,000,000 ELCV minimum target (Section 19), measured the non-gamable way (never raw lines), across the two locked backend languages (Python and Rust); Section 4.1 plus the Section 14.1 PG.01-PG.15 index ground it in what exists today versus what is planned, with per-slice acceptance. |
| Architecture | 10 | The design fits the modular monolith with an explicit Section 6.1 boundary contract (governance owns PreGate; PreGate reads other modules as text and AST, never by Python import; metrics register into the shared process-global registry so no Layer-2 module imports Layer-3), the in-process Rust PyO3/maturin extension (no sidecar, no C ABI), AutoIssues, the live local Prometheus plus VictoriaMetrics path, the Angular UI (no React rewrite exists), and the planned K8s and CodeBuild gates, and is honest about what is not built yet. |
| Sliceability | 10 | Phase 1 is a concrete 15-row index with dependencies and acceptance, with full bodies for PG.01-PG.05; the carving is mechanical for the rest. |
| Citations | 10 | Every named algorithm, tool, and standard has a DOI, ISBN, official URL, ePrint id, repo path, or plan cross-reference, including the reconciled tools (Hypothesis, proptest, nextest, ruff, Prometheus, regression gate, ADBC). |
| Project-rule fit | 10 | The spec matches the current repo: the Python-plus-Rust-only rule (no Haskell, C++, Go, or Lua; Rust hot paths via PyO3/maturin, no Python fallback), Vitest not Karma, the live PBT gate, the Prometheus exposition path with VictoriaMetrics running locally, `regression_gate.py` for Gap K, ruff and oxlint, the mutation ratchet, the `backend-quality` container split, the Angular UI (Plan #13's remove-Angular/React framing superseded), and the no-metaphor rule (literal name PreGate). |
| Self-test strategy | 10 | Section 13.1 gives exact per-tool commands and Section 13 wires PreGate kernels into the live PBT gate (Hypothesis plus proptest), the mutation ratchet (mutmut plus cargo-mutants), cargo-fuzz fuzzing, insta snapshot tests, loom concurrency checks, coverage thresholds, and the five TDD layers. Section 18 elevates this into a repo-wide, CI-enforced TDD-plus-ten-metrics layer that PreGate dogfoods. |
| Performance and observability | 10 | Latency, memory, trace, metric (Prometheus exposition plus local VictoriaMetrics, governance-owned `metrics_pregate.py` registering into the shared registry), log, profile, typed-error, SARIF, and AutoIssue budgets are all explicit and reuse the existing stack; Section 26 states the 10x and 100x scaling behaviour. |
| Risk and dependency | 10 | The risk table plus the Section 12.1 per-phase runbooks cover crashes, solver UNKNOWN, parser pinning, missing graph store, missing solver, budget caps, rule-pack failures, false positives, and unbuilt-stream sequencing. |
| Plain-English readability | 10 | Every advanced term, including the reconciled ones, is defined before use; the companion guide carries the operator-facing burden in plain English and states its readability target; the engine is named literally per the no-metaphor rule. |
| **Total** | **100/100** | Reconciled to the current repo and gap-closed: honest present-versus-planned baseline, concrete Phase 1 slice index, exact test commands, per-phase runbooks, and full plain-English coverage. Section 18 (TDD plus ten CI-enforced engineering metrics, each with a numeric threshold, enforcement mechanism, failure behavior, and continuous verification) and Section 19 (the non-gamable ELCV code-size metric and the ELCV-expressed 5,000,000 target) make the quality bar first-class and measurable. Sections 20-23 add formal verification (Kani/Creusot/Prusti/MIRAI + Z3/CVC5), 64-bit numerical accuracy and determinism, the security and supply-chain gates, and the registry-driven AutoIssue flow with a reserved quota and agent-review-before-fix; the runtime sibling spec `fr-observatory.md` carries the APM, helper-fleet, and Sentry-grade GUI. A 2026-06-13 architecture review (five independent reviewers) was then applied: the baseline was re-synced to the live repo (VictoriaMetrics is local; the UI is Angular, not React; the boundary hook is created, not extended), the Section 6.1 module-ownership contract resolves the layer-rule conflict, Sections 22.1-22.2 specify the capability-registry schema, the exact #2470/#2471 migration, and the new `proposed` status with the end-to-end finding flow, Sections 24-27 add the data-model field schemas, API contracts, 10x/100x scaling, and the threat model, and ELCV honestly reports `pending` until the ARW registry and code-USO normalizer ship — the score reflects this corrected, more accurate state. |

## 18. Quality Enforcement Layer

This layer applies to the WHOLE repository (Python, Rust, frontend), and PreGate
is held to it too — it dogfoods every gate. Thresholds are absolute and enforced
from day one; each gate is armed by a slice that first remediates existing
violations to green (Section 14.2). Every threshold lives in
`config/quality-thresholds.yaml`, and the existing `check-no-downgraded-gates.py`
blocks any weakening.

### 18.0 Test-Driven Development And Exhaustive Unit Testing

TDD is mandatory and evidenced. Every slice writes a failing test first, then the
code that turns it green, then refactors — recorded with the repo's TDD-strict
markers (timestamped red, green, refactor) and the live property-based-testing
gate (`//tools/quality:pbt`). No production line lands without a failing test
first.

"Exhaustive unit testing" is defined, not left to taste. A unit is exhaustively
tested only when it meets ALL of:

- branch coverage at or above the Metric 6 floor;
- mutation score at or above the Metric 7 floor;
- at least one property-based test wherever the logic is generative;
- the five-layer TDD coverage from `docs/TDD-STRICT-RULE.md` — edge cases,
  resource release, latency, smoke, and end-to-end.

Tooling is reused, not new: Python Hypothesis, mutmut, coverage.py; Rust proptest,
cargo nextest, cargo-mutants, cargo-llvm-cov, loom, insta; frontend Vitest and
Stryker. Quality tools run in `backend-quality`, `compiled-mutation-tools`, and
`frontend-mutation-tools`, never the runtime `backend`. This foundation is the
substrate the ten metrics measure; Metrics 6 and 7 are its hard numeric gates.

### 18.1 The Ten Engineering Metrics

Each metric states a measurable enterprise threshold, the enforcement mechanism,
the failure behavior, how compliance is continuously verified, and which part of
this spec it maps to. Failure behavior is uniform unless a row says otherwise:
(a) the `.githooks` chain hard-blocks the commit, (b) CI (GitHub Actions, and the
planned AWS CodeBuild master gate) hard-blocks the push, and (c) for the running
app the rollback analogue is that the release tag is blocked and the offending
commit reverted. Continuous verification is uniform: commit hooks → per-push CI →
master gate → the Code Quality page (Section 6.8) polling
`/api/governance/code-quality/` → a nightly recompute that files drift
AutoIssues → PreGate dogfooding its own code through every gate.

| # | Metric | Enterprise threshold (hard, day-one) | Enforcement | Failure behavior | Continuous verification | Maps to |
|---|---|---|---|---|---|---|
| 1 | Logical code size | Function ≤50 logical lines; file ≤1500; per-module ELCV budget; raw LOC is NOT the size metric — ELCV is (Section 19) | `check-file-size.py` (exists) + the ELCV gate | pre-commit + CI hard-block | Code Quality page + nightly recompute | Gap O / Section 19 |
| 2 | Production execution evidence | Every public code unit shows ≥1 production execution in the trailing 30 days, or carries a documented exemption (entrypoint, migration, disaster-recovery path); a net-new public symbol unexecuted after 2 release cycles gets ARW=0 | NEW `check-pregate-dead-code.py` reading the production-execution registry (Pyroscope + coverage contexts) | hard-block: ARW=0 code cannot count toward ELCV, and dead net-new public surface blocks the commit | "dead code (ARW=0)" list + AutoIssue `pregate_dead_code` | ARW (Section 19), Gap L |
| 3 | Cognitive complexity ceiling | Cognitive ≤15; cyclomatic ≤10; nesting ≤4; arguments ≤7 | `ruff` C901 (cyclomatic) + SonarQube/clippy cognitive + NEW `check-pregate-complexity.py` | pre-commit + CI hard-block | complexity tile; feeds SCW | SCW (Section 19) + Section 6.2 |
| 4 | Code churn isolation | ≤1 primary module + ≤200 out-of-scope files per push; a commit spanning >3 modules needs a declared cross-cutting marker; top-5% churn files require tests + extra review | `lint-all.ps1` step 10 (exists) + NEW `check-pregate-churn.py` (git-history fan-out) | hard-block on unmarked multi-module churn | churn heatmap; AutoIssue on hotspot | new gate, Section 18.1 |
| 5 | Defect density | ≤1.0 critical/high defect per 1,000 ELCV units (KELCV), trailing 90 days; the gate is only ARMED once KELCV ≥ 1.0 and is advisory below that, so a near-zero ELCV denominator before PG.E5 lands cannot spuriously hard-block every merge | NEW `code_quality` service: (GlitchTip + SonarQube blockers + open agent AutoIssues) ÷ KELCV | exceeding ⇒ block new feature merges (fix-first) + block the release tag | density tile + trend | new gate; ties Section 19 to GlitchTip/SonarQube |
| 6 | Branch coverage | ≥85% branch + ≥90% line backend per module; Rust ratchet → 95%; frontend ≥85% branch / 95% line; PreGate rule kernel ≥95% branch | `check-per-module-coverage.py` + `check-coverage-erosion.py` (exist), with branch floors added | pre-commit + CI hard-block; ratchet only rises | coverage tile + per-module table | Section 18.0 / CODE-COVERAGE-RULES.md |
| 7 | Mutation score | ≥90% Python; ≥95% Stryker frontend; Rust cargo-mutants ratchet → 90%; PreGate kernel ≥95% | `check-mutation-score.py` ratchet (exists) | pre-push hard-block | mutation tile | Section 18.0 / Section 13 |
| 8 | Module coupling | No upward or sibling cross-module import outside `api.py` (Layer 1→2→3); efferent fan-out ≤20 external module deps; no cross-language direct calls | `check-no-cross-language-import.py` (exists) + NEW `check-modular-monolith-boundaries.py` + `import-linter` (`.importlinter`) | pre-commit + CI hard-block | coupling tile; feeds SCW | Gap B + SCW (Section 19) |
| 9 | Code duplication | ≤3% duplicated logical blocks system-wide; ZERO new 6+ logical-line duplicate blocks | NEW `check-pregate-duplication.py` driving the USO engine — EXTENDS `papertrail_dedup` with a new code-token normalizer over the Tree-sitter parse (new work, not a drop-in; depends on PG.03b) | hard-block on any new duplicate block | duplication tile | USO (Section 19) |
| 10 | Build + test time | Pre-commit fast gate ≤5 min; changed-file test suite ≤2 min; full master gate ≤15 min; any single unit test >1s flagged; >10% wall-time regression blocks | `//tools/quality:pbt` budget (exists) + NEW `check-pregate-build-time.py` + `regression_gate.py` extended to wall-time | hard-block locally; nightly-shed for the heavy master gate | build/test-time trend | Section 10 / Gap K |

Each metric is also a rule pack (Section 9) with its own AutoIssue picker source,
so the operator sees which gate is noisy at a glance.

### 18.2 The `config/quality-thresholds.yaml` Schema

Every threshold the ten gates and the self-budget use lives in one new file,
`config/quality-thresholds.yaml`. It does not exist yet; the first quality-gate
slice creates it, and `ThresholdEntry` rows back it (Section 22.1). The existing
`check-no-downgraded-gates.py` parses it and blocks any weakening. Schema:

```yaml
version: 1
metrics:
  branch_coverage:        { value: 85,   unit: percent,   ratchet: up }
  line_coverage:          { value: 90,   unit: percent,   ratchet: up }
  mutation_score:         { value: 90,   unit: percent,   ratchet: up }
  cognitive_complexity:   { value: 15,   unit: count,     ratchet: down }
  cyclomatic_complexity:  { value: 10,   unit: count,     ratchet: down }
  function_lines:         { value: 50,   unit: count,     ratchet: down }
  file_lines:             { value: 1500, unit: count,     ratchet: down }
  efferent_coupling:      { value: 20,   unit: count,     ratchet: down }
  duplication_pct:        { value: 3,    unit: percent,   ratchet: down }
  defect_density_kelcv:   { value: 1.0,  unit: per_kelcv, ratchet: down, arm_above_kelcv: 1.0 }
  build_time_master_min:  { value: 15,   unit: minutes,   ratchet: down }
self_budget:
  cpu_pct_sustained:      { value: 10,   unit: percent }
  resident_memory_mb:     { value: 256,  unit: megabytes }
  foreground_p99_guard:   { value: true, unit: bool }
```

Each key has a value, a unit, and a ratchet direction (`up` = a floor that only
rises, `down` = a ceiling that only tightens). A change is reviewable in one diff,
and a downgrade is blocked. The `self_budget` defaults follow resource-isolation
practice [SRE]. The DEFAULT-ON rule applies: every key ships with a sensible
non-zero starting value, seeded by the gate slice that adds it.

## 19. Effective Logical Code Volume (ELCV)

Raw lines of code are explicitly disallowed as the primary size metric: they are
trivially gamed by formatting, duplication, or generated scaffolding. PreGate
measures Effective Logical Code Volume instead — deduplicated, runtime-validated,
complexity-weighted executed logic — computed deterministically in CI by the Rust
extension, never by developer estimation.

### 19.1 The Four Inputs

- Logical Execution Units (LEU): the count of non-trivial control-flow nodes in
  the AST — a branch, loop, state transition, or function-level decision
  boundary. Comments, whitespace, repeated patterns, and boilerplate are
  excluded; only executable logic counts. Built on the Tree-sitter parse
  (Section 8) [TREE_SITTER], with a Python `ast` bridge until the Rust parser
  lands, and on McCabe's control-flow basis [MCCABE].
- Unique Semantic Operations (USO): a deduplicated count of distinct operations
  after normalization. Two code paths implementing identical logic across modules
  count as one USO, so duplication cannot inflate size. This EXTENDS the
  `papertrail_dedup` MinHash/LSH engine [MINHASH] [LSH] — it is not a drop-in reuse.
  That crate today hashes 5-character shingles of error text, so USO adds a new
  code-token normalizer (over the Tree-sitter parse, so that `for i in range(n)`
  and `for j in range(m)` collapse and formatting does not leak) plus a new bound
  function for code-structural dedup. USO therefore depends on the Tree-sitter
  parser (Phase 2 / PG.03b). The same extended engine powers Metric 9 (duplication).
- Active Runtime Coverage Weight (ARW): a weight from 0 to 1. A unit contributes
  only if it executed in production telemetry within a defined window (default 30
  days). Unexecuted or dead code weighs 0 and is flagged for removal, so dead code
  and unused libraries cannot inflate size. This needs a per-symbol
  production-execution registry that does not exist yet: Pyroscope [PYROSCOPE_DOCS]
  gives live profiles, not a queryable 30-day per-symbol history, so PG.E3 builds
  the registry from Pyroscope plus coverage dynamic contexts. Until the registry
  has a full window of data, a unit's ARW is `unknown` and is excluded from the
  target — never silently treated as 0 (which would wrongly mark live code dead) and
  never as 1 (which would inflate). ARW powers Metric 2.
- Structural Complexity Weight (SCW): a penalty-adjusted multiplier from cognitive
  complexity [COGNITIVE_COMPLEXITY], cyclomatic complexity [MCCABE], and
  dependency fan-out [CHIDAMBER_KEMERER] [MARTIN_METRICS]. It peaks in a healthy
  complexity band and decays for both trivial filler (little real logic) and
  over-complex code (penalized, never rewarded), so writing convoluted code can
  never earn more volume credit. Built on Metrics 3 and 8.

### 19.2 Formula

`ELCV = (LEU × ARW × SCW) + USO`

Aggregated across the system as the sum over all units of
(LEU_i × ARW_i × SCW_i), plus the system-wide USO total. LEU is a count, ARW is in
0 to 1, SCW is a bounded multiplier, and USO is a deduplicated count. The
computation is deterministic — identical inputs always produce identical ELCV —
and runs in CI, never as a developer estimate.

### 19.3 Anti-Gaming Constraints

The following must NOT increase ELCV, and each is neutralized by a specific input:

- duplicated files or mirrored modules → collapsed to one by USO;
- auto-generated boilerplate without runtime execution → ARW = 0;
- vendored third-party code → excluded set, never counted;
- formatting or whitespace changes → not a LEU;
- synthetic wrappers that add no new execution path → no new LEU and no new ARW.

Any commit whose ELCV rises without a matching rise in executed, unique, and
behaviorally distinct runtime logic is a build failure, blocked by
`check-pregate-elcv.py` in the pre-commit chain and re-checked in CI.

### 19.4 The 5,000,000 Target, Expressed As ELCV Only

The 5,000,000 target is a cumulative, deduplicated, runtime-validated ELCV
threshold across the entire system — never raw repository size. Progress is
reported as ELCV growth per release cycle on the Code Quality page (Section 6.8).
Because ARW is at most 1 and USO removes duplicates, ELCV is much smaller than raw
line count, so 5,000,000 ELCV is a long-horizon, whole-system target tracked by
growth per release, with no artificial deadline.

Not computable today (honest status). Because ARW (the runtime-execution registry,
Section 19.1) and the code-structural USO (Section 19.1) have no data source until
PG.E3 and PG.E2 ship, the whole-system ELCV — and therefore any reading of progress
toward 5,000,000 — is not computable yet. Until those slices land and ARW coverage
passes its configured threshold, the Code Quality page shows ELCV as `pending`,
never a fabricated number. 5,000,000 ELCV is a measured target, not a live gauge
yet; the spec says so rather than implying a number exists today.

Regression detection: an ELCV decrease caused by refactoring, deduplication, or
dead-code removal (USO steady while LEU or ARW falls) is recorded as healthy and
is not a failure. An ELCV decrease accompanied by a drop in USO — distinct
operations lost — with no matching deprecation record is flagged as a possible
functionality regression for review. PreGate never treats honest shrinkage as a
failure, and never lets silent functionality loss pass unflagged.

### 19.5 Why 5,000,000 ELCV Is Aggressive — And Why It Is Built In Slices

5,000,000 ELCV is a deliberately aggressive target, for three reasons that are the
whole point of the metric:

- It is dense, not padded. One ELCV unit is a real decision point (LEU) that
  actually ran in production (ARW above 0), counted only once across the system
  (USO), at a healthy complexity (SCW). Comments, blank lines, boilerplate,
  duplicates, dead code, and convoluted code contribute little or nothing, so one
  ELCV unit represents far more real, exercised behavior than one raw line.
  5,000,000 ELCV therefore likely corresponds to many millions of raw lines of
  genuinely-executed, non-duplicated logic — the scale of a large platform.
- It cannot be reached by gaming. Because duplicates collapse to one, unrun code
  weighs zero, and complexity is penalized, the number rises only when real,
  unique, executed behavior is added. Every increment is earned.
- It is whole-system and cumulative. 5,000,000 ELCV is the sum of every honest
  increment across the entire codebase over the program's life, not the size of
  any one component.

This is exactly why the target is reached in slices, never in one shot. No human
and no AI model produces 5,000,000 ELCV of real logic in a single pass, and this
spec never asks for that. The roadmap is 80 to 150-plus independently-shippable
slices (Section 14), each a bounded unit of about 5,000 to 15,000 lines of change,
each written test-first and each made to pass all ten quality gates (Section 18)
before it lands. A capable AI coding agent — the project's Claude and high-effort
Codex agents, for example — completes one such slice in a working session: design,
tests, code, green gates, proof. ELCV then grows monotonically per release
(Section 19.4), and 5,000,000 is the compounding total of those many small,
verified increments over the 18-to-24-month-and-beyond horizon, with no artificial
deadline.

One honest caveat. ELCV counts only executed, distinct production logic, so the
system can reach 5,000,000 ELCV only if it genuinely accrues that much real,
behaviorally-distinct functionality. If the app's true scope turns out smaller,
ELCV plateaus below 5,000,000 — and that is reported honestly as a plateau, never
hidden or faked. That honesty is the feature: the target pulls work toward real
functionality, and the metric refuses to let slice count, copy-paste, or
scaffolding pretend the system is bigger than the behavior it actually runs.

## 20. Correctness, Formal Verification, And 64-Bit Math

PreGate validates that the app's logic is correct, not just well-shaped. Sections
20-22 are pre-execution (commit/CI) validation; the runtime counterparts live in
the sibling spec `docs/specs/fr-observatory.md`.

Formal verification uses Rust's real tools, not Lean 4 (which does not run in
Rust). For security-critical and ranking-correctness paths only — never the whole
app — PreGate generates obligations for:

- **Kani** [KANI] — bounded model checking of Rust (array bounds, overflow,
  unwrap-safety);
- **Creusot / Prusti** [CREUSOT] [PRUSTI] — deductive verification of Rust
  contracts (pre/post-conditions);
- **MIRAI** [MIRAI] — abstract-interpretation taint and panic analysis;
- **Z3 + CVC5** (already in Gap E) — SMT cross-check of the generated obligations.

A solver UNKNOWN never auto-rejects; it routes to the Plan #17 Review queue.

| # | Check | Threshold / rule | Mechanism | Failure |
|---|---|---|---|---|
| 1 | 64-bit numerical accuracy | f64 everywhere in business logic + ranking; no silent f32 downcast; ULP-tolerant test assertions (never `==`); compensated (Kahan) summation for score aggregation | Rust types + a PreGate rule pack + property tests | hard-block |
| 2 | Determinism | ranking/scoring is bit-reproducible given the same inputs + seed (fixed seeds, sorted iteration, no hash-order dependence) | property test + CI replay | hard-block on non-determinism |
| 3 | Ranking-weight invariants | every weight in its declared range; normalization holds; no NaN/Inf; monotonicity where required (a better link cannot score lower) | SMT + property tests | hard-block |
| 4 | Algorithm reference oracle | each algorithm has a recorded/slow reference; the fast Rust path matches within tolerance | parity test | hard-block on divergence |
| 5 | Hidden-O(n²) / complexity regression | fitted growth at 3 input sizes stays within declared big-O; no nested loop over the same collection in a hot path | empirical scaling test + static pass | hard-block |
| 6 | Frontend↔backend numeric correctness | a value shown in the UI equals the API's f64 under the declared rounding rule | contract test (extends Gap C) | hard-block |
| 7 | Float-safety lints | no `==`/`!=` on floats; no NaN-propagating compare in ranking; explicit rounding at API boundaries | ruff + clippy + rule pack | hard-block |
| 8 | Units / dimensions | newtype wrappers so a "days" value can never be added to a "score" | Rust newtypes + lint | hard-block |

Determinism replay boundary (Check 2). The replay fixes the ranking seed and
freezes the genuinely-variable external inputs — the GA4, GSC, and Matomo
snapshots and the autotuned weight set — to a recorded fixture, so it tests the
seed-controlled core, not the changing environment. Without that boundary a naive
replay would flake on live data and wrongly report non-determinism.

## 21. Security, Supply-Chain, Frontend, Docs & Domain Gates

Pre-execution gates beyond the 14 gaps and the ten metrics. Each is a rule pack
with its own picker source and reuses an existing tool where one is present.

| Area | Gate | Tool | Failure |
|---|---|---|---|
| Secrets | no new secret in diff or history | gitleaks / trufflehog [GITLEAKS] | hard-block |
| SAST | static security findings | bandit (exists) + cargo-geiger (unsafe Rust) + semgrep [SEMGREP] | hard-block on high severity |
| Dependency CVEs | no critical CVE in deps | pip-audit / cargo-audit / npm-audit (exist) + Trivy | block release |
| License compliance | only allowlisted licenses | license scan (deny unknown/incompatible) | hard-block |
| SBOM | bill of materials per release + diff | CycloneDX [CYCLONEDX] | n/a (artifact) |
| Supply-chain provenance | signed maturin/wasm artifacts; no lockfile drift | SLSA-style signing [SLSA] + lockfile audit | hard-block on drift |
| Data quality (static) | null/outlier/range/cardinality rules on content + signals | rule pack | block ingest path |
| Label/target leakage | no future/target signal leaks into a ranking feature | static dataflow | hard-block |
| Embedding/index integrity | FAISS/pgvector dim match; no NaN vectors; count parity | rule pack | hard-block |
| DB (static) | no N+1 pattern; no new seq-scan on large tables; online-safe + reversible migrations | query-count test + EXPLAIN + migration check | hard-block |
| Concurrency (static) | lock-ordering analysis prevents cross-resource deadlock | static pass | hard-block |
| API (static) | versioning + deprecation policy honored (sunset headers, window) | contract rule pack | hard-block on breaking change |
| Frontend gates | accessibility (axe/WCAG AA), i18n completeness, per-route bundle-size budget, visual-regression diff | CI gates (their runtime/RUM counterparts surface in Observatory §5.4) | hard-block on regression |
| Docs | spec↔code drift; docstring/API-doc coverage; no broken internal link | drift + coverage + link check (extends Docs Freshness) | hard-block |
| Knowledge | auto-surface the relevant resolved lesson when an agent touches a file; lessons decay | extends `search_resolved_issues` | advisory |
| Domain (link app) | link-graph integrity (orphans, suggestion cycles, broken target URLs, PageRank sanity) + anchor quality (generic/over-optimized/duplicate) | rule pack | hard-block on broken graph |

## 22. AutoIssue Integration: Reserved Quota, Agent Review, Registry, Dedup

PreGate (and Observatory) feed findings into the AutoIssue system under these
rules, several of which fix things that are hardcoded today.

- **Registry-driven sources (fixes AutoIssue #2470).** `source` becomes a registry
  entry, not a 25-value hardcoded enum, following the existing `AutoIssueCategory`
  get-or-create pattern. Each subsystem registers its own source(s) with a
  `reserved_quota` field. The concrete registry schema and the exact #2470/#2471
  migration are specified in Section 22.1.
- **Reserved quota of 10.** On top of the normal session quota, 10 picks are
  reserved for "improve PreGate/Observatory itself" — extending, correcting, or
  adding subsystems — so self-improvement is always pickable.
- **Agent-review-before-fix.** Findings land `status=proposed`. An agent must
  then **approve** (and fix), **reject with a reason**, or **correct PreGate's own
  logic/code** when the finding is wrong. Agents never blind-accept; they are free
  to reject or correct a wrong hard-block and immediately improve the engine. The
  `proposed` status does not exist in the AutoIssue model yet; Section 22.2
  specifies its migration and the full step-by-step finding lifecycle.
- **False-positive feedback loop.** Every rejection/correction is recorded against
  the rule pack that produced it; a pack whose false-positive rate exceeds its
  threshold auto-demotes to shadow (the §9 lifecycle), so wrong rules stop blocking
  until fixed.
- **Deduplicate everything (two cooperating layers, stated precisely).** Layer 1 is
  exact canonical-fingerprint dedup via `upsert_dedup` — the mandatory path every
  picker already uses and the one a pre-commit hook forbids any new picker from
  bypassing. `upsert_dedup` does NOT itself run MinHash/LSH. Layer 2 is optional
  near-duplicate collapsing via the `papertrail_dedup` MinHash/LSH index, used today
  only on Rust findings. Making the near-duplicate layer apply to every finding is
  new integration work (fold the `DedupIndex` into an `upsert_dedup` pre-pass), not
  an existing guarantee — the spec names which is which so no slice assumes the
  near-dup pass already runs everywhere. A bug found by PreGate AND GlitchTip AND a
  failing test still collapses to one issue with three observations through Layer 1.
- **PreGate's own fast store.** A dedicated read-optimized store (the
  `agent_memory.db` SQLite pattern; the QuestDB/SQLite volumes are already
  allocated) holds findings, the dedup index, thresholds, and verification state,
  so agents can query cheaply to audit the engine.
- **Verification surface.** An agent-facing "is PreGate correct?" view + command
  lists recent findings with their evidence, the rule that fired, and parity to
  ground truth, with bulk approve/reject — making "verify it isn't making
  mistakes" a first-class operation.
- **Self-budget.** PreGate's analysis obeys the same resource contract as
  Observatory (`fr-observatory.md` Section 10) so it never slows the foreground.
  PreGate's per-run local budget (≤2 seconds incremental) and Observatory's
  collector budget are summed against that one Section 10 envelope — neither gets a
  separate full budget.

### 22.1 Capability Registry And The AutoIssue Source Migration (resolves #2470, #2471)

The capability registry is one small set of governance-owned tables holding every
dynamic source, metric, threshold, rule pack, and helper, so nothing is a hardcoded
enum. It follows the existing `AutoIssueCategory` get-or-create pattern. Field names
may change in implementation; the responsibilities are locked.

Registry tables:

- `AutoIssueSource`: `slug` (primary key, e.g. `pregate_arch_boundary`), `label`,
  `subsystem` (`pregate` / `observatory` / `legacy`), `reserved_quota` (integer,
  default 0), `active` (bool), `created_at`. Seeded by a data migration with all 25
  existing source names plus the seven quality packs and the `obs_*` sources.
- `MetricDescriptor`, `ThresholdEntry`, `RulePackEntry`, `HelperEntry`: the metric,
  threshold, rule-pack, and helper registries, each `get_or_create`-seeded and read
  through `apps.governance.api`. `ThresholdEntry` is the row-level backing for
  `config/quality-thresholds.yaml` (Section 18.2).

The `AutoIssue.source` migration (#2470), specified exactly:

- `source` stays a string column, widened from `CharField(max_length=16,
  choices=SOURCE_CHOICES)` to `CharField(max_length=64)` with the hardcoded
  `choices=` removed. Keeping it a string (not a foreign key) leaves the 25 existing
  values byte-for-byte stable and leaves the existing
  `uniq_autoissue_source_external_id` unique constraint over `source` unaffected.
- A validator checks `source` against the `AutoIssueSource` registry on write
  (unknown source → validation error), so the field is registry-governed without an
  FK rewrite.
- Forward data migration: create `AutoIssueSource`, seed the existing 25 names plus
  the new ones, then `AlterField` on `source`. No existing row changes value. This
  is one-way (the repo forbids rollback paths): the widened column plus registry are
  added and the old fixed-choice list is deleted in the same change.
- Frontend (#2471): replace the `'glitchtip' | 'pyroscope' | 'agent'` union in
  `auto-issues.service.ts` with `source: string`, fed by a new
  `/api/governance/auto-issue-sources/` registry endpoint; the client renders any
  registered source.

PG.01 carries this migration; no `pregate_*` ingestion runs before it lands.

### 22.2 The `proposed` Status And The End-To-End Finding Flow

The agent-review-before-fix flow needs a status the AutoIssue model does not have
today. `AutoIssue.STATUS_CHOICES` is currently `open`, `picked`, `fixing`,
`resolved`, `deferred` (verified). PG.01's migration adds `proposed` as the initial
status for any finding that must be reviewed before a fix, plus a `rejection_reason`
text field. The migration is one-way (new status added, no rollback path).

One finding's full path, naming the data shape and the owning module at each hop:

1. Detection — a rule pack in the Rust extension returns a typed finding (rule-pack
   id, file, line, severity, decision, evidence). Owner: `governance/pregate`.
2. SARIF — the finding is written as one SARIF v2.1.0 result. Owner:
   `governance/pregate`.
3. Dedup — keyed by canonical fingerprint and passed to `upsert_dedup` (Layer 1 of
   the Section 22 dedup model), which creates a new AutoIssue or merges an
   observation into an existing one. Owner: `auto_issues`, called through its
   `api.py`.
4. Proposed — a new AutoIssue lands `status=proposed`, `source=pregate_<pack>`.
   Owner: `auto_issues`.
5. Agent review — the agent **approves** (status → `picked`/`fixing`, then the
   normal fix flow), **rejects with a reason** (status → `resolved` with
   `rejection_reason` set and the rule pack's false-positive counter incremented),
   or **corrects the rule** (edits the rule pack; the finding closes when the
   corrected pack no longer fires). No blind acceptance.
6. GUI — the finding shows on the PreGate diagnostics page and, for runtime
   findings, the Observatory tab, grouped by source, with its status and evidence.

Every hop is idempotent on the canonical fingerprint, so re-running detection
updates the same row instead of creating duplicates.

## 23. Auto-Threshold Setting

PreGate sets sensible starting thresholds automatically (percentile baselines from
the first window of data) for everything it tracks, stores them in the
configurable threshold registry (not hardcoded), and re-tunes on drift. When a
tracked value breaches its threshold or behaves anomalously, PreGate auto-files a
deduped AutoIssue (`status=proposed`) for agent review. This mirrors the runtime
auto-baseline in Observatory §5.3 and shares the registry.

## 24. Data Model Field Schemas

Section 6.3 lists the six `Pregate*` table responsibilities; this locks their field
types, keys, indexes, and retention so a migration is testable. Per the
no-duplicates rule, every derived-artifact row carries `artifact_hash`,
`source_snapshot_hash`, and `rule_pack_version`, and is superseded (not duplicated)
on a repeat input.

| Table | Key fields (type) | Indexes | Retention |
|---|---|---|---|
| `PregateRulePack` | `slug` (PK), `version` (str), `signature_fp` (str), `lifecycle` (enum: shadow/canary/production/retired), `owner_runtime` (enum), `budget_tier` (enum), `source_slug` (FK→`AutoIssueSource`), `promoted_at` (dt) | `slug`, `lifecycle` | keep all (small) |
| `PregateRun` | `id` (PK), `source_snapshot_hash` (str), `commit_or_patch_hash` (str), `mode` (enum: local/codebuild), `status` (enum), `started_at`/`finished_at` (dt), `native_artifact_version` (str), `contract_version` (str) | `commit_or_patch_hash`, `started_at` | 90 days, then prune |
| `PregateFinding` | `id` (PK), `sarif_id` (str), `rule_pack` (FK), `file_path`/`line`, `severity` (enum), `decision` (enum: allow/warn/review/critical), `canonical_fingerprint` (str), `autoissue_id` (FK, null), `review_id` (FK, null), `override_id` (FK, null), `artifact_hash` (str) | `canonical_fingerprint`, `rule_pack` | supersede on `(canonical_fingerprint, rule_pack_version)` |
| `PregateContractSnapshot` | `id` (PK), `contract_kind` (enum: rest/openapi/pydantic/serializer/ts), `canonical_form` (json), `source_snapshot_hash` (str) | `(contract_kind, source_snapshot_hash)` unique | keep latest N per contract |
| `PregateProofObligation` | `id` (PK), `kind` (enum), `budget_ms` (int), `z3_result`/`cvc5_result` (enum: sat/unsat/unknown), `unknown_reason` (str, null), `review_id` (FK, null) | `kind` | 90 days |
| `PregateBlastRadius` | `id` (PK), `patch_hash` (str), `affected_tests`/`affected_modules`/`affected_contracts` (Roaring blob), `graph_run_id` (FK) | `patch_hash` | 90 days |

Retention is enforced by the existing `prune_test_artefacts`-style command extended
to the `Pregate*` tables; run artifacts attach to the K8S.17 source-snapshot hash
and expire through the existing retention path. No table grows unbounded.

## 25. API Contracts

All PreGate endpoints require `IsAuthenticated` (401 without auth, 403 without the
operator role) and return JSON. List endpoints paginate with the repo's standard
`?page=`/`?page_size=` (default 50, max 200) and accept `?source=`, `?severity=`,
and `?status=` filters. Errors use the standard problem shape
`{ "detail": "...", "code": "..." }`.

The JSON-tile shape (reused by `PrometheusSummaryView` and
`/api/governance/code-quality/`):

```json
{ "tiles": [ { "key": "mutation_score", "label": "Mutation score",
              "value": 91.4, "unit": "percent", "threshold": 90,
              "status": "pass", "sparkline": [] } ],
  "generated_at": "<iso8601>", "available": true }
```

Endpoints:

- `GET /api/governance/code-quality/` → the tile list above plus the ELCV gauge
  (`{ "elcv": "pending" | <float64>, "target": 5000000, "growth": [] }`).
- `GET /api/governance/pregate/diagnostics/` → availability, latest runs,
  per-rule-pack health and 30-day override rate, and solver-UNKNOWN counts.
- `GET /api/governance/pregate/findings/` → paginated, filterable findings.
- `GET /api/governance/auto-issue-sources/` → the source registry (resolves #2471).

`available: false` with an empty `tiles` array is returned when the Rust extension
is down, so the frontend shows the empty-state rather than stale numbers.

## 26. Scaling At 10x And 100x

The THINK-BEFORE-YOU-CODE rule requires the growth story to be stated, not assumed.

- Finding volume. At 10x findings the AutoIssues 256 MB cap (Plan #33) still holds
  because Layer-1 dedup collapses repeats to one row with N observations; at 100x,
  backpressure (Observatory §8 #53) batches and rate-limits AutoIssue creation and
  emits one overflow bulletin instead of thousands of rows.
- In-memory structures. CIR and Roaring-bitmap sets are per-run and freed at run
  end; they scale with the changed-file set, not the whole repo, so a 100x repo does
  not grow a single run's memory. The whole-system ELCV and topology recompute is
  the only whole-repo pass and runs nightly on a helper, never in the ≤2-second
  local path.
- Dedup cost. `papertrail_dedup` is MinHash plus LSH (sub-linear nearest-neighbour),
  so the near-duplicate corpus scales to 100x through banded LSH lookups rather than
  pairwise comparison; the index is bounded and pruned by retention.
- Master gate. At 100x test volume the K8S.20 shard formula spreads work across the
  cluster and the heaviest packs shed to nightly (Section 12.1 Phase 6); the
  ≤15-minute budget is held by sharding, never by silently skipping checks.

## 27. Threat Model

PreGate runs in-process and can hard-block commits, so its own attack surface is
governed.

- Rule-pack trust. A rule pack is signed; the trust root is a project-held signing
  key stored outside the repo (the existing secret store), the algorithm is Ed25519
  [ED25519], and the loader verifies the signature before load. On signature failure the pack
  is refused and an AutoIssue is filed (Section 12.1 Phase 5) — it is never loaded
  "to see if it works."
- Authorization. Only the operator role may change a `ThresholdEntry`, promote a
  rule pack past shadow or canary, or edit `config/quality-thresholds.yaml`; every
  such change is written to the Observatory immutable audit log
  (`fr-observatory.md` §5.9: who, when, why). The `check-no-downgraded-gates.py`
  hook blocks a threshold weakening regardless of role.
- Blast radius — malicious rule pack. Because a pack runs in the Rust extension and
  can block commits, an unsigned or unreviewed pack cannot reach production: it must
  pass signature verification, 24h shadow, and 24h canary, and a high false-positive
  rate auto-demotes it to shadow (Section 9). A pack cannot read secrets outside the
  governance allowlist (Gap I applies to PreGate's own code too).
- Blast radius — compromised helper. Off-prem helpers receive short-lived tokens and
  Redis-results-only credentials, never database credentials and never the signing
  key (`fr-observatory.md` §6); a `db_heavy` or `low_latency` job is refused
  (fail-closed) on a shared-hosting transport, so a compromised shared host cannot
  reach the database or run latency-sensitive ranking work.

[SPEC CITED: feature=fr-code-validation-engine kind=technical_doc id=https://tree-sitter.github.io/tree-sitter/ verified_at=2026-06-13]
