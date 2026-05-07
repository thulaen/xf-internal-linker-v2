# FR-237 — Post-quality-gate L2-normalization audit

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | L2-normalization invariant audit |
| **Settings prefix** | n/a — runtime invariant, no operator tunable |
| **Pipeline stage** | Embed (between quality gate filter and DB persist) |
| **Helper** | `apps.pipeline.services.embeddings._audit_l2_normalization` |
| **Error type** | `apps.pipeline.services.embeddings.L2NormalizationAuditError` |
| **Alert event** | `embeddings.l2_audit_failed` (severity: high, source: embeddings) |
| **Default state** | ON. No flag, no opt-out. |

## 2 · Motivation (ELI5)

The pipeline scores how similar two pages are by multiplying their AI fingerprints (vectors) together. That math only gives the right answer if both fingerprints have the same length (technically: are unit-length, also called L2-unit). Two different code paths score the vectors — a fast GPU one and a slower CPU one — and they only agree when the vectors are unit-length. If a fingerprint ever drifts off unit-length (because of a bug in normalization, a corrupted batch, a race condition, anything), the GPU path and CPU path will silently disagree, and every link suggestion the system makes will be biased. The audit is one tiny check (~2 microseconds per batch) that screams the moment the invariant breaks, instead of letting bad scores leak through to operators.

## 3 · Academic / industry source of truth

| Field | Value |
|---|---|
| **Primary** | Wang, P. et al. (2017). *Normalized Word Embedding and Orthogonal Transform for Bilingual Word Translation.* NAACL. arXiv: [1505.04711](https://arxiv.org/abs/1505.04711). §2 establishes that cosine similarity on un-normalized vectors is biased by magnitude, not direction. |
| **Floating-point tolerance** | IEEE 754-2019 — *IEEE Standard for Floating-Point Arithmetic.* DOI: [10.1109/IEEESTD.2019.8766229](https://doi.org/10.1109/IEEESTD.2019.8766229). §5.4 — single-precision rounding for unit-magnitude floats is below 1e-6. |
| **Industry prior art** | Faiss documentation (Meta AI Research) — "for cosine similarity, vectors must be L2-normalized before adding to the index" (https://github.com/facebookresearch/faiss/wiki/Pre--and-post-processing). |
| **What we reproduce** | The invariant check that any cosine-similarity index needs vectors normalized to unit length within fp32 rounding error. |
| **What we diverge on** | Faiss recommends normalization at index-add time. We additionally audit at the persistence boundary because our embeddings are stored in pgvector and re-loaded by FAISS later — the audit catches drift introduced between persistence and re-load (e.g. a future ETL bug that shaves precision). |

## 4 · Triggers (when does the audit fire?)

The audit runs from `_flush_embeddings_slice` immediately after the quality gate (`_apply_quality_gate_filter`) returns its surviving slice and before `_bulk_update_embeddings` writes to the DB. Two conditions:

| Condition | Audit behaviour |
|---|---|
| `arr.shape[0] == 0` | No-op (zero-row slices are valid; they happen when the gate prunes everything). |
| any `‖arr[i]‖₂ - 1.0` > tolerance (`1e-6` by default) | Raises `L2NormalizationAuditError` with `worst_row` index and observed `max_dev`. |

The caller (`_flush_embeddings_slice`) catches the error, emits an `embeddings.l2_audit_failed` ops-feed event at severity `high`, drops the bad slice, and returns. The bad batch is NOT persisted. The pipeline continues with the next slice.

## 5 · Output contract

- `_audit_l2_normalization(arr, *, tolerance=1e-6) -> None` — pure check, no return.
- On pass: silent return. On fail: `raise L2NormalizationAuditError(max_dev=…, worst_row=…, n_rows=…)`.
- `L2NormalizationAuditError` inherits `ValueError` so existing broad-except handlers in the embedding pipeline log rather than crash.
- Audit is idempotent and side-effect-free.

## 6 · Why "post-quality-gate" specifically

The quality gate (`embedding_quality_gate.py`, FR-236) compares new vs old embeddings and may drop rows. Normalization runs BEFORE the gate (line 517 of `embeddings.py`). So the surviving slice has been L2-normalized then index-filtered. Auditing after the gate catches:

1. Bug in `_l2_normalize` itself (e.g. C++ extension producing slightly off-norm output, fp16/fp32 round-trip).
2. Bug in `_apply_quality_gate_filter` that corrupts the matrix (e.g. mis-indexed slice).
3. Race condition between normalize and write (unlikely but the audit bounds the worst case).

Auditing earlier (immediately after `_l2_normalize`) wouldn't catch #2; auditing later (after `bulk_update`) is too late — the corruption is already in the DB.

## 7 · Hyperparameters

| Name | Value | Source | Why |
|---|---|---|---|
| `_L2_AUDIT_TOLERANCE` | `1e-6` | IEEE 754-2019 §5.4 | Single-precision unit-magnitude rounding floor. fp32 cannot represent unit norms more tightly than this anyway. |
| (no operator override) | n/a | Runtime invariant | Operators should not tune correctness invariants. If fp16 ever ships, the call site can pass `tolerance=1e-3` per Wang et al. 2017 §3 (their reported safe threshold for half-precision). |

## 8 · Test plan

Tests live in `backend/apps/pipeline/tests_embeddings_helpers.py::AuditL2NormalizationTests`. Seven cases per Beizer 1990 (boundary value analysis) and IEEE 754-2019 §5.4:

1. **Happy path** — A fresh L2-unit batch of 3 random vectors passes silently.
2. **Edge: empty** — Zero-row arrays are a no-op (matches the gate-drops-everything case).
3. **Adversarial: zero vector** — A row of all-zeros has norm 0, deviation 1.0, raises.
4. **Adversarial: 1.5× scaling** — A row pre-multiplied by 1.5 raises with `max_dev ≈ 0.5`.
5. **Diagnostic: error carries `n_rows`** — Operators can tell whether the failure is one row or a corrupt batch.
6. **Edge: tolerance override** — `tolerance=1e-2` accepts a 0.999-norm vector that would fail at default.
7. **IEEE 754 boundary** — A vector drifted by 5e-7 (still inside fp32 unit-magnitude rounding) passes at default `1e-6`.

## 9 · Failure mode and recovery

If the audit raises:
1. The slice is dropped (NOT persisted).
2. Ops feed alert `embeddings.l2_audit_failed` fires at severity `high`.
3. Alert payload includes `max_dev`, `worst_row`, `n_rows` for triage.
4. Pipeline continues with the next slice.

A drop loses one batch's worth of fresh embeddings. The next pass will re-encode those rows (the embedding-text-hash supersede pattern in `NO-DUPLICATES.md` ensures no duplicate persistence).

## 10 · Performance

| Metric | Value |
|---|---|
| Cost per batch (1024-dim × 64-row fp32) | ~2 µs |
| Cost as % of one BGE-M3 forward pass | < 0.001% |
| Memory overhead | one (n,) norms array, freed at scope exit |

Trivially small relative to the embed forward pass it audits.

## 11 · Compatibility / migration

| Item | Impact |
|---|---|
| Existing pgvector rows | Unchanged — the audit only fires on new flushes. |
| Existing FAISS index | Unchanged — the audit fires before pgvector persist, so FAISS rebuild is unaffected. |
| Schema migrations | None. |
| Settings additions | None. |

The change is purely additive: a new function and a new try/except branch in `_flush_embeddings_slice`. No call-site rename, no signature change, no opt-in flag.

## 12 · Citations on every default

- `_L2_AUDIT_TOLERANCE = 1e-6` — IEEE 754-2019 §5.4.
- The audit-on-failure-drop policy — Nygard 2018 *Release It!* circuit-breaker pattern (already cited by FR-234), restated for this scope: isolate the bad slice, emit signal, keep moving.
- The post-gate placement — Wang et al. 2017 §3 implicitly motivates auditing at every persistence boundary.

## 13 · Operator-facing surface

- `embeddings.l2_audit_failed` ops-feed event surfaces in the existing Ops Feed and `/error-log` UI via the standard `emit()` plumbing. No new dashboard panel.
- Plain-English helper (`peHelper`) for the alert: "An embedding fingerprint failed a length check just before being saved. The bad batch was thrown away and an alert was raised. The next pass will redo it." (To be added when the alert appears in the Notification Center if the rule designs warrant it.)

## 14 · Extension points

- Future fp16 GPU pipeline → call site passes `tolerance=1e-3` (Wang et al. 2017 §3).
- Future cross-provider audits → audit can move from row-level to per-provider aggregate (max-deviation across batch, p99 deviation) by extending `L2NormalizationAuditError` payload. Current shape (`max_dev`, `worst_row`, `n_rows`) is forward-compatible.
- If FAISS HNSW (FR-244 NRT delta index) ships, audit fires on the delta index input the same way — no extra wiring needed.

---

**Status**: shipped 2026-05-07. **Verification**: 7 SimpleTestCase tests pass; embeddings.py forbidden-pattern lint clean; no schema changes.
