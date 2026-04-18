# Business Logic Checklist

**This file is mandatory reading before any session that touches ranking, scoring, attribution, import, or reranking logic.**

An AI session or PR that skips any section is non-compliant. Read every section in order, check every box, or explicitly explain in writing why a box does not apply.

---

## Section 0 — AI Drift Rejection Gate

Run this first. Before writing a single line of code. If any answer is YES, stop immediately and resolve the issue or flag it to the user.

- [ ] Does this feature duplicate an existing FR in `FEATURE-REQUESTS.md` or `AI-CONTEXT.md`? → **Stop.**
- [ ] Does this feature lack a primary source (peer-reviewed paper with DOI, IETF RFC, or US/EU patent number)? → **Stop.**
- [ ] Does this feature mix two or more independent concepts into one composite score without a published formula that combines them the same way? → **Stop.**
- [ ] Can you name the exact Python, C++, or C# file and variable that this feature reads as input? If not → **Stop.**
- [ ] Does this feature have no neutral fallback — meaning if it produces garbage output, the rest of the pipeline cannot continue as if the feature is absent? → **Stop.**
- [ ] Does this feature produce no reviewer-visible diagnostic (a score that appears in the suggestion detail view, health page, or diagnostics panel)? → **Stop.**
- [ ] Can you state what specific user harm this feature prevents OR what measurable business value it improves? If not → **Stop.**
- [ ] Does this feature let one FR smuggle in a second unrelated capability? → **Split it into two separate FRs.**

---

## Section 0.5 — Forward Clash Gate

Before writing code, check that your work won't paint future phases into a corner.

- [ ] I checked the next 3 queued phases in the Execution Ledger (`AI-CONTEXT.md`)
- [ ] I searched pending FRs in `FEATURE-REQUESTS.md` for overlap with my current work area (same models, services, or signals)
- [ ] I searched `docs/specs/` for specs that reference the same code paths I will modify
- [ ] My implementation does not create new constraints, coupling, or breaking changes for any queued phase
- [ ] If a clash exists, I flagged it to the user before proceeding

---

## Section 1 — Pre-Session Research Gate

### 1.1 Source binding

Before writing any formula or algorithm:

- [ ] Name the algorithm exactly (e.g., "unbiased inverse-propensity scoring", "Dunning log-likelihood ratio", "synthetic control matching").
- [ ] Find the primary source. Acceptable: peer-reviewed paper (DOI required), IETF RFC, US/EU patent number (e.g., `US8407231B2`). Blogs, tutorials, and Stack Overflow answers are not acceptable.
- [ ] Paste the full citation into the feature spec (`docs/specs/frXXX-*.md`) under a `## Academic Source` heading. Include author, year, title, DOI or patent number.
- [ ] Quote the exact equation number or patent claim you are implementing. If the paper uses different variable names, document the mapping between paper variables and code variables.
- [ ] If no primary source exists after a thorough search, mark the logic `# HEURISTIC: no primary source` in the code and flag it explicitly in the session summary. Do not silently ship an ungrounded algorithm.

### 1.2 Duplicate and overlap gate

- [ ] Search `backend/apps/pipeline/services/` for any existing function that computes the same quantity from the same inputs. If one exists, extend it — do not create a parallel implementation.
- [ ] Search `FEATURE-REQUESTS.md` and `AI-CONTEXT.md § What Is Complete` for an FR that already covers this need.
- [ ] If overlap is found, document *why* the new approach supersedes the old one. The old implementation must not be silently deleted without explanation in the spec and commit message.

### 1.3 Researched starting-point defaults

Every new tunable weight, threshold, or hyperparameter needs a published baseline so that a non-expert operator has somewhere to start.

- [ ] Look up a published baseline value from the primary source or a closely related empirical study (e.g., "the paper reports that α = 0.6 performs well on short-document corpora").
- [ ] Write that baseline as the `WeightPreset` default (Django) or `appsettings.json` default (C#) with a comment: `# Baseline: <Author YYYY, Table N>` or `// Baseline: <Author YYYY, Table N>`.
- [ ] State whether auto-tuning (`WeightObjectiveFunction.cs`) covers this parameter. If it does, confirm the parameter is included in the L-BFGS search space. If it does not, document why and what an operator should watch to tune it manually.
- [ ] The baseline must produce reasonable results without the operator understanding the internal math.

### 1.4 Regression risk

- [ ] List every scoring signal or DB field that feeds the changed code path. Reference the composite score formula in `ranker.py` or the objective in `WeightObjectiveFunction.cs`.
- [ ] State which existing benchmark files cover those signals (`backend/benchmarks/test_bench_*.py`, `backend/extensions/benchmarks/bench_*.cpp`, `services/http-worker/benchmarks/*Benchmarks.cs`).
- [ ] If no benchmark exists for the changed signal, create one before merging. Three input sizes are required: small (10 candidates), medium (100 candidates), large (500 candidates). Cite the paper's reported time complexity if available.

---

## Section 2 — Algorithm Fidelity and Safety Rules

### 2.1 Formula lineage — mandatory inline comments

The paper or patent is the immutable spec. Code follows it, not the other way around.

- [ ] Every non-trivial formula has a comment on the line directly above it:
  ```python
  # Source: Joachims et al. 2017, eq. 4 — inverse propensity weight
  score = click / propensity
  ```
  or
  ```csharp
  // Source: Patent US8407231B2, claim 3 — freshness decay
  double decay = Math.Exp(-lambda * daysSinceLastSeen);
  ```
- [ ] If the implementation diverges from the source formula (clamped denominator, added epsilon, changed exponent), add a second comment: `# Divergence: <reason>` and update the spec accordingly.
- [ ] If you are tempted to change the formula without a new source, treat that as a drift signal — stop and ask the user.

### 2.2 Reality gap rule

A paper can describe a correct algorithm that is too slow or too memory-intensive to ship as written.

- [ ] After proving correctness (tests pass, formula matches paper), check whether the implementation meets the performance budget for this machine (see Section 6).
- [ ] If the algorithm is correct but too slow, mark it `# PERF: pending C++ port` and open a follow-up task. Do not ship a correct-but-unusably-slow algorithm without a documented optimization plan.
- [ ] Constraints that the paper does not mention (RAM limits, FAISS index size, DB connection pool limits, Docker container memory) must be documented in the spec under `## Real-World Constraints`.

### 2.3 Architecture lane

| Logic type | Required language |
|---|---|
| Hot-path scoring loop (>1 k calls per pipeline run) | C++ extension — Python fallback only if C++ unavailable |
| ML inference, embedding generation | Python |
| External HTTP I/O, crawling, import | C# HTTP Worker |
| UI orchestration | Angular |

- [ ] New code is in the correct lane. Hot-path Python prototypes must be tagged `# PERF: must port to C++ before merge`.
- [ ] If the feature touches core ranking, retrieval, or reranking loops, C++ is the default fast path. Python is the safety fallback, not the primary implementation.

### 2.4 Edge case and error handling

Every function must be robust to real-world data. No silent failures.

- [ ] The function handles without throwing: empty fields, zero values, negative numbers, `None`/`null`, unexpected types, empty result sets, and division by zero.
- [ ] When a business rule is violated (score outside valid range, required field missing, data below minimum threshold), the system raises a specific, readable error stating: what rule was violated, which input caused it, and what the operator should do next.
- [ ] Errors that indicate degraded or missing data propagate to the **Errors page** or the **Diagnostics / System Health panel** in the Angular UI. They must not be log-only.

### 2.5 Separation of concerns

Business rules must be independent of the UI layer and the database layer.

- [ ] Business rule logic lives in a service class or module. It does not import from `views.py`, Angular components, or ORM model fields directly.
- [ ] If the DB schema changes or the UI changes, the business rule must not need to change.
- [ ] New rules with more than three branches are expressed declaratively — constants, config entries, `WeightPreset` fields, or explicit policy objects — rather than as procedural `if/else` chains. This makes rules auditable and testable in isolation.

### 2.6 Safety invariants — never bypass

These rules protect end-users and operators. No feature may override them.

- [ ] The feature does not auto-edit XenForo or WordPress content. Suggestions are always surfaced for manual operator review before any link is applied.
- [ ] The feature does not bypass: stale checks, duplicate checks, canonical checks, anchor-policy checks, or link-budget rules.
- [ ] If the feature introduces uncertainty, it lowers confidence or stays neutral. It must not silently force a suggestion into a high-rank position or suppress a competing signal.

---

## Section 3 — Operator Diagnostics

Every new scoring signal or ranking change must be visible to operators without reading logs. This is not optional.

- [ ] The signal's contribution to the final composite score appears in the suggestion detail view (the per-suggestion diagnostic panel in the Review UI). It shows: raw signal value, whether the value was clamped or defaulted, whether fallback logic was used.
- [ ] Whether the C++ fast path or the Python fallback ran is shown in the diagnostic panel.
- [ ] Operators can answer these four questions from the UI — no log access required:
  1. What changed the ranking of this suggestion?
  2. Why is this score neutral (zero or at its published default)?
  3. Was fallback logic used for any signal?
  4. Is the C++ fast path active?
- [ ] If a signal is degraded or missing (data source returned zero rows, embedding unavailable, GSC data older than 7 days), the **System Health / Diagnostics panel** shows a warning banner. A log entry alone is not sufficient.

---

## Section 4 — Change Tracking and Doc Sync

AI drift happens when code advances but documentation does not. Preventing it is required, not optional.

### 4.1 Execution ledger

- [ ] Open `AI-CONTEXT.md § Execution Ledger`. Find the FR(s) this session touches.
- [ ] Update the status column to reflect actual code state today — not intended state, not last-session state.
- [ ] Add a `YYYY-MM-DD` timestamp to the ledger row.
- [ ] If a feature is complete but marked partial or pending, fix the ledger. If it is partial but marked complete, fix the ledger.

### 4.2 Spec parity

- [ ] Every changed FR has a matching `docs/specs/frXXX-*.md`. If the file does not exist, create a stub with at minimum these headings: `## Summary`, `## Academic Source`, `## Architecture Lane`, `## Real-World Constraints`, `## Researched Defaults`, `## Benchmark`, `## Edge Cases`, `## Diagnostics`, `## Pending`.
- [ ] The spec's `## Academic Source` matches the inline code comments. If the formula changed, update both.

### 4.3 Pending work tracking

- [ ] Any work deferred from this session (C++ port pending, additional signals planned, data migration not yet written) is logged as a `[ ]` item in the spec under `## Pending`.
- [ ] The `AI-CONTEXT.md` execution ledger reflects partial status for any FR with open `## Pending` items.

### 4.4 Audit trigger

If this session changed any of the following files, create a dated report in `docs/reports/YYYY-MM-DD-<topic>.md`:

| File changed | Report required |
|---|---|
| `backend/apps/pipeline/services/ranker.py` | Composite score formula or new signals |
| `backend/apps/analytics/impact_engine.py` | Attribution model |
| `services/http-worker/.../GSCAttributionService.cs` | Attribution model |
| `services/http-worker/.../PipelineServices.cs` | Crawl page cap or frontier logic |
| `backend/apps/pipeline/services/feedback_rerank.py` | Feedback reranking |
| `services/http-worker/.../WeightObjectiveFunction.cs` | Weight optimization objective |

The report must state: what changed, what academic source justifies it, what the known regression risk is, and what benchmark confirms it.

---

## Section 5 — CI and Static Analysis Compliance

- [ ] The magic-number checker passes with no new violations. Every new numeric constant is either a named constant with a source citation, or a tunable parameter in `WeightPreset` / `appsettings.json`.
- [ ] The duplicate-block detector passes. No copy-pasted scoring logic across files.
- [ ] The N+1 query detector passes for any new ORM call.
- [ ] All three benchmark sizes exist for new hot-path functions (small / medium / large).
- [ ] At least one unit test covers each edge case listed in Section 2.4.
- [ ] Pre-push hook runs without `--no-verify`.

---

## Section 6 — Hardware Budgets and Self-Pruning Policy

This section reflects the actual machine this project runs on. Re-verify these figures if the machine changes (run `df -h /` and check Task Manager → Performance).

### Host machine — as of 2026-04-11

| Resource | Spec | Hard constraint |
|---|---|---|
| CPU | Intel i5-12450H · 8 cores / 12 threads | Laptop chip — sustained loads may thermal-throttle. Benchmark at sustained load, not just cold-start. |
| RAM | 16 GB | Shared between OS, Docker, PostgreSQL, Django, Celery, Angular dev server. Application headroom ≈ 10 GB. |
| GPU | RTX 3050 6 GB VRAM (laptop) | FAISS GPU index is safe up to ~1.2 M vectors at 768-dim float32. No dedicated VRAM for training. |
| Disk | 512 GB NVMe — **59 GB free (88% full)** | This is the binding constraint. Every new feature must state its steady-state disk footprint. |

### 6.1 Feature-level performance budget

Before merging any new feature, measure it against all of these:

- [ ] Python hot-path signal: < 50 ms per pipeline run on a 500-candidate batch (single core, sustained).
- [ ] C++ hot-path: < 5 ms per pipeline run on a 500-candidate batch.
- [ ] C# import / attribution: < 2 s per page batch.
- [ ] Embedding batch (BAAI/bge-m3): < 500 ms per 32-document batch on GPU; < 2 s on CPU fallback.
- [ ] FAISS index rebuild: < 30 s for up to 50 k vectors on RTX 3050.
- [ ] RAM headroom: Django + 2 Celery workers + PostgreSQL must stay under 10 GB combined during a pipeline run. Verify with `docker stats`.
- [ ] Every spec for a feature that adds a new persistent table must include the estimated row size and projected growth rate (rows/day) under `## Real-World Constraints`.

### 6.2 Disk-space guard for new features

- [ ] Before adding a new DB table or expanding an existing one, estimate steady-state disk usage at 30-day and 90-day horizons. Write the estimate in the spec.
- [ ] pgvector storage: 768-dim float32 = 3 KB per vector + index overhead ≈ 5 KB per content item. 20 k items ≈ 100 MB. Include this in any spec that adds a vector column.
- [ ] Do not add a new log table, event table, or telemetry table without including a pruning rule in the same PR.

### 6.3 Self-pruning intervals

The following jobs run automatically on their stated cadence. Every pruning job must: (a) run as a Celery beat task, (b) log how many rows it deleted and the new row count, (c) check the minimum thresholds in 6.4 before deleting — abort and emit a health panel warning if a threshold would be breached.

| Table or artifact | Prune after | Celery task |
|---|---|---|
| `SuggestionPresentation` rows | 60 days | `analytics.tasks.prune_old_presentations` |
| `PipelineRun` rows (non-latest) | Keep last 30 runs per source | `pipeline.tasks.prune_old_runs` |
| `SearchMetric` rows | 120 days | `analytics.tasks.prune_old_search_metrics` |
| `TelemetryCoverageDaily` rows | 90 days | `analytics.tasks.prune_telemetry` |
| `GSCImpactSnapshot` rows | 120 days | `analytics.tasks.prune_gsc_snapshots` |
| `ImpactReport` rows | 180 days | `analytics.tasks.prune_impact_reports` |
| `LinkFreshnessEdge` inactive rows | 90 days since last seen | `graph.tasks.prune_stale_edges` |
| Celery task results (`django_celery_results`) | 14 days | Celery beat schedule |
| Django log files (`logs/*.log`) | Rotate at 10 MB, keep 5 files | `logging.handlers.RotatingFileHandler` |
| Docker dangling images | After every `docker-compose build` | `docker image prune -f` |
| Docker build cache | Weekly | `docker builder prune -f` |

### 6.4 Minimum data thresholds — ranking engine floor

Pruning must never drop below these values. Below the floor, the subsystem must return a neutral score and show a warning in the health panel — not crash.

| Subsystem | Minimum data required | What happens below the floor |
|---|---|---|
| FAISS retrieval | 10 `ContentItem` rows with embeddings | Pipeline returns zero candidates; health panel warning shown |
| Feedback reranking (`feedback_rerank.py`) | 100 `SuggestionPresentation` rows (any age) | Signal uses prior (neutral); diagnostic: "feedback: insufficient data" |
| Co-occurrence signal (`cooccurrence/services.py`) | 50 `ContentCooccurrence` pairs | Signal returns 0 (neutral); diagnostic: "cooccurrence: insufficient sessions" |
| GSC attribution (`impact_engine.py`) | 7 days of `SearchMetric` rows for the target page | Attribution shows `None`; health panel warning |
| Link freshness (`link_freshness.py`) | 14 days of `LinkFreshnessEdge` history | Freshness set to neutral 0.5; diagnostic: "freshness: cold start" |
| Weight auto-tuning (`WeightObjectiveFunction.cs`) | 30 days of outcome data | Tuner skips cycle, keeps existing weights; logs "auto-tune: insufficient window" |

### 6.5 Disk-space monitoring

- [ ] The System Health panel shows current Docker volume disk usage and PostgreSQL DB size at all times.
- [ ] A Celery beat task runs weekly (`disk_space_check`) and emits a health panel warning banner if free disk space drops below 15 GB.
- [ ] If free disk falls below 15 GB, the operator sees the warning on the Health page — not just in logs.
