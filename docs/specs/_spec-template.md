# Spec template — `<pick short name>` (Pick #NN)

> This file is the **template** every new pick spec must follow. Copy it,
> rename to the pick's canonical key (e.g. `pick-29-hits.md`), fill every
> section, delete this banner. A pick whose spec omits a section below
> is not ready to merge.

---

## 1 · Identity

| Field | Value |
|---|---|
| **Plan pick number** | `<#NN>` — matches the 52-pick plan manifest |
| **Canonical name** | `<e.g. HITS — Kleinberg authority + hub>` |
| **Settings prefix** | `<e.g. hits>` — used as `<prefix>.enabled`, `<prefix>.<param>` in AppSetting |
| **Pipeline stage** | Source · Crawl · Parse · Embed · Score · Rank · Feedback · Training · Eval · Reviewable |
| **Shipped in commit** | `<git sha if already merged, else "not yet merged">` |
| **Helper module** | `<path e.g. backend/apps/pipeline/services/hits.py>` |
| **Tests module** | `<path e.g. backend/apps/pipeline/test_graph_signals.py>` |
| **Benchmark module** | `<path e.g. backend/benchmarks/test_bench_hits.py>` |

## 2 · Motivation (ELI5)

Plain-English: why this pick exists. What does it give the linker that
we don't already have? One paragraph, max five sentences, no jargon
without a definition the sentence earlier.

## 3 · Academic source of truth

| Field | Value |
|---|---|
| **Full citation** | Authors, year, title, venue, pages, DOI or arXiv link |
| **Open-access link** | URL to an authoritative full-text copy (arXiv, author's page, institutional repo) |
| **Relevant section(s)** | e.g. "§3 — Algorithm R", "Table 2", "§5.2 default μ=2000" |
| **What we faithfully reproduce** | e.g. "the power-iteration recurrence" |
| **What we deliberately diverge on** | e.g. "uses Laplace smoothing instead of the paper's Good-Turing to avoid a counts table" — with reason |

If the source is a patent or RFC, give the patent number / RFC number
and the clause ranges we implement.

## 4 · Input contract

What the caller hands in. Exact types, shapes, units. No hand-waving.

- **Parameter 1** — type, domain, units, example. What happens on
  invalid input (exception class + message).
- **Parameter 2** — same.
- …

Document the **empty-input behaviour** (degenerate graph, empty stream,
empty query) explicitly — operators hit these on a fresh install.

## 5 · Output contract

What the caller gets back.

- **Return type** — exact dataclass or built-in, with every field.
- **Invariants** — e.g. "score ∈ [0, 1]", "sum of contributions equals
  total score", "doc IDs in the same set as input".
- **Determinism** — is the output bit-identical for the same input, or
  does it depend on RNG state / floating-point order?
- **Empty-input output** — what comes back when the input is degenerate.

## 6 · Hyperparameters

Every hyperparameter as a row. This table is the single source of
truth — the `recommended_weights.py` dict and the migration that seeds
AppSetting must agree with it byte-for-byte.

| Setting key | Type | Default | Source of default | TPE-tuned? | TPE search space | Impact |
|---|---|---|---|---|---|---|
| `<prefix>.enabled` | bool | `true` | Project policy — Recommended preset turns every shipped pick on | No | — | Whether the pick runs at all |
| `<prefix>.<param_name>` | float / int / str | `<value>` | Cite paper section or RFC clause | Yes / No | e.g. `loguniform(1e-4, 1e-1)`, `[0.6, 0.95]`, `categorical({"sigmoid","isotonic"})` | One short line on what moving this does |

**Rules:**

- Every pick ships `<prefix>.enabled=true` in the Recommended preset.
- Every default must cite a specific paper section / RFC clause / plan
  decision — no "round number" guesses.
- **TPE-tuned**:
  - *Yes* for ranking-quality knobs (α, β, μ, seed count, K-factor, …)
    that trade bias/variance against the live corpus.
  - *No* for correctness knobs (Bloom FPR target, HLL precision,
    Kernel SHAP `nsamples`) and for numerical floors (tie-break ε).
- TPE search space syntax follows `optuna` conventions (`uniform`,
  `loguniform`, `categorical`). Integer ranges use `int` with an
  explicit bounds tuple.

## 7 · Pseudocode

Formal statement of the algorithm. Math notation for the core
recurrence, then Python-like pseudocode that mirrors the helper's
actual shape.

```
# Math:
#   f(x) = …
#
# Python:
def algorithm(input):
    ...
```

If the implementation delegates to a library (networkx, scipy, shap,
faiss), call out which library function is wrapped and paste the
one-line signature plus our wrapper's added value.

## 8 · Integration points

| Caller | What they pass in | What they do with the result |
|---|---|---|
| `<apps/... caller module>` | `<inputs>` | `<consumer>` |

The first row answers "who is expected to import this module?". For
freshly-shipped helpers the only row is "nothing yet — lands in W1/W2/
W3/W4" until wiring happens.

## 9 · Scheduled-updates job (if periodic)

If the pick runs periodically, name the job exactly as it appears in
the job list + link to its runbook section.

| Field | Value |
|---|---|
| Job key | `<e.g. hits_refresh>` |
| Cadence | `<daily 14:50 / weekly Mon 13:30 / monthly>` |
| Priority | critical / high / medium / low |
| Estimate | `<wall-clock range e.g. 5–8 min>` |
| Multicore inside | yes / no |
| Depends on jobs | `<e.g. pagerank_refresh>` (empty if none) |
| RAM budget | `<≤ MB>` |
| Disk budget | `<≤ MB>` |

If the pick is **on-demand only** (Kernel SHAP), say so explicitly
with a one-line reason.

## 10 · Resource budget

| Resource | Budget | Measured on |
|---|---|---|
| RAM (peak) | `<MB>` | typical corpus (cite the benchmark input size) |
| Disk (model artefacts) | `<MB>` | first-run warm |
| CPU time (typical) | `<ms / s>` | benchmark run |
| Wall-clock when scheduled | `<range>` | last scheduler run if applicable |

Budgets must match the plan's per-stage caps:
- Source: ≤ 128 MB RAM, ≤ 256 MB disk
- Crawl: ≤ 128 MB RAM, ≤ 256 MB disk
- Parse/Embed: ≤ 128 MB RAM, ≤ 256 MB disk (FastText LangID excepted —
  plan allows 126 MB disk)
- Score/Rank: ≤ 256 MB RAM
- Auto-Seeder (#51): ≤ 50 MB RAM, ≤ 50 MB disk
- ACI (#52): < 1 MB RAM, < 1 MB disk

Any pick that blows a budget must either be re-designed or get an
explicit exception entry in `docs/PERFORMANCE.md`.

## 11 · Tests

What the `test_*.py` file covers. Each row: "if this test fails, the
following invariant is broken." At least one row per invariant listed
in §5.

| Test name | Invariant verified |
|---|---|
| `test_empty_input_returns_empty` | Empty input is not an error |
| `test_…` | … |

Benchmark file (CLAUDE.md mandatory rule) lives in
`backend/benchmarks/` and measures **three input sizes** documented
in §12.

## 12 · Benchmark inputs

Three input sizes for the benchmark module, small → medium → large.
Measured timing goal + regression alert threshold.

| Size | Input shape | Expected runtime | Alert threshold |
|---|---|---|---|
| small | `<e.g. 100 docs>` | `< 10 ms` | > 50 ms |
| medium | `<e.g. 10 000 docs>` | `< 200 ms` | > 1 s |
| large | `<e.g. 100 000 docs>` | `< 5 s` | > 30 s |

## 13 · Edge cases & failure modes

- What breaks catastrophically if a user hands in malformed input?
- What goes wrong quietly? (e.g. "silent fall back to uniform PageRank
  when every seed is missing")
- What depends on upstream picks being enabled? (e.g. "TrustRank's
  quality depends on an auto-seeder actually having seeds")

Every failure mode must map to either (a) an exception + message, or
(b) a documented fallback behaviour.

## 14 · Paired picks (how it composes)

| Upstream | Reason |
|---|---|
| `<pick>` | feeds input |

| Downstream | Reason |
|---|---|
| `<pick>` | consumes output |

Helps reviewers spot wiring-time ordering constraints.

## 15 · Governance checklist

Tick each box before merging the spec or the wiring PR.

- [ ] `<prefix>.enabled` seeded in `recommended_weights.py`
- [ ] All hyperparameters seeded in `recommended_weights.py` with this
      spec's defaults
- [ ] Migration upserts the AppSetting rows
- [ ] `FEATURE-REQUESTS.md` entry written
- [ ] `AI-CONTEXT.md` execution ledger entry written
- [ ] `docs/BUSINESS-LOGIC-CHECKLIST.md` row ticked
- [ ] `docs/PERFORMANCE.md` entry added
- [ ] Helper module written and merged
- [ ] Benchmark module written and merged
- [ ] Test module written and merged
- [ ] Scheduled-updates job registered (if periodic)
- [ ] TPE search space declared in the meta-HPO study (if TPE-tuned)

---

> End of template. Fill every section. Empty sections block merge.
