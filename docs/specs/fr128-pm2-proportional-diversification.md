# FR-128 — PM2 Proportional Diversification

## Overview
xQuAD (FR-127) and IA-Select (FR-126) maximise aspect coverage but make no guarantee about *proportional* representation. If aspect A has probability 0.6 and aspect B has 0.4, the slate may end up 8-2 instead of the proportional 6-4. PM2 (Proportionality-based diversification Method) explicitly allocates slate slots to aspects in proportion to their probability using the Sainte-Laguë divisor method (the same algorithm used in proportional-representation elections). On a forum this means operators get exactly the topic mix they asked for. Complements FR-127 because xQuAD lets aspect coverage drift; PM2 enforces it.

## Academic source
**Dang, V., & Croft, W. B. (2012).** "Diversity by Proportionality: An Election-based Approach to Search Result Diversification." *Proceedings of the 35th International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR 2012)*, Portland, OR, pages 65-74. DOI: `10.1145/2348283.2348296`.

## Formula
From Dang & Croft (2012), Eqs. 1-4 (PM2 with Sainte-Laguë quotient):

```
For each pick at position k+1, given current slate S of size k:

Step 1 (quotient computation, Eq. 2 — Sainte-Laguë divisor):
    qt(c_i) = v(c_i) / (2 · s(c_i) + 1)

Step 2 (aspect selection, Eq. 3):
    c* = argmax_{c_i}  qt(c_i)

Step 3 (document selection, Eq. 4):
    d* = argmax_{d ∉ S}   λ · qt(c*) · P(d | c*)
                        + (1 - λ) · Σ_{c_i ≠ c*}  qt(c_i) · P(d | c_i)

Step 4 (seat allocation update, Eq. 5):
    For each aspect c_i:
        s(c_i) ← s(c_i) + P(d* | c_i) / Σ_{c_j} P(d* | c_j)

Where:
    v(c_i)     ∈ [0, 1], aspect probability (votes), Σ_i v(c_i) = 1
    s(c_i)     ∈ ℝ_{≥0}, current "seats" allocated to aspect c_i (initially 0)
    P(d | c)   ∈ [0, 1], probability d satisfies aspect c
    qt(c_i)    = Sainte-Laguë quotient (favours under-represented aspects)
    λ ∈ [0,1]  = relevance-to-target-aspect vs collateral-aspect-coverage trade-off
                 (paper default λ = 0.5)
```

The Sainte-Laguë divisor `(2s + 1)` is the unique divisor that minimises representation bias against small aspects (Balinski & Young, 2001 result on apportionment).

## Starting weight preset
```python
"pm2.enabled": "true",
"pm2.ranking_weight": "0.0",
"pm2.lambda_proportionality": "0.5",
"pm2.aspect_source": "host_classified_topics",
"pm2.target_slate_size": "10",
```

## C++ implementation
- File: `backend/extensions/pm2.cpp`
- Entry: `std::vector<int> pm2_pick(const float* aspect_votes, int n_aspects, const float* doc_aspect_matrix, int n_candidates, int target_k, float lambda)`
- Complexity: O(K · (|C| + n · |C|)) = O(K · n · |C|) — for each of K picks, compute |C| quotients then score n candidates over |C| aspects
- Thread-safety: stateless; SIMD over aspects per candidate
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/pm2.py::pm2_pick` — NumPy implementation with vectorised quotient and seat-update steps.

## Benchmark plan
| Candidates × aspects | Slate K | C++ target | Python target |
|---|---|---|---|
| small (50 × 5) | 5 | <0.05 ms | <0.6 ms |
| medium (500 × 20) | 10 | <0.5 ms | <10 ms |
| large (5000 × 50) | 20 | <8 ms | <150 ms |

## Diagnostics
- Per-position aspect-allocation log in suggestion detail UI (`pm2_diagnostics.pick_log`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `aspect_votes`, `quotients_per_pick`, `selected_aspect_per_pick`, `seat_allocation_progression`, `final_proportionality_error` (L1 distance between target votes and final seat distribution)

## Edge cases & neutral fallback
- Single aspect with vote = 1.0 → degenerates to top-K by `P(d|c)`; flag
- Zero candidates → empty slate
- All-zero document-aspect matrix → flag and fall back to relevance ranking
- `λ = 0` or `λ = 1` boundaries → behaviour follows the paper (extreme proportionality vs extreme target-only); flag if outside [0.1, 0.9]
- NaN/Inf in matrices → clamp; flag

## Minimum-data threshold
At least 2 aspects with `v(c) > 0.05` AND at least `K` candidates; otherwise skip.

## Budget
Disk: <1 MB  ·  RAM: <25 MB at 5000 × 50 doc-aspect matrix in float32 + per-aspect seat/quotient vectors

## Scope boundary vs existing signals
- **FR-126 IA-Select**: maximises coverage but not proportionality (winner-takes-most aspects).
- **FR-127 xQuAD**: trade-off between relevance and aspect coverage but no proportionality guarantee.
- **FR-129 DPP**: determinant-based diversity, no aspect concept at all.
- **FR-133 quota-based diversity**: hard quotas (integer per-class limits); PM2 uses fractional Sainte-Laguë seats which give smoother allocation when aspects overlap.

## Test plan bullets
- correctness test: paper's Table 1 example (3 aspects with votes [0.5, 0.3, 0.2], slate of 10) → final seat allocation matches Sainte-Laguë proportional allocation (5, 3, 2) within 0.1 seats
- proportionality test: as K → ∞, seat allocation L1-converges to vote distribution (paper Theorem 1)
- λ-sweep test: λ near 0 minimises proportionality error; λ near 1 maximises it
- parity test: C++ vs Python within 1e-6
- election-equivalence test: PM2 with binary doc-aspect matrix (each doc satisfies exactly one aspect) reduces exactly to Sainte-Laguë seat allocation on `n` parties
- no-crash on adversarial input: zero candidates, all-zeros matrix, single aspect, vote vector that doesn't sum to 1 (renormalise)
- integration test: `ranking_weight = 0.0` leaves ranking unchanged
- determinism: tie-breaking by lower index → identical slate across runs
