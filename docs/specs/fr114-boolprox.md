# FR-114 - BoolProx (Boolean Conjunction Weighted by Proximity)

## Overview
Strict Boolean AND retrieval is brittle (one missing query term excludes the document) and pure proximity scoring is noisy on long documents. BoolProx multiplies a soft-Boolean score (a smooth approximation of "all query terms present") with a proximity factor, giving a result that is conservative on coverage but rewards locality. Complements FR-008 phrase matching because BoolProx allows partial-coverage matches with a continuous penalty rather than the binary phrase-hit gate.

## Academic source
**Svore, Krysta M.; Kanani, Pallika H.; Khan, Nazan (2011).** "How Good is a Span of Terms? Exploiting Proximity to Improve Web Retrieval." *Proceedings of the 33rd International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR 2010)*, pp. 154-161. DOI: `10.1145/1835449.1835477`. (Note: Microsoft Research published this in SIGIR 2010 / continued WSDM 2011 work; the BoolProx model is the SIGIR 2010 Eq. 5 variant.)

## Formula
From Svore, Kanani, Khan (2010), Eq. 5 (BoolProx scoring function):

```
soft_AND(Q, D) = ∏_{q ∈ Q}  ( 1 − exp( − γ · tf(q, D) ) )

prox_factor(Q, D) = exp( − β · minSpan(Q, D) / |D| )

BoolProx(Q, D) = soft_AND(Q, D) · prox_factor(Q, D)
```

Where:
- `tf(q, D)` = term frequency
- `minSpan(Q, D)` = shortest interval covering all query terms in `D` (same as FR-112)
- `|D|` = document length
- `γ > 0` = soft-AND saturation (default 0.5 per paper §4.1; lower means stricter "must be present")
- `β > 0` = proximity decay (default 1.0; higher means stronger preference for short spans)
- `(1 − e^{−γ·tf})` ∈ `(0, 1)` is a smooth gate: 0 when `tf = 0`, → 1 as `tf` grows; the product over query terms enforces soft conjunction
- `e^{−β·minSpan/|D|}` ∈ `(0, 1]` is the proximity factor, normalised by document length

## Starting weight preset
```python
"boolprox.enabled": "true",
"boolprox.ranking_weight": "0.0",
"boolprox.gamma": "0.5",
"boolprox.beta": "1.0",
```

## C++ implementation
- File: `backend/extensions/boolprox.cpp`
- Entry: `double boolprox_score(const uint32_t* query_term_ids, int n, const PositionalDoc& doc, double gamma, double beta);`
- Complexity: `O(|D| · |Q|)` for `minSpan` (shared with FR-112), then `O(|Q|)` for soft-AND
- Thread-safety: pure function
- SIMD: soft-AND product has `|Q|` `exp` calls; precomputed `1−e^{−γ·t}` LUT for `t ∈ [0, 100]`
- Builds against pybind11 like FR-099

## Python fallback
`backend/apps/pipeline/services/boolprox.py::score_boolprox(...)`.

## Benchmark plan
| Candidates | C++ target | Python target |
|---|---|---|
| 10 | < 0.1 ms | < 1 ms |
| 100 | < 0.5 ms | < 5 ms |
| 500 | < 2.5 ms | < 25 ms |

## Diagnostics
- Soft-AND value, proximity factor, and product
- C++ vs Python badge
- Per-term `(1 − e^{−γ·tf(q)})` factors
- `minSpan` and `minSpan/|D|` ratio

## Edge cases & neutral fallback
- Any `tf(q) = 0` → that factor in soft-AND is 0 → score = 0; flag `term_missing`
- `Q ∩ D = ∅` → 0.0
- `|Q| = 1` → soft-AND is just `(1 − e^{−γ·tf})`; minSpan = 1 so prox = `e^{−β/|D|}` ≈ 1
- `|D| = 0` → 0.0, flag `empty_doc`
- No positional data → use proximity factor of `e^{−β}` (worst case) and flag `no_positions`
- NaN / Inf → 0.0, flag `nan_clamped`

## Minimum-data threshold
Document with positional data; corpus stats not required. Below positional availability, returns neutral 0.5.

## Budget
Disk: <1 MB  ·  RAM: <10 MB

## Scope boundary vs existing signals
FR-114 does NOT duplicate FR-008 phrase matching because FR-008 is a binary all-or-nothing phrase test, while BoolProx is a continuous soft-AND × proximity score. It does not duplicate FR-112 MinSpan because MinSpan ignores `tf`; BoolProx weights by both `tf` (via soft-AND) and span (via proximity factor).

## Test plan bullets
- unit tests: every term tf=0 (score=0), all tf=1 contiguous, all tf=1 spread, single-term query
- parity test: C++ vs Python within `1e-4`
- limit checks: `γ → ∞` recovers strict Boolean AND; `β = 0` removes proximity factor
- monotonicity: increasing tf for any term cannot decrease soft-AND
- no-crash test on adversarial input (`γ = 0`, `|D|` very large)
- integration test: ranking unchanged when `ranking_weight = 0.0`
