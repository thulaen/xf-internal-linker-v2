# FR - Code Validation Engine

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## 1. Summary

The Code Validation Engine, shortened to CVE in this document, is a
pre-execution code safety feature for the XF Internal Linker app. In this
project, CVE means Code Validation Engine, not the public vulnerability database
with the same initials. It checks code changes before they run, before they are
committed, and before they reach the master gate. It is not a replacement for
GlitchTip, Pyroscope, Tempo, Loki, VictoriaMetrics, SonarQube, NewRelic, or any
other existing runtime or quality surface. It fills the gaps those systems
cannot see because those systems mostly report what happened after code ran.

This spec replaces the older draft at
`C:\Users\goldm\OneDrive\Pictures\Deterministic_Validation_Engine_Plan.md`.
The old draft aimed at an oversized single-language monolith and a tiny legacy
hardware target. That framing is rejected. The realistic target is a
300,000 to 500,000 line polyglot system spread across the six locked languages
from Plan #40 and Plan #42: Haskell, C++, Go, Rust, Lua, and Python. The engine
is built over 18 to 24 months in six phases and 80 to 150 shippable slices.

The most important design choice is tight app integration. CVE is not a side
tool that agents run when they remember it. It is part of the governance module,
the AutoIssue work queue, the paper-trail evidence chain, the existing hook
chain, the Lua PreToolUse advisor layer, the React diagnostics route planned by
Stream F2, the K8s Bazel sharding plan, and the AWS CodeBuild master gate. Every
finding is visible in the app, deduped through AutoIssues, exported as SARIF,
and attached to the same operator override and lesson flow that the rest of the
  project already uses. K8s means Kubernetes, the local distributed test
  cluster used by the project. AWS means Amazon Web Services, and CodeBuild is
  its managed build runner.

Two app-integration problems were found while writing this spec and were filed
as AutoIssues, as required by the repo rules:

- AutoIssue #2470: `backend/apps/auto_issues/models.py` currently stores
  `source` in a 16-character field with fixed choices. CVE needs dynamic
  sources shaped as `cve_<rule_pack_name>`.
- AutoIssue #2471: `frontend/src/app/core/services/auto-issues.service.ts`
  currently types AutoIssue sources as a fixed union. CVE needs the app client
  to accept registry-backed dynamic source names.

Those issues are not side notes. Phase 1 includes the database and client
changes that make CVE findings first-class app data.

## 2. Plain-English Terms

This table defines the advanced terms before the spec uses them. The guide at
`docs/architecture/code-validation-engine-guide.md` repeats the smaller set
needed by non-specialist readers.

| Term | Plain-English meaning |
|---|---|
| Galois connection | A mathematical pattern that lets us safely approximate a complicated state with a simpler one. CVE uses it only in abstract interpretation proofs. |
| Chaotic iteration | Repeatedly running an analysis pass until no new information is learned. CVE uses a bounded form and stops at the budget. |
| Hoare triple | A before-during-after specification for a code block. CVE uses it only for security-critical proof obligations. |
| Datalog clause | A small if-then rule that looks like "if A and B and C then conclude D." CVE uses it only when reachability queries across the call graph cannot be expressed by existing rule packs. |
| Semilattice | A set of values where any two can be combined to a third in a predictable way. CVE uses it inside abstract interpretation. |
| Roaring bitmap | A compressed bit-array format that makes large set operations fast. CVE uses it for changed-file and affected-test sets. |
| Compact region | A Haskell memory area you can throw away in one shot without garbage collection. CVE may use it as a speed optimization, not as a correctness requirement. |
| MinHash | A fast way to estimate how similar two big sets are. CVE uses it for near-duplicate code and comment corpora. |
| LSH, or Locality-Sensitive Hashing | A hash family that puts similar inputs into the same bucket on purpose. CVE uses it with MinHash for fast similarity search. |
| FFI, or Foreign Function Interface | Calling code in one language from another. CVE uses one stable C application binary interface, meaning a plain C-shaped boundary, for native libraries. |
| SMT, or Satisfiability Modulo Theories | Automated math solving over richer types than plain true-or-false logic. CVE uses SMT only for security-critical proof obligations. |
| UAST, or Unified Abstract Syntax Tree | One tree shape that can represent code from many languages. CVE builds UAST nodes from Tree-sitter parse trees. |
| CIR, or Compact Intermediate Representation | A memory-efficient form of the UAST used for analysis. CVE uses CIR in native kernels so Python never owns the hot path. |
| Dominator | Node A dominates node B if every path to B goes through A first. CVE uses dominators to prove authentication checks happen before sensitive operations. |
| SCC, or Strongly Connected Component | A group of nodes where every node can reach every other node. CVE uses SCCs to summarize cyclic call graphs. |
| Confusable or homoglyph | Characters that look the same but are different code points, for example Latin `a` versus Cyrillic `a`. CVE uses Unicode TR39 confusable detection for prompt-injection checks. |
| Taint flow | Tracking which values are influenced by untrusted input through the program. CVE uses it for security-critical paths only. |
| Proof obligation | A small math problem the engine generates and asks an SMT solver to prove. CVE sends proof obligations to Z3 and CVC5 within a time budget. |
| Aho-Corasick | A fast multi-pattern string search algorithm. CVE uses it to scan comments against a known prompt-injection phrase corpus. |
| Tree-sitter | An open-source library that produces concrete syntax trees for many programming languages. CVE uses its C parsers as the language parsing layer. |
| WebAssembly, or WASM | A sandboxed binary instruction format runnable inside other processes. CVE rule packs use the existing rulesd WebAssembly lifecycle. |
| SARIF | A standard JSON format for static analysis findings. CVE exports every finding as SARIF v2.1.0. |
| Blast radius | The set of code paths or tests affected by a given change. CVE computes this with the Plan #36 GraphAnalyzer and Apache AGE. |
| Equivalent mutant | A code mutation that does not change observable behavior, so tests cannot catch it. CVE treats this as an allowed quarantine case, not as a test failure. |

## 3. Vision And Non-Goals

### 3.1 Vision

CVE answers one question: "Before this code runs, can we prove it respects the
rules this app already depends on?"

The engine must:

- catch pre-execution semantic problems that the runtime stack cannot catch;
- turn every finding into an AutoIssue row or an operator-visible review item;
- run locally on the agent's working-directory diff in under two seconds for
  the incremental path;
- run the full master-gate suite in AWS CodeBuild in under 15 minutes inside
  the 11:00 to 23:00 user-time window from Plan #32;
- reuse the existing hook, Lua advisor, AutoIssue, observability, K8s, Bazel,
  CodeBuild, governance, and diagnostics surfaces;
- keep Python as orchestration only, never as the compute fallback for CVE
  analysis;
- keep security-critical proof work narrow, budgeted, and reviewable.

### 3.2 Non-Goals

CVE does not replace:

- GlitchTip runtime error capture;
- Pyroscope profiles;
- Tempo traces;
- Loki logs;
- VictoriaMetrics metrics and alerts;
- SonarQube code-smell scanning;
- NewRelic CI failure reporting;
- the existing 47-plus `.githooks/*.py` hard-block hooks;
- the Plan #41 Lua advisory layer;
- the AutoIssue and paper-trail system.

CVE also does not introduce:

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

| Plan | Lock title | CVE alignment |
|---|---|---|
| Plan #1 | pgvector plus Apache AGE local graph projection | CVE uses Apache AGE for graph-backed blast-radius queries and does not create a second graph store. |
| Plan #2 | Corrected OPQ design | CVE does not add embedding quantization work; similarity needs use existing embedding and dedup layers. |
| Plan #3 | Reliability pass | CVE routes unknown or unavailable states into typed errors and AutoIssues instead of silent decisions. |
| Plan #4 | Performance and capability roadmap | CVE treats performance proof as a first-class check and respects hot-path budget rules. |
| Plan #5 | Copy-paste plan | CVE enforces dead-code-on-replace and duplicate-artifact rules so copied replacements do not leave stale code. |
| Plan #6 | Forward-looking architecture backbone | CVE stays inside the modular monolith plus sidecar model rather than inventing a separate platform. |
| Plan #7 | Programmatic registries plus GUI | CVE adds rule-pack registry entries and app-visible status, not loose files hidden from the operator. |
| Plan #8 | NewRelic plus AutoIssues repair intake | CVE findings join AutoIssues; NewRelic continues to own CI failure intake. |
| Plan #9 | Modular Monolith doctrine | CVE lives under `apps/governance/code_validation_engine/` and uses the governance public boundary. |
| Plan #10 | PaperTrail enrichments | CVE rule changes, overrides, and promotion decisions cite paper-trail entries where the existing rule requires one. |
| Plan #11 | Modular Monolith refactor | CVE uses `api.py` for module boundaries and extends the existing boundary checker. |
| Plan #12 | Coverage hardening and lesson registry | CVE consumes coverage thresholds and logs lessons through AutoIssues. |
| Plan #13 | Frontend rewrite, remove Angular and Material | CVE UI lands in the React rewrite under `/diagnostics/code-validation/`; no new Angular screen is introduced. |
| Plan #14 | UI and UX design spec | CVE UI is a dense diagnostics tool with filters, chips, and drill-ins, not a marketing page. |
| Plan #15 | Ranking weights and autotuner | CVE does not change ranking weights; it can validate that weight changes cite performance proof. |
| Plan #16 | Testing Tools Dashboard | CVE run summaries and failing rule packs feed the testing dashboard when that stream owns the UI. |
| Plan #17 | Vibe-coding controls, Review queue, Docs Freshness, and new navigation | CVE sends solver UNKNOWN and ambiguous findings to the Review queue; docs ship as Docusaurus pages. |
| Plan #18 | rulesd WebAssembly rules and lifecycle | CVE rule packs reuse the rulesd WebAssembly lifecycle: shadow, canary, production, and rollback to shadow. |
| Plan #19 | Compiled-runtime ownership and zero Python compute fallback | CVE compute runs in Haskell, C++, Go, Rust, and Lua rule packs; Python orchestrates only. |
| Plan #20 | Errors page UI | CVE typed errors appear in the existing error surfaces through GlitchTip and the app diagnostics route. |
| Plan #21 | Prevention-focused cleanup and quality bar | CVE itself must pass mutation, coverage, hooks, and clean-working-tree requirements before production promotion. |
| Plan #22 | Embedding System | CVE does not introduce a new embedding store; near-duplicate needs reuse Plan #36 and Plan #33 lineage. |
| Plan #23 | Strategic Go expansion | Go owns transport, bounded worker pools, and sidecar wrapping patterns where measured concurrency benefits exist. |
| Plan #24 | UI feature catalog and trust calibration | CVE exposes false-positive rate, override rate, and rule-pack confidence in the trust dashboard. |
| Plan #25 | Hardware baseline and helper offload | CVE targets the Dell 3070 SFF i5-9500, 16 GB DDR4, and 1 TB SSD hardware lock, with no local GPU path. |
| Plan #26 | Haskell STM coordination service | CVE uses Haskell-tier patterns, tasty-hedgehog, tasty-golden, and dejafu for concurrent Haskell paths. |
| Plan #27 | Modular Monolith hardening | CVE strengthens architectural fitness checks rather than weakening module boundaries. |
| Plan #28 | Anchor Text Commander Haskell plus C++ FFI | CVE follows the same Haskell plus C++ native ownership style and the C boundary standard. |
| Plan #29 | Hot-path extraction critique | CVE requires benchmark proof for hot-path edits and validates macrobenchmark evidence for hot-path gap #34. |
| Plan #30 | Location and mobile linking | CVE does not alter location or mobile linking, but it can validate contract drift on those APIs. |
| Plan #31 | NewRelic Error Inbox and Link Intelligence Console | CVE does not duplicate NewRelic; CI failures remain there and in `source="gh_ci"` AutoIssues. |
| Plan #32 | ML/scoring layer and CodeBuild window | CVE master-gate runs only within the 11:00 to 23:00 user-time CodeBuild window and respects the budget cap. |
| Plan #33 | AutoIssues enterprise evolution and 256 MB cap | CVE is a consumer of the AutoIssues subsystem and must stay inside the 256 MB AutoIssues cap. |
| Plan #34 | Sidecar directives: gRPC over Unix-domain socket | `services/cve/` exposes gRPC over `/var/run/xf/cve.sock` and does not use shared-memory service IPC. |
| Plan #35 | Scoped fail-fast validation | CVE fast local checks fail fast only on deterministic hard blockers; review-class findings route to Review. |
| Plan #36 | Five dynamic C++ libraries | CVE reuses DeduplicationEngine, EmbeddingEngine kernels, and GraphAnalyzer rather than creating duplicate libraries. |
| Plan #37 | Sticky-document governance | CVE emits the required OpenTelemetry span attributes and propagates traces across gRPC. |
| Plan #38 | Memory-bounded C++ library techniques | Native CVE subsystems stay under the 128 MB worker-process envelope and use bounded structures. |
| Plan #39 | TDD and modular architecture ideas | CVE ships each slice with behavior-first tests and clear module boundaries. |
| Plan #40 | Lua ownership and sandbox refinement | CVE rule packs are Lua-owned where appropriate, hot-reloadable, signature-verified, and sandboxed. |
| Plan #41 | Lua cross-agent workflow advisory layer | CVE adds advisory rule packs to PreToolUse and commit-time phase validation for the seven workflow phases. |
| Plan #42 | C ABI Wrapper Standard | Every native CVE library exposes one stable C-shaped ABI; Python calls through `ctypes`, Go through cgo, and Haskell through `foreign import ccall unsafe`. |
| K8S.01-K8S.25 | K8s plus Bazel distributed test foundation | CVE adds Bazel test targets that use the source-snapshot protocol, sharding formula, coverage adapters, mutation adapters, and final merge job. |

## 5. Size, Runtime, And Hardware Envelope

### 5.1 Code Size

The full target is 300,000 to 500,000 lines over 18 to 24 months. The split is
large enough to be realistic for a multi-language validation platform and small
enough to fit this repository's locked architecture.

| Runtime | Target size | Ownership |
|---|---:|---|
| Haskell | 60,000 to 80,000 lines | Rule kernel, Aeson JSON parsers [AESON], decision algorithm, proof-obligation coordinator, result normalization. Lives at `services/cve/` as the fourth Haskell-tier member next to Sentinel, xfstm, and ATC. |
| C++ | 50,000 to 70,000 lines | Tree-sitter bindings, SIMD validators using the CPU vector-instruction pattern documented by vendor intrinsics guides [INTEL_INTRINSICS], Aho-Corasick scanner, Myers bit-parallel edit distance, CIR storage, and calls into Plan #36 DeduplicationEngine, EmbeddingEngine kernels, and GraphAnalyzer. |
| Go | 40,000 to 60,000 lines | Transport wrapper, bounded worker pools, health checks, and sidecar process coordination following Plan #23. |
| Rust | 20,000 to 40,000 lines | Hot-path acceleration only when benchmarks prove the need. Rust paths must run clippy and cargo-mutants through Docker-managed tooling [CLIPPY] [CARGO_MUTANTS]. |
| Lua | 10,000 to 25,000 lines | Rule packs for advisory checks, hot reload, signature verification, and WebAssembly packaging through Plan #18 and Plan #40. |
| Python | 30,000 to 50,000 lines | Orchestration only: Django models, REST API, management commands, app integration, AutoIssue ingestion, and `ctypes` calls. Lives under `apps/governance/code_validation_engine/`. |

### 5.2 Memory And Latency

The old tiny-memory target is removed. CVE uses the locked caps already in the
project:

- native subsystem cap inside the Django worker process: 128 MB from Plan #38;
- AutoIssues subsystem cap: 256 MB from Plan #33, with CVE as one consumer;
- Pyroscope profile cap: 100 MB from Plan #25 G-194;
- local incremental CVE scan: under two seconds on the agent's working-directory
  diff, matching the Plan #41 PreToolUse budget;
- full master-gate CVE suite: under 15 minutes on AWS CodeBuild inside the
  11:00 to 23:00 user-time window from Plan #32.

The hardware baseline is the Plan #25 Dell 3070 SFF with an i5-9500 CPU, 16 GB
DDR4 memory, and a 1 TB SSD. CVE must not assume a GPU path. Hardware-aware
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

CVE has three repo homes:

- `apps/governance/code_validation_engine/` for the app-facing governance
  module. This is where Django-facing models, serializers, API functions,
  management commands, and orchestration live.
- `services/cve/` for the Haskell plus native sidecar. It exposes the query API
  through gRPC over the Unix-domain socket `/var/run/xf/cve.sock`, following
  Plan #34.
- Plan #36 native libraries for C++ kernels when the logic belongs in
  DeduplicationEngine, EmbeddingEngine, or GraphAnalyzer instead of a new CVE
  library.

The governance module exposes only `apps.governance.api` to other Python
modules. CVE implementation files are private. Cross-module imports use the
`api.py` public surface from ADR 0002. Cross-module database foreign keys remain
allowed under ADR 0003, but Python imports do not bypass `api.py`.

### 6.2 Service Shape

`services/cve/` becomes the ninth sidecar in the locked sidecar list: Sentinel,
xfstm, ATC, xfgeo, rulesd, bullboard, snapshotd, RealtimeLinker, and CVE. ADR
0007 must be amended in Phase 1 to add CVE to the Haskell-tier list and to state
that CVE uses the same gRPC-over-Unix-socket service shape as the sidecar rules.

The service is Haskell-led. Haskell owns the rule kernel, Aeson parsing, the
decision algorithm, proof-obligation coordination, and result normalization.
C++ owns parsers and tight kernels. Go owns the sidecar process wrapper and
bounded worker pools where the Plan #23 concurrency pattern applies. Rust is
allowed only after a benchmark proves a hot path cannot meet its budget in the
existing native implementation. Lua owns rule packs where Plan #40 says Lua owns
hot-reloadable rule logic.

Every C++, Rust, Haskell, or Go library with a cross-language consumer exposes a
single stable C application binary interface, following the repo's C ABI
standard [C_ABI_SPEC]. Public structs use size and version fields, borrowed
buffers are length-delimited, errors return status codes with separate error
retrieval, and language-native object types never cross the boundary. Python
calls this boundary through `ctypes`; Go uses cgo; Haskell uses explicit
`foreign import ccall unsafe` [PYTHON_CTYPES] [GO_CGO] [GHC_FFI].

### 6.3 Data Model

Phase 1 adds a narrow governance-owned data model. API means application
programming interface: the callable surface another part of the app can use.
Exact field names can change
during implementation, but the data responsibilities are locked:

- `CveRulePack`: rule-pack name, version, signature fingerprint, lifecycle
  state, owner runtime, declared budget, source name, and promotion timestamps.
- `CveRun`: run id, source snapshot hash, git commit or dirty patch hash, local
  or CodeBuild mode, status, start and finish times, native artifact version,
  and contract version.
- `CveFinding`: SARIF id, rule-pack id, file path, line, severity, decision,
  canonical fingerprint, AutoIssue id, review id when applicable, and operator
  override id when applicable.
- `CveContractSnapshot`: canonical contract form for REST, gRPC, Protocol
  Buffers, OpenAPI, Pydantic, Django serializer, and TypeScript interface
  shapes.
- `CveProofObligation`: proof kind, budget, solver result, Z3 result, CVC5
  result, UNKNOWN reason, and Review queue id when needed.
- `CveBlastRadius`: patch hash, affected tests, affected modules, affected API
  contracts, and GraphAnalyzer run id.
- `OperatorOverride`: existing Plan #18 override table or a governance-owned
  equivalent if that table has not landed. CVE override commit markers link
  here.

No table may grow without a retention rule. Each row that represents a derived
artifact uses `artifact_hash`, `source_snapshot_hash`, and `rule_pack_version`.
If the same input appears again, CVE updates the existing row or supersedes it
according to NO-DUPLICATES.md. Run artifacts attach to the K8s source-snapshot
hash from K8S.17 and expire through the existing retention path.

### 6.4 AutoIssue Integration

CVE findings become AutoIssues, not a parallel issue store. Each rule pack gets
its own dynamic AutoIssue source named `cve_<rule_pack_name>`, for example
`cve_arch_boundary` or `cve_contract_drift`. This lets the operator see noisy
rule packs at a glance and lets the session ritual pick from each source. The
75-pick ritual count grows as rule packs are added, following the Plan #18
ritual model.

Because the current AutoIssue schema uses a fixed source list and a short source
field, Phase 1 must widen source handling before broad CVE ingestion:

- create or extend a source registry so dynamic sources are first-class;
- raise the source field length enough for `cve_<rule_pack_name>`;
- expose dynamic sources through `/api/auto-issues/`;
- update frontend clients to treat source as a registry value instead of a
  fixed string union;
- keep existing source names stable for GlitchTip, Pyroscope, Tempo, Loki,
  Faro, SonarQube, VictoriaMetrics alerting, Rust defect import, mutation,
  fuzz, contract, GitHub CI, and agent findings.

Every CVE operational problem also becomes an AutoIssue. Sidecar unavailable,
rule pack signature failure, solver budget exhaustion, K8s merge missing
artifacts, malformed SARIF, and importer failures all file or dedupe rows. If
backend filing is unavailable in a local hook, the existing findings buffer from
`fr-hook-finding-autoissue.md` is used and drained later.

### 6.5 Hook Integration

Pre-commit hard blocks already live in `.githooks/*.py`, with more than 47
hooks. CVE adds at most 8 to 12 new hooks. They are thin wrappers over the CVE
sidecar and existing AutoIssue filing helper, not a hundred new checks.

The planned hook set is:

- `check-cve-architectural-boundaries.py`;
- `check-cve-contract-drift.py`;
- `check-cve-migration-safety.py`;
- `check-cve-security-proof-queue.py`;
- `check-cve-prompt-injection-comments.py`;
- `check-cve-hallucinated-apis.py`;
- `check-cve-secret-env-reads.py`;
- `check-cve-performance-proof.py`;
- `check-cve-dead-code-on-replace.py`;
- `check-cve-workflow-phase.py`;
- `check-cve-agent-identity.py`;
- `check-cve-rule-pack-integrity.py`.

The hooks reuse `git diff` and the existing hook finding to AutoIssue path.
CVE does not write a bespoke diff parser. Hooks that detect deterministic hard
violations block the commit. Hooks that produce review-class uncertainty file a
finding and route to the Plan #17 Review queue.

### 6.6 Lua Advisor Integration

Plan #41 already has a Lua PreToolUse advisor layer, and the repo already has
`apps/governance/lua_runtime/` with a sandbox loader and advisory scripts. CVE
extends that layer with rule packs. It does not replace the layer.

The advisor path runs before the agent edits, so it can warn about likely
workflow or rule-pack problems earlier than a hook. It remains advisory. It
reminds, classifies, and explains. Hard-block enforcement stays in the
pre-commit hook chain.

Lua rule packs must obey the existing sandbox: no direct host libraries, no
direct file or operating-system calls, and all host access through granted
capabilities. Rule packs are hot-reloadable, signature-verified, and packaged
through the WebAssembly lifecycle from Plan #18 and Plan #40.

### 6.7 UI Integration

The current frontend still has an Angular `diagnostics` route, but Plan #13
locks the product direction to the React rewrite. CVE UI work must therefore
land in the Stream F2 React route `/diagnostics/code-validation/` and not add a
new Angular screen.

The CVE diagnostics page shows:

- current CVE availability: healthy, degraded, or unavailable;
- latest local and CodeBuild runs;
- rule-pack health, lifecycle state, version, signature, and budget use;
- open CVE AutoIssues grouped by `cve_<rule_pack_name>`;
- false-positive rate, computed as operator override rate over 30 days;
- slowest rule packs by p50, p95, and p99 latency;
- solver UNKNOWN counts routed to Review;
- K8s shard status and final merge report links for CVE Bazel targets;
- override markers and their linked OperatorOverride rows.

Until the React route exists, the app-visible minimum is the AutoIssues table
and diagnostics API. CVE must not hide findings in local files.

## 7. What CVE Checks

The existing observability stack already covers runtime errors, profiles,
traces, logs, metrics, code smells, and CI failures. CVE covers the gaps below.
Each gap maps to app integration, a rule-pack source, and a decision path.

### Gap A: Pre-Execution Semantic Checks

Existing systems mostly report after code executes. CVE runs semantic checks
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

- local advisory hints appear before edits when the Lua advisor can see the
  intent;
- deterministic violations block in `.githooks`;
- review-class findings go to Plan #17 Review.

### Gap B: Architectural Boundary Violations Beyond The Existing Hook

The repo already has `.githooks/check-module-boundaries.py`. CVE extends it
instead of replacing it. The expanded check covers cross-module imports outside
`api.py`, layering reversals, sidecar bypass, and direct private calls into
another module.

Implementation:

- Use Tree-sitter [TREE_SITTER] for import and call-site extraction.
- Use Tarjan's SCC algorithm, where an SCC is a group of nodes that can all
  reach each other, to summarize cyclic dependency groups [TARJAN_SCC].
- Use the modular monolith docs and ADRs 0001 through 0006 as the source of
  allowed boundaries.

App path:

- source `cve_arch_boundary`;
- hard-block when a forbidden import or sidecar bypass is deterministic;
- AutoIssue description names the caller, callee, expected public boundary,
  and suggested `api.py` move.

### Gap C: Breaking-Change Detection Across Contracts

CVE detects breaking changes in REST, meaning Representational State Transfer
HTTP APIs, gRPC, meaning Google's remote procedure call framework, Protocol
Buffers, OpenAPI, Pydantic, Django serializers, and TypeScript interfaces
[GRPC] [PROTOBUF] [OPENAPI] [PYDANTIC] [DJANGO] [TYPESCRIPT]. A contract is
the shape one part of the app promises another part can call or read.

Implementation:

- Build canonical contract forms for each source.
- Diff canonical forms with compatibility rules.
- Use GumTree source differencing, a structured source-code differ, when a
  language-aware tree diff is needed [GUMTREE].
- For Protocol Buffers, keep field numbers and optionality rules from the
  official docs [PROTOBUF].
- For OpenAPI, compare schema changes against the official OpenAPI
  Specification [OPENAPI].

App path:

- source `cve_contract_drift`;
- deterministic breaking removals hard-block;
- ambiguous compatibility changes route to Review;
- findings link to the contract snapshot and affected frontend/backend paths.

### Gap D: Database Migration Safety

CVE checks migration risk before the database sees it. It detects drop-column,
drop-table, irreversible alter, missing default, missing NOT NULL backfill, and
lock-escalation risk.

Implementation:

- Parse Django migration files and SQL with Tree-sitter [TREE_SITTER].
- Apply PostgreSQL lock and constraint rules from the PostgreSQL docs
  [POSTGRES].
- Reuse the existing migration-data-safety command where possible.

App path:

- source `cve_migration_safety`;
- deterministic destructive migration without approved evidence hard-blocks;
- valid but risky migration creates a Review item with required backfill,
  rollback, and lock notes.

### Gap E: Mathematical Safety Proofs For Security-Critical Paths

CVE uses mathematical proofs only for security-critical paths. It does not try
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

- source `cve_security_proof`;
- hard-block only when both solvers prove a deterministic violation within
  budget;
- UNKNOWN creates `CveProofObligation` plus Review queue item.

### Gap F: Test Impact Blast Radius

CVE computes which tests are invalidated by a patch. Blast radius means the set
of code paths or tests affected by a change.

Implementation:

- Use Plan #36 GraphAnalyzer for call graph and dependency graph operations.
- Use Apache AGE, the PostgreSQL graph extension, for graph queries [APACHE_AGE].
- Use openCypher query syntax through Apache AGE docs [OPENCYPHER].
- Store affected file and test sets with Roaring bitmaps, compressed bit arrays
  that make large set operations fast [ROARING].

App path:

- source `cve_blast_radius`;
- K8s local mode uses the result to choose incremental Bazel targets;
- UI shows "why this test was selected" through a call-graph path.

### Gap G: Prompt Injection Inside Code Comments

CVE detects prompt-injection text hidden in code comments. Prompt injection in
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

- source `cve_prompt_injection`;
- deterministic direct matches hard-block;
- near-duplicate matches warn locally and route to Review unless confidence is
  above the rule pack's production threshold.

### Gap H: Hallucinated APIs

CVE detects code where an AI added `foo.bar()` but `foo` has no method `bar` in
the codebase. This is common when a model invents a plausible method name.

Implementation:

- Use Tree-sitter [TREE_SITTER] to extract call expressions.
- Build scope-resolution tables and symbol tables per language.
- Compare call sites against local definitions, imports through `api.py`,
  generated clients, and known external dependencies.

App path:

- source `cve_hallucinated_api`;
- deterministic missing local methods hard-block;
- external dependency uncertainty goes to Review with the package and symbol
  name.

### Gap I: Unauthorized Environment Variable Reads

CVE detects new reads of restricted environment variables outside
`apps/governance/secret_allowlist.py`.

Implementation:

- Parse Python, TypeScript, Go, Rust, C++, Haskell, and Lua access patterns.
- Compare environment keys against the governance allowlist.
- Treat secret-like key names as high severity when the key is not listed.

App path:

- source `cve_secret_env_read`;
- deterministic unauthorized reads hard-block;
- finding includes the key, file, line, and allowlist path.

### Gap J: Cross-Language Contract Drift

CVE detects when Pydantic, gRPC, Protocol Buffers, and TypeScript declare
different shapes for the same app contract.

Implementation:

- Build canonical forms for each language contract.
- Compare required fields, optional fields, enum values, numeric ranges, and
  nullability.
- Use Datalog clauses, small if-then rules, only when cross-language
  reachability cannot be expressed by the existing rule-pack pattern
  [DATALOG].

App path:

- source `cve_cross_language_contract`;
- deterministic drift hard-blocks when it would break a caller;
- otherwise a Review item lists each contract source and the mismatched field.

### Gap K: Performance Regression Proof

CVE checks that every hot-path edit includes benchmark proof. A hot path is code
run often enough that slowdown matters to users or to the worker process.

Implementation:

- Read the existing Plan #21 Phase G and Plan #29 hot-path-gap #34
  macrobenchmark requirements.
- Check for benchmark evidence, profiling proof, and the required marker.
- Compare benchmark identifiers against touched native and Python paths.

App path:

- source `cve_performance_proof`;
- missing proof hard-blocks when the touched path is classified as hot;
- proof artifacts link to AutoIssue and diagnostics.

### Gap L: Dead-Code-On-Replace

CVE checks that when a function is replaced, the old version is deleted in the
same commit. This follows Plan #19 and Rule H.29.

Implementation:

- Use GumTree [GUMTREE] plus Myers bit-parallel edit distance, a fast edit
  distance algorithm, to detect replace patterns [MYERS].
- Use MinHash and LSH to catch near-duplicate old/new bodies [MINHASH] [LSH].
- Use Cuckoo filters, compact membership filters, to avoid repeatedly scanning
  known deleted bodies [CUCKOO].

App path:

- source `cve_dead_code_replace`;
- deterministic duplicate old implementation hard-blocks;
- false positives can use the CVE override marker.

### Gap M: Workflow Phase Validation

CVE validates the seven workflow phases from Plan #41: research, BDD, TDD,
implement, review, AutoIssues, and commit. BDD means behavior-driven
description in Given/When/Then form. TDD means test-driven development, where a
test is written before or alongside the code and the Red-Green-Refactor cycle is
recorded.

Implementation:

- Use the existing Lua advisor to remind during PreToolUse.
- At commit time, check that each phase artifact exists and is fresh.
- Reuse the repo's `TDD-STRICT-RULE.md`, paper-trail evidence rule, test-case
  rule, and code-review lesson rule.

App path:

- source `cve_workflow_phase`;
- missing deterministic phase evidence hard-blocks;
- advisory reminders stay non-blocking before the commit.

### Gap N: AI-Agent Identity Drift

CVE tracks which agent wrote which code. Agent identity drift means a commit
claims one agent context but the session evidence points to a different agent
or bypasses the required startup ritual.

Implementation:

- Require commit trailers naming the agent.
- Cross-check `AGENT-HANDOFF.md` session markers, including the 12-marker
  session-start ritual.
- Link findings to the agent, the session id, and the touched files.

App path:

- source `cve_agent_identity`;
- bypassed ritual markers hard-block;
- identity mismatch goes to Review if the evidence is ambiguous.

## 8. Multi-Language Parsing And Analysis

CVE uses Tree-sitter C parsers [TREE_SITTER]. It does not write a 200,000-line
parser per language. Each supported language gets one Bazel `cc_library`
mapper, about 6,000 lines including tests, that converts Tree-sitter output to
the CVE UAST and CIR.

Supported languages:

- Python;
- TypeScript;
- JavaScript;
- Go;
- Rust;
- C++;
- Haskell;
- Lua;
- SQL;
- YAML;
- JSON;
- Markdown;
- Dockerfile.

The CIR is stored in native memory with explicit budgets. Roaring bitmaps store
sets of file ids, symbol ids, rule ids, and affected test ids [ROARING].
Compact regions may be used in Haskell so whole run graphs can be released at
once [COMPACT_REGIONS]. If a future GHC 9.x deprecates compact regions, CVE
keeps working because compact regions are a latency optimization only. Removing
them may make the rule kernel two to three times slower, but it does not change
correctness.

## 9. Policy And Rule Packs

CVE does not introduce a bespoke Datalog runtime. Most policy lives in the
existing Plan #18 rulesd WebAssembly pattern and Plan #40 Lua rule packs. A
Datalog clause is added only for transitive reachability across the call graph,
where existing rule-pack patterns are not expressive enough [DATALOG].

Rule-pack lifecycle:

1. Author rule pack in the allowed Lua subset or native rule schema.
2. Compile or package through WebAssembly where the Plan #18 lifecycle requires
   it [WASM_CORE].
3. Sign the pack.
4. Run 24 hours in shadow mode.
5. Run 24 hours in canary mode.
6. Promote to production only after false-positive rate and latency are within
   budget.
7. If the pack misbehaves, return it to shadow status. Do not auto-delete it.

Each rule pack declares:

- name and `cve_<rule_pack_name>` source;
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

## 10. Execution Modes

### 10.1 Local Incremental Mode

Local mode runs on the agent's working-directory diff. It uses `git diff` and
the K8s source snapshot when distributed tests are involved. It does not use a
bespoke diff parser.

Local mode includes:

- Lua advisory rule packs before tool use;
- fast AST and text checks;
- selected medium cross-file checks;
- one-second proof obligations only for security-critical touched paths;
- AutoIssue filing for every finding;
- SARIF export for every finding.

Target: under two seconds for the incremental scan path.

### 10.2 Local K8s Mode

The K8s infrastructure at `C:\Users\goldm\OneDrive\Desktop\K8S\` runs CVE as
Bazel test targets.

CVE inherits:

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

AWS CodeBuild runs the full mutation, coverage, and cross-language CVE suite.
It respects the Step 5 budget lock and the Plan #32 time window. If the
CodeBuild budget reaches the 100 percent cap, the CVE master-gate suite skips
as required by the Step 5 lock. Local K8s incremental CVE still runs.

## 11. Observability

CVE emits observability through the existing stack only: OpenTelemetry, Tempo,
Pyroscope, GlitchTip, Loki, and VictoriaMetrics [OPENTELEMETRY] [TEMPO_DOCS]
[PYROSCOPE_DOCS] [GLITCHTIP_DOCS] [LOKI_DOCS] [VICTORIAMETRICS_DOCS].

Every CVE call from the Python adapter to the Haskell sidecar emits an
OpenTelemetry span. A span is one timed operation in a trace. The span carries
these attributes:

- `component_name`;
- `owner_runtime=haskell`;
- `fallback_used=false`;
- `runtime_artifact_version`;
- `runtime_contract_version`;
- `duration_ms`;
- `error_class`;
- `rule_pack_name`;
- `rule_pack_version`.

Tempo receives trace propagation across the gRPC boundary per Plan #37 idea 26.
Pyroscope profiles the sidecar continuously with a 100 MB profile cap. GlitchTip
captures typed errors:

- `HaskellUnavailableError`;
- `CompiledRuntimeContractError`;
- `CompiledRuntimeTimeoutError`;
- `CveRulePackError`;
- `CveProofObligationUnknown`.

Loki receives structured logs with:

- `run_id`;
- `rule_pack_id`;
- `file_path`;
- `line`;
- `severity`;
- `decision`, with values `allow`, `warn`, `review`, or `critical`.

VictoriaMetrics tracks:

- per-rule-pack p50, p95, and p99 latency;
- per-rule-pack false-positive rate, measured as operator override rate over a
  30-day rolling window;
- sidecar availability;
- proof UNKNOWN rate;
- AutoIssue filing failures.

Every finding has SARIF v2.1.0 output [SARIF] and a corresponding AutoIssue or
Review item.

## 12. Risk And Rollback Map

| Risk | Behavior | Rollback or recovery |
|---|---|---|
| `services/cve/` crashes | Python raises `HaskellUnavailableError`. Pipeline continues without CVE checks. | Operator sees "CVE unavailable" chip using the Plan #25 G-229 explanation library. AutoIssue is filed. |
| Z3 or CVC5 returns UNKNOWN beyond budget | CVE does not reject the change. | Route to Plan #17 Review queue and store `CveProofObligation`. |
| Tree-sitter upstream breaks | Version is pinned in `MODULE.bazel`. | Bump only through a paper-trail entry and golden test update. |
| GHC deprecates compact regions | Correctness unaffected. | Remove or replace compact-region optimization. Latency may degrade two to three times. |
| Rule pack misbehaves | WebAssembly sandbox, signature verification, shadow, canary, production lifecycle contains it. | Return the pack to shadow status. Never auto-delete it. |
| CodeBuild reaches 100 percent budget cap | CVE master-gate suite skips per Step 5. | Local K8s incremental scan still runs. AutoIssue records the budget skip. |
| Known false positive | Operator adds `[CVE OVERRIDE: rule_pack=<name> rule_id=<id> reason="..."]` in the commit body. | Override is logged to OperatorOverride and counted in false-positive rate. |
| AutoIssue filing fails | Hook helper writes to findings buffer where allowed. | Drain buffer next session. In CI, fail strict because soft filing is not allowed. |
| Dynamic CVE source unsupported | Current schema/client cannot show sources cleanly. | Phase 1 resolves AutoIssues #2470 and #2471 before broad rule-pack ingestion. |

## 13. Self-Test Strategy

CVE must satisfy the Plan #21 Quality Bar before production use. The engine is a
validator, so it must be harder on itself than on normal feature code.

Required test layers:

- Property-based testing with tasty-hedgehog, following Plan #26 Slice 3
  [HEDGEHOG] [TASTY].
  Property-based testing means generating many inputs to test a rule, not just
  hand-picking examples. The citation lineage follows QuickCheck
  [QUICKCHECK].
- Golden tests with tasty-golden for parser output, UAST output, CIR output,
  canonical contract snapshots, and proof obligations. A golden test compares
  output to a checked-in expected file [TASTY_GOLDEN].
- Mutation testing with MuCheck for Haskell, mutmut for Python, Stryker for
  TypeScript and JavaScript, Mull for C++, cargo-mutants for Rust, and
  go-mutesting for Go [MUCHECK] [MUTMUT] [STRYKER] [MULL] [CARGO_MUTANTS]
  [GO_MUTESTING]. Mutation testing changes code on purpose to prove tests catch
  real behavior changes.
- Fuzz testing with libFuzzer and AFL-style fuzzers for the patch parser,
  Tree-sitter wrappers, and Unicode homoglyph detector [LIBFUZZER] [AFL].
- Linearizability checks with dejafu for Haskell concurrent paths. A
  linearizability check proves concurrent operations behave like some valid
  one-at-a-time order [DEJAFU].
- Coverage target: 95 percent on the rule-engine kernel and 90 percent
  elsewhere, following `docs/CODE-COVERAGE-RULES.md` and Plan #21 Phase D.
- Five-layer TDD coverage from `docs/TDD-STRICT-RULE.md`: edge cases, resource
  release, latency, smoke, and end-to-end tests on every touched file.

The CVE test suite must be discoverable by the K8s Bazel runner and by
CodeBuild. New languages, folders, runtime paths, and build targets must update
tool wiring in the same slice.

## 14. Roadmap

The roadmap has six phases over 18 to 24 months. Each slice is 5,000 to 15,000
lines and ships independently. The target is 80 to 150 chronological slices.

### Phase 1: Months 1-3, About 15 Slices

Goal: app skeleton and highest-impact checks.

Deliverables:

- create `apps/governance/code_validation_engine/`;
- add governance `api.py` surface;
- create `services/cve/` Haskell sidecar foundation;
- add gRPC over `/var/run/xf/cve.sock`;
- amend ADR 0007 to include CVE in the Haskell-tier list;
- widen AutoIssue dynamic source support and frontend client handling, resolving
  AutoIssues #2470 and #2471;
- add SARIF writer and AutoIssue ingestion;
- add diagnostics API for `/diagnostics/code-validation/`;
- add the 10 highest-impact rule packs:
  architectural boundary, breaking API, drop-column migration, taint flow,
  missing authentication, prompt injection in comments, hallucinated API,
  unauthorized environment read, dead-code-on-replace, performance-regression
  proof.

### Phase 2: Months 4-6, About 20 Slices

Goal: native parsing and UAST kernels.

Deliverables:

- Plan #42 C application binary interface wrappers for Tree-sitter binding;
- UAST builder kernels;
- per-language UAST mappers for Python, TypeScript, Go, Rust, C++, and Haskell;
- Bazel `cc_library` per mapper;
- golden tests for parse tree, UAST, and CIR output.

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
- dejafu checks for concurrent Haskell paths.

### Phase 5: Months 13-18, About 20 Slices

Goal: rule-pack lifecycle.

Deliverables:

- extend Plan #18 rulesd lifecycle for CVE packs;
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

## 15. Acceptance Criteria

### Scenario 1: Local edit creates an app-visible CVE finding

Given an agent edits a Python file and adds a forbidden cross-module private
import, when the local CVE hook runs, then the commit is blocked, a SARIF
finding is written, and an AutoIssue with source `cve_arch_boundary` is created
or deduped.

### Scenario 2: Solver uncertainty goes to Review

Given a security-critical proof obligation exceeds the local one-second budget,
when Z3 or CVC5 returns UNKNOWN, then CVE does not reject the change and creates
a Plan #17 Review queue item with the proof details.

### Scenario 3: Rule-pack noise is visible

Given a rule pack produces many operator overrides over 30 days, when the
diagnostics page loads, then the page shows the rule pack's false-positive rate
and the source bucket is visible in AutoIssues.

### Scenario 4: K8s runs CVE as Bazel targets

Given the K8s distributed test coordinator runs an incremental local suite, when
CVE targets are selected, then they use the source-snapshot protocol, shard
through the K8S.20 formula, and merge coverage and mutation evidence through the
K8S.23 final merge job.

### Scenario 5: CodeBuild budget cap is respected

Given AWS CodeBuild reaches the 100 percent budget cap, when the master-gate
CVE suite is due to run, then it skips per the Step 5 lock, files an AutoIssue,
and local K8s incremental CVE remains available.

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
- [COMPACT_REGIONS] Yang, Mainland, and Marlow, 2015, "Compact Normal Forms for
  Efficient Storage of Immutable Data," ICFP, DOI: 10.1145/2784731.2784735.
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
- [WASM_CORE] W3C, "WebAssembly Core Specification 2.0," official
  recommendation, https://www.w3.org/TR/wasm-core-2/.
- [AESON] Hackage, "aeson: Fast JSON parsing and encoding," official docs,
  https://hackage.haskell.org/package/aeson; Bryan O'Sullivan, 2011, "Aeson:
  A Fast JSON Library for Haskell," https://www.serpentine.com/blog/2011/12/05/aeson-a-fast-json-library-for-haskell/.
- [HOARE] Hoare, 1969, "An Axiomatic Basis for Computer Programming,"
  Communications of the ACM, DOI: 10.1145/363235.363259.
- [ABSTRACT_INTERPRETATION] Cousot and Cousot, 1977, "Abstract Interpretation:
  A Unified Lattice Model for Static Analysis of Programs," POPL,
  DOI: 10.1145/512950.512973.
- [GALOIS] Cousot and Cousot, 1979, "Systematic Design of Program Analysis
  Frameworks," POPL, DOI: 10.1145/567752.567778.
- [SARIF] OASIS, "Static Analysis Results Interchange Format Version 2.1.0,"
  official standard, https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html.
- [GRPC] gRPC authors, "gRPC over Unix domain sockets and naming," official
  docs, https://grpc.io/docs/guides/custom-name-resolution/.
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
- [PROTOBUF] Google, "Protocol Buffers Language Guide," official docs,
  https://protobuf.dev/programming-guides/proto3/.
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
- [AFL] AFL++ maintainers, "AFL++ Documentation," official docs,
  https://aflplus.plus/docs/.
- [DEJAFU] Hackage, "dejafu: systematic testing for concurrent Haskell
  programs," official docs, https://hackage.haskell.org/package/dejafu.
- [HEDGEHOG] Hackage, "hedgehog: property-based testing," official docs,
  https://hackage.haskell.org/package/hedgehog.
- [TASTY] Hackage, "tasty: modern and extensible testing framework," official
  docs, https://hackage.haskell.org/package/tasty.
- [TASTY_GOLDEN] Hackage, "tasty-golden: golden tests support for tasty,"
  official docs, https://hackage.haskell.org/package/tasty-golden.
- [MUCHECK] MuCheck project, "MuCheck: mutation testing for Haskell," official
  repository, https://github.com/fortytools/mucheck.
- [MUTMUT] mutmut maintainers, "mutmut documentation," official docs,
  https://mutmut.readthedocs.io/.
- [STRYKER] Stryker Mutator, "Stryker mutation testing documentation,"
  official docs, https://stryker-mutator.io/docs/.
- [MULL] Mull project, "Mull mutation testing system," official docs,
  https://mull.readthedocs.io/.
- [CARGO_MUTANTS] cargo-mutants maintainers, "cargo-mutants documentation,"
  official docs, https://mutants.rs/.
- [GO_MUTESTING] go-mutesting project, "go-mutesting," official repository,
  https://github.com/zimmski/go-mutesting.
- [CLIPPY] Rust project, "Clippy documentation," official docs,
  https://doc.rust-lang.org/clippy/.
- [INTEL_INTRINSICS] Intel, "Intel Intrinsics Guide," official docs,
  https://www.intel.com/content/www/us/en/docs/intrinsics-guide/index.html.
- [C_ABI_SPEC] Repo spec, "C ABI Wrapper Standard,"
  `docs/specs/fr-c-abi-wrapper-standard.md`.
- [PYTHON_CTYPES] Python Software Foundation, "ctypes: A foreign function
  library for Python," official docs, https://docs.python.org/3/library/ctypes.html.
- [GO_CGO] Go project, "cgo command documentation," official docs,
  https://pkg.go.dev/cmd/cgo.
- [GHC_FFI] GHC User Guide, "Foreign function interface," official docs,
  https://ghc.gitlab.haskell.org/ghc/doc/users_guide/exts/ffi.html.
- [BAZEL_BEP] Bazel project, "Build Event Protocol," official docs,
  https://bazel.build/remote/bep.
- [AWS_CODEBUILD] Amazon Web Services, "AWS CodeBuild User Guide," official
  docs, https://docs.aws.amazon.com/codebuild/latest/userguide/welcome.html.

## 17. Self-Score

| Dimension | Score | Justification |
|---|---:|---|
| Vision | 10 | The spec states a focused purpose: pre-execution validation that fills known app gaps and does not duplicate runtime observability. |
| Scope | 9 | Scope is realistic at 300,000 to 500,000 lines across six locked languages, with clear non-goals. One point is held back because exact per-slice contents will still need implementation specs. |
| Architecture | 10 | The design fits the modular monolith, governance module, sidecar tier, Plan #42 native boundary, AutoIssues, K8s, and CodeBuild. |
| Sliceability | 9 | The six-phase roadmap targets 80 to 150 slices with independent deliverables. Exact slice names are left for phase specs. |
| Citations | 10 | Every named algorithm and standard in the spec has a DOI, ISBN, official URL, ePrint id, or plan cross-reference. |
| Project-rule fit | 10 | The spec follows the repo's no-duplicate, plain-English, AutoIssue, paper-trail, C++ first, compiled-tooling, Lua sandbox, and modular-monolith rules. |
| Self-test strategy | 9 | It reuses tasty-hedgehog, tasty-golden, mutation testing, fuzzing, dejafu, coverage thresholds, and the five TDD layers. One point is held back for future per-tool command specs. |
| Performance and observability | 10 | Latency, memory, trace, metric, log, profile, error, SARIF, and AutoIssue budgets are explicit and reuse the existing stack. |
| Risk and dependency | 9 | Rollback paths cover crashes, UNKNOWN solver results, parser pinning, budget caps, rule-pack failures, and false positives. More detail will be needed in per-phase runbooks. |
| Plain-English readability | 9 | Advanced terms are defined before use and app behavior is described plainly. One point is held back because the spec necessarily includes many technical source names. |
| **Total** | **95/100** | This clears the 90-point target while leaving honest room for future implementation specs to add command-level detail. |

[SPEC CITED: feature=fr-code-validation-engine kind=technical_doc id=https://tree-sitter.github.io/tree-sitter/ verified_at=2026-06-02]
