# FR-133 — Quota-Based Diversity

## Overview
PM2 (FR-128) gives proportional aspect representation but uses fractional Sainte-Laguë seats which can produce surprising integer allocations. Sometimes operators want a strict, hand-set quota — e.g. "at least 2 'tutorial' threads, at most 3 'review' threads, exactly 1 'official announcement' in every slate of 10." Capannini et al. (2011) formalise this as the *quota-based diversification* problem: given upper and lower per-class quotas, pick the top-K subset that satisfies all quotas while maximising relevance. On a forum this is the right method when category mix is a hard editorial requirement, not a soft preference. Complements FR-128 because PM2 gives soft proportionality while quota-based gives hard min/max constraints — different operator-control axes.

## Academic source
**Capannini, G., Nardini, F. M., Perego, R., & Silvestri, F. (2011).** "Efficient Diversification of Web Search Results." *Proceedings of the 34th International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR 2011)*, Beijing, China, pages 1297-1298 (poster). Extended in: Capannini, G., et al. (2011). *Proceedings of the VLDB Endowment*, 4(7), 451-459. DOI: `10.14778/1988776.1988779`.

## Formula
The quota-constrained selection problem from Capannini et al. (2011), Section 3:

```
Maximise   Σ_{d ∈ S}  rel(d, q)
Subject to:
    |S| = K                                              (slate size)
    L_c ≤ |S ∩ class_c| ≤ U_c    for each class c        (per-class quotas)
    S ⊆ V                                                (candidates universe)

Where:
    V                   = candidate pool
    class_c ⊆ V         = documents in class c (e.g. category, type, author)
    L_c, U_c ∈ ℤ_{≥0}   = lower and upper quotas for class c (operator-set)
    Σ_c L_c ≤ K ≤ Σ_c U_c                               (feasibility constraint)
```

This is an Integer Linear Programme (ILP) but Capannini et al. give a polynomial-time greedy algorithm (their Algorithm 2) that is exact when `Σ L_c = K` (all slots are committed by lower quotas) and a `(1 - 1/K)` approximation otherwise:

```
Algorithm 2 (Capannini et al. 2011):
    1. For each class c, take top-L_c documents by rel(d,q) → "committed picks"
    2. Remaining_slots = K - Σ_c L_c
    3. From remaining candidates (excluding committed), greedily pick by rel(d,q)
       subject to per-class upper bound U_c
       Stop when remaining_slots = 0 or no eligible candidate exists.
```

## Starting weight preset
```python
"quota_diversity.enabled": "true",
"quota_diversity.ranking_weight": "0.0",
"quota_diversity.class_source": "destination_category",
"quota_diversity.target_slate_size": "10",
"quota_diversity.lower_quotas_json": "{}",
"quota_diversity.upper_quotas_json": "{}",
```

(Operators set the per-class lower/upper quotas via the settings UI as JSON dictionaries keyed by class name.)

## C++ implementation
- File: `backend/extensions/quota_diversity.cpp`
- Entry: `std::vector<int> quota_pick(const float* relevance, const int* class_ids, const int* lower_quotas, const int* upper_quotas, int n_candidates, int n_classes, int target_k)`
- Complexity: O(n log n) for the initial relevance sort + O(K) for the quota-aware second pass
- Thread-safety: stateless; uses `std::sort` then linear scan
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/quota_diversity.py::quota_pick` — pure-Python sort-and-scan implementation.

## Benchmark plan
| Candidates × classes | Slate K | C++ target | Python target |
|---|---|---|---|
| small (50 × 5) | 5 | <0.05 ms | <0.5 ms |
| medium (500 × 10) | 10 | <0.3 ms | <5 ms |
| large (5000 × 50) | 20 | <2 ms | <40 ms |

## Diagnostics
- Per-class allocation log in suggestion detail UI (`quota_diversity_diagnostics.allocation_log`)
- C++/Python badge
- Fallback flag
- Signal-specific fields: `lower_quotas_used`, `upper_quotas_used`, `committed_picks_per_class`, `remaining_picks_per_class`, `quota_satisfaction_status` (one of `all_satisfied`, `infeasible_lower_too_large`, `relaxed_lower_to_fit`)

## Edge cases & neutral fallback
- Infeasible quotas (`Σ L_c > K`) → relax lower quotas proportionally until feasible, flag `quotas_relaxed`
- Some class has zero candidates → that class's lower quota cannot be satisfied → relax it to 0, flag
- `Σ U_c < K` → fewer than K total picks possible → return all eligible, flag `slate_short_by_quota`
- All quotas zero → degenerates to top-K by relevance; short-circuit and flag
- NaN relevance scores → clamp to 0 (rank last); flag

## Minimum-data threshold
At least one quota with `L_c > 0` or `U_c < n_class` (otherwise no diversification happens); at least K candidates with at least one per non-zero-lower class.

## Budget
Disk: <1 MB  ·  RAM: <5 MB at n=5000 (relevance + class id + per-class counters in int32/float32)

## Scope boundary vs existing signals
- **FR-128 PM2**: PM2 gives soft proportional allocation via Sainte-Laguë; quota-based gives hard min/max integer constraints.
- **FR-126/127 IA-Select/xQuAD**: aspect-coverage maximisation, no per-class slot guarantee.
- **FR-129 DPP / FR-130 submodular**: continuous diversity scores, no per-class enforcement.
- **FR-015 final-slate diversity reranking**: pairwise-dissimilarity reranking, no class concept.

## Test plan bullets
- correctness test: paper's Section 4.2 example (10 candidates, 3 classes, L=[2,1,1], U=[5,3,2], K=5) → quota_pick output matches Algorithm 2 trace exactly
- feasibility-check test: `Σ L_c = 11 > K = 10` → algorithm relaxes lower quotas proportionally and flags
- upper-bound test: relevance-sorted-only would pick 8 from class A but `U_A = 3` → quota_pick caps at 3, fills remainder from B/C
- approximation-bound test: when `Σ L_c < K`, brute-force optimum on small instances → quota_pick score ≥ (1 - 1/K) · OPT
- parity test: C++ vs Python within 1e-6 (deterministic — no randomness)
- no-crash on adversarial input: empty class with non-zero lower quota, all-classes-empty, K = 0, NaN relevance
- integration test: `ranking_weight = 0.0` (i.e. all quotas zero) leaves ranking unchanged
- determinism: stable sort + lower-index tie-break → identical slate across runs
