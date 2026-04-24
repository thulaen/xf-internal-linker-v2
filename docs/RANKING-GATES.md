# Ranking Signal Gates — canonical reference

This document is the single source of truth for the two strict gates that govern ranking signals, meta-algorithms, autotuners, hyperparameters, and weight-preset keys in this project.

**Every AI agent (Claude, Codex, Gemini, Antigravity, and any future agent) must read this file at session start if their work touches ranking, meta, autotuner, or weight code.** Abridged copies of these gates live in `CLAUDE.md`, `AGENTS.md`, and `AI-CONTEXT.md § Session Gate`, and all three point back here for the full text.

Both gates are additive to:
- `docs/BUSINESS-LOGIC-CHECKLIST.md` (which they reinforce and extend)
- The 5-step Ranking FR Checklist in `FEATURE-REQUESTS.md` (which they strengthen)

Skipping any item in either gate is a policy violation equivalent to bypassing a pre-commit hook. Reviewers must reject work where the gate was skipped.

---

## Why two gates

The project has suffered from signal drift: ideas shipped as ranking signals without primary sources; hyperparameters defaulted to round numbers without citation; new signals that silently overlapped with existing signals or meta-algorithms; signals that worked on paper but blew the hardware budget of the target machine.

The two gates address the two moments where drift enters:

- **Gate A — Ranking Signal Implementation Gate.** Fires when an agent is about to write or modify *code* that implements a ranking signal. Catches: missing spec, missing DOI, missing baseline citation, hidden overlap, missing neutral fallback, missing diagnostic.
- **Gate B — User-Idea Overlap Gate.** Fires the moment a new idea is *proposed* by the operator or another agent — before any plan, spec, or code is written. Catches: duplication with an existing signal, conflict with an adjacent signal, untenable hardware cost, missing primary source.

Gate A prevents bad code from landing. Gate B prevents bad plans from being made.

---

## Gate A — Ranking Signal Implementation Gate

### When it fires

Any session that is about to add, edit, or tune:

- a ranking signal (a term in `ranker.py`'s composite score)
- a meta-algorithm (reranker, slate diversifier, clustering passes, feedback loops)
- an autotuner (weight optimizer, hyperparameter search)
- a hyperparameter default (a value in `backend/apps/suggestions/recommended_weights.py`)
- a weight-preset key (any setting with a `<prefix>.ranking_weight` or `<prefix>.enabled` key)

### Every box must be checked before one line of code is written

#### A1 — Spec exists with every mandatory section

The spec file at `docs/specs/frXXX-*.md` (or `pick-NN-*.md`) must exist and contain all of these sections:

| Section | Purpose |
|---|---|
| `## Summary` | Plain-English one-paragraph description of what the signal does |
| `## Academic Source` | DOI / RFC number / patent number + full citation + open-access link |
| `## Mapping: Paper Variables → Code Variables` | Table mapping paper notation to the exact code variable names |
| `## Researched Starting Point` | Every default value cited from a published baseline |
| `## Why This Does Not Overlap With Any Existing Signal` | Complete enumeration + disambiguation |
| `## Neutral Fallback` | Behavior when input is missing or below BLC §6.4 minimum-data floors |
| `## Architecture Lane` | Python / C++ / hybrid — decision and justification |
| `## Hardware Budget` | RAM, CPU ms, GPU VRAM, disk — measured on the target machine |
| `## Real-World Constraints` | Deployment gotchas, rate limits, FAISS index size interactions |
| `## Diagnostics` | What the reviewer sees in the suggestion detail view |
| `## Benchmark Plan` | Three input sizes per BLC §1.4 |
| `## Edge Cases` | Every failure mode mapped to an exception or documented fallback |
| `## Gate Justifications` | Explicit justification for any gate checklist item that doesn't apply |
| `## Pending` | Explicit list of what's deferred (C++ port, frontend UI, benchmark, etc.) |

A spec that omits a section blocks the merge. A spec with an empty section blocks the merge.

#### A2 — Academic Source has a DOI / RFC / patent number

Accepted: peer-reviewed paper with DOI, IETF RFC with number, US / EU patent with number.

Not accepted: blog posts, tutorials, Stack Overflow answers, GitHub issues, LLM knowledge, "I read it somewhere."

#### A3 — Source quotes the exact equation / claim / section range

The spec must quote the specific equation number, claim number, section number, or page range being implemented. Not: "the PageRank paper". Yes: "Page et al. 1998 §2.5 eq. 3".

#### A4 — Variable mapping table when paper notation differs

If the paper uses variable names like `α`, `β`, `r(p)` and the code uses `damping`, `attenuation`, `rank`, the spec must have a two-column table showing the mapping.

#### A5 — Every default value cites a published baseline

Every hyperparameter default must be cited in the form: `Baseline: Author YYYY, Table N` or `Baseline: Author YYYY, empirical study on <corpus>, reported optimum range [X, Y]`.

Round-number defaults (0.5, 1.0, 0.1) are banned **unless** explicit written justification is provided (e.g. "0.5 is the standard neutral-midpoint in Kim et al. 2014 §4.1 for dwell-time scoring").

#### A6 — Non-overlap section enumerates every adjacent signal

The `## Why This Does Not Overlap With Any Existing Signal` section must list:

- Every currently-live signal in `ranker.py` (all 15 as of FR-098, extending to 22 after FR-099–FR-105).
- Every pending FR spec in `docs/specs/` (fr### + pick-NN + meta-### + opt-###).
- Every meta-algorithm (FR-013 Explore/Exploit reranker, FR-014 clustering, FR-015 slate diversity, FR-018 auto-tuner).
- Every reserved key in `backend/apps/suggestions/recommended_weights.py` and `recommended_weights_forward_settings.py`.

For each, a one-sentence non-overlap argument. If a signal is genuinely adjacent, an explicit disjoint-input-partition contract is documented (input X goes to signal A, input Y goes to signal B, they never read the same input).

#### A7 — Neutral fallback is explicit

Every signal must behave gracefully when:
- Required input is missing (the dependent column is `NULL`, the cache is empty, the graph is disconnected)
- Input is below the BLC §6.4 minimum-data floor (too few rows to compute)
- Input is corrupted (NaN, infinity, unexpected type)

The fallback must be: return a neutral value (0.0 for boosts, 0.5 for bidirectional signals, 0.0 for penalties) AND emit a diagnostic line (`<signal>: cold start` / `<signal>: missing input`).

No signal may raise an unhandled exception inside `score_destination_matches`. A crash there kills the whole pipeline.

#### A8 — Hardware budget measured on the target machine

The spec must show, with numbers derived from the hardware targets in `docs/BUSINESS-LOGIC-CHECKLIST.md §6`:

- Python hot-path < 50 ms per 500-candidate batch
- C++ hot-path < 5 ms per 500-candidate batch
- RAM < 10 GB app-headroom (Docker + PostgreSQL + Django + Celery + Angular dev) — each signal's per-pipeline cost
- GPU < 6 GB VRAM (shared with BAAI/bge-m3 already loaded) — zero for non-embedding signals
- Disk cost with 30-day and 90-day growth projections for any new persistent column

If any budget is violated: either (a) propose a cheaper algorithm (approximation, sampling, cache) and re-measure, or (b) mark the signal `# PERF: pending C++ port` in code with a follow-up ticket, or (c) defer the signal to a session after hardware upgrade.

#### A9 — Recommended-preset keys seeded with cited comments

In `backend/apps/suggestions/recommended_weights.py`:

```python
# FR-XXX <signal name>
# Baseline: <Author YYYY>, <Table N or section N>
"<signal_prefix>.enabled": "true",
"<signal_prefix>.ranking_weight": "<value>",
```

Every key has an inline comment citing the source of the default.

#### A10 — Migration upserts keys into Recommended preset

A data migration exists that upserts the new keys into the `WeightPreset` row where `is_system=True AND name='Recommended'`. Without this, existing installs never see the new defaults when they load the preset.

#### A11 — Suggestion-detail diagnostic JSON populated

The `Suggestion` model has two new columns per signal:
- `score_<signal>` (FloatField) — the raw signal value
- `<signal>_diagnostics` (JSONField) — the blob showing fallback flag, C++/Python path, input values, derived intermediate values

The JSON is visible in the Review page's detail panel, so a reviewer can answer the BLC §3 four questions without reading logs.

#### A12 — Inline source comments on every non-trivial formula

Example:
```python
# Source: Katz 1953, Psychometrika 18(1) eq. 2 — attenuated reachability
katz_score = 1.0 - math.exp(-beta * hop_count)
```

Divergences tagged:
```python
# Divergence: Katz 1953 uses beta ∈ (0, 1/λ₁]; we clamp to 0.5 to avoid
# eigenvalue computation. See spec §X for derivation.
beta = min(0.5, beta_param)
```

---

## Gate B — User-Idea Overlap Gate

### When it fires

The moment the operator (or any AI agent) proposes a new idea touching: a ranking signal, meta-algorithm, autotuner, hyperparameter, weight-preset key, or a re-tuning of any of the above.

This gate fires **before** any planning, spec writing, or code. Its output is a report; only after operator approval does the session proceed to Gate A and spec writing.

### Every box must be checked and reported

#### B1 — Overlap search (mandatory)

The AI must grep these locations for the proposed concept:

- `FEATURE-REQUESTS.md` — every FR entry (COMPLETED, IN-PROGRESS, PENDING)
- `docs/specs/` — every `fr###-*.md`, `pick-NN-*.md`, `meta-###-*.md`, `opt-###-*.md`
- `backend/apps/pipeline/services/` — every helper module
- `backend/apps/suggestions/recommended_weights.py` — every reserved key
- `backend/apps/suggestions/recommended_weights_forward_settings.py` — every forward-declared key
- `backend/apps/suggestions/meta_registry.py` — every registered meta-algo name

Report as one of three statuses:

- **CLEAR** — no overlap found. Proceed to other gate checks.
- **SOFT OVERLAP** — adjacent signal exists but disambiguation is possible via disjoint-input-partition or mechanism-level difference. Report the specific spec/FR and propose the disambiguation.
- **HARD DUPLICATE** — an existing signal does the same thing on the same input. STOP and refuse. Report which FR to extend instead of creating a new one.

#### B2 — Source-of-truth check (mandatory)

Does the proposed idea have a primary source (DOI / RFC / patent)?

If yes → cite it, proceed to B3.

If no → check exception criteria:
- (a) Newly-published paper not yet in the project's bibliography (cite the paper, explain why it wasn't available at project start)
- (b) Newly-granted patent (cite the patent number, explain)
- (c) A better unexplored option exists that combines known sources into a novel measurable claim (explain what makes it novel, cite the building-block sources)

If no exception applies → STOP. The operator must either (i) provide a primary source, (ii) explicitly accept a `# HEURISTIC: no primary source` tag in the shipped code with a session-summary callout, or (iii) abandon the idea.

#### B3 — Hardware budget check (mandatory — derived from BLC §6)

Target machine: i5-12450H (8 cores / 12 threads), 16 GB RAM, RTX 3050 6 GB VRAM, 512 GB NVMe with 59 GB free (subject to change — re-verify `df -h /` if the machine is upgraded).

Estimate for the proposed idea:

- **Expected RAM**: must fit in the 10 GB app-headroom after Django + Celery + PostgreSQL + Angular + Redis are loaded.
- **Expected CPU**: hot-path < 50 ms per 500-candidate batch (Python) or < 5 ms (C++). Non-hot-path (precompute caches, periodic Celery tasks) gets looser budgets but still documented.
- **Expected GPU**: if using the GPU, must fit in 6 GB VRAM with BAAI/bge-m3 (~2.5 GB) already loaded.
- **Expected disk**: any new persistent column must include 30-day and 90-day growth projections.

If any budget is violated:
- Propose a cheaper algorithm (approximation, sampling, caching) and re-estimate.
- OR defer the idea to a session after hardware upgrade (16 GB → 32 GB RAM, 6 GB → 12 GB VRAM, etc.).

Exceptions do not bypass this step. Even a newly-published paper must pass the hardware budget check before the idea is accepted.

#### B4 — Non-interference contract (mandatory)

For every live signal, pending spec, and meta-algorithm with adjacent inputs, show that the proposed idea does not:

- **Double-count** — produce a second copy of the same signal value from the same input. Example: adding a second PageRank signal using the same matrix duplicates FR-006.
- **Contradict** — one signal boosts a candidate the other penalizes based on the same property. Example: RLI would reward reciprocal links which FR-197 link-farm ring detection penalizes. If contradiction exists, design an explicit non-interference gate (RLI is suppressed when FR-197 fires).
- **Create dependency cycles** — signal A reads signal B's output which reads signal A's output. Example: an autotuner optimizing weights for a signal whose output is fed back into the autotuner's objective.

If any interference exists, either explicitly design a disjoint input partition OR abandon the idea.

#### B5 — Default-value derivation (mandatory)

For every hyperparameter the idea introduces:

- Name a published baseline (paper Table N, RFC §M, empirical study corpus-C).
- If no published baseline exists, cite a closely-related empirical study and justify the transfer.
- "Round-number" defaults (0.5, 1.0, 0.1, 10) are banned unless explicit written justification.

#### B6 — Report format to the operator

Before writing any spec, the AI reports findings in this exact shape:

```
PROPOSED IDEA: <name>
  Overlap status:   CLEAR | SOFT-resolved-by-<mechanism> | HARD-BLOCKED
  Source of truth:  DOI / RFC / patent <number>  OR  exception: <reason>
  Hardware budget:  fits | violates <which budget>
  Non-interference: <list existing signals checked + 1-line each>
  Default values:   <list + baseline citations>
  Recommendation:   PROCEED TO SPEC | REFINE AND RE-CHECK | ABANDON
```

#### B7 — Explicit operator approval

A "nod" is not enough. The operator must say: `"proceed"`, `"ship it"`, `"spec it"`, `"go ahead"`, or equivalent. Only after that does the AI proceed to spec writing and Gate A.

---

## Enforcement

### At session start

Every AI agent whose planned work touches ranking, meta, autotuner, or weight-preset code must:

1. Read this file in full.
2. Read `docs/BUSINESS-LOGIC-CHECKLIST.md` in full.
3. Post the `Session Start Snapshot` (see AI-CONTEXT.md § Session Gate) before any other work.
4. Run Gate B on the operator's request before making any promise.

### Before code is written

1. The spec file must exist with every mandatory section filled.
2. Gate A must pass — every checkbox has a satisfying answer.
3. If any checkbox is genuinely inapplicable, the spec has a `## Gate Justifications` section explaining why.

### Before merge

1. CI runs `backend/scripts/check_phantom_references.py` to verify no banned identifier reappeared.
2. CI runs `docker compose --env-file .env up --build` and the three verification sub-steps (`pytest`, `pytest --benchmark-only`, end-to-end smoke).
3. Reviewer verifies every checkbox in Gate A.

### After merge

1. `AI-CONTEXT.md § Execution Ledger` is updated with the FR and timestamp.
2. `FEATURE-REQUESTS.md` has the FR entry with `Completed:` set.
3. `AGENT-HANDOFF.md` has the handoff entry.
4. `docs/reports/YYYY-MM-DD-<topic>.md` dated audit report exists if `ranker.py` composite-score formula changed (BLC §4.4 mandatory trigger).

---

## Examples

### Example 1 — Correct Gate B application

> **Operator:** "I think we should add a signal that boosts candidates whose destination URL contains the same top-level category as the host."

**AI Gate B output:**
```
PROPOSED IDEA: URL-Category Overlap Boost
  Overlap status:   HARD-BLOCKED
  Details:          This duplicates silo.same_silo_boost which already rewards
                    same-category links based on the configured silo membership.
                    If the user wants URL-path-based matching instead of
                    scope-based matching, they should propose extending the
                    silo signal with a URL-path input rather than a new signal.
  Recommendation:   ABANDON — extend silo.same_silo_boost instead.
```

### Example 2 — Correct Gate A application

> **Agent about to write code for FR-100 KMIG.**

Gate A checklist applied:
- [x] `docs/specs/fr100-katz-marginal-information-gain.md` exists with all 14 mandatory sections
- [x] Academic Source cites Katz (1953) Psychometrika 18(1) with DOI `10.1007/BF02289026`
- [x] Source quotes eq. 2 — `r_ij = Σ_k β^k · a_ij^(k)`
- [x] Variable mapping table: `β` → `kmig.attenuation`, `a_ij^(k)` → `graph_power_matrix[k][i,j]`
- [x] Default `kmig.attenuation=0.5` cited: Katz 1953 §3 recommends β ∈ (0, 1/λ₁); we clamp to 0.5 to avoid eigenvalue computation
- [x] Non-overlap section enumerates FR-012 click-distance (different graph), FR-006 PageRank (different recurrence), FR-073 prof-graph (different graph), + 90 others
- [x] Neutral fallback: returns 0.0 and emits `kmig: cold start` diagnostic when graph has <100 edges
- [x] Hardware budget: 50 MB RAM, <1 ms per candidate — well under both budgets
- [x] Preset keys seeded in `recommended_weights.py` with inline comment citing Katz 1953
- [x] Migration 0035 upserts `kmig.enabled=true` and `kmig.ranking_weight=0.05`
- [x] Diagnostic JSON exposes `raw_score`, `hop_count`, `fallback_triggered`, `path=python`
- [x] Inline source comment on the attenuation formula

Gate A passes → code may be written.

---

## Exceptions

The only exceptions to these gates are:

1. **Brand-new paper or patent** — published after the project's last bibliography freeze and relevant to the proposed idea. Must still pass B3 (hardware budget) and B4 (non-interference).
2. **Better unexplored option** — a novel combination of existing sources that creates a new measurable claim. Must still pass B3 + B4 + B6 (operator approval).
3. **Heuristic with explicit tag** — shipped with `# HEURISTIC: no primary source` inline tag, called out in the session summary, and explicitly approved by the operator.

Nothing else bypasses these gates.

---

## Anti-patterns (do not do)

- **"We'll add the source later."** No. The source is the first thing that goes in the spec.
- **"Round-number default for now, we'll tune it later."** No. Default is cited or the signal doesn't ship.
- **"It's only a soft overlap."** Soft overlap is a design smell. Either disjoint the inputs explicitly or abandon.
- **"Performance budget is an implementation detail."** No. A signal that blows the budget is a non-starter.
- **"The operator said yes in chat, no need to write it down."** No. Operator approval is recorded in the session note.
- **"Gate A doesn't apply because it's just a weight tweak."** No. Weight tweaks hit Gate A because they change the Recommended preset.

---

## Change log

- **2026-04-24** — Gates A + B written and canonicalized. Extracted from the FR-099–FR-105 session (7 graph-topology ranking signals). Referenced by CLAUDE.md, AGENTS.md, AI-CONTEXT.md Session Gate.
