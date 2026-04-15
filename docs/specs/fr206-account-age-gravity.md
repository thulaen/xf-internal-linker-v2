# FR-206 - Account-Age Gravity

## Overview
Older accounts have had more time to demonstrate good behaviour and have more skin in the game; newer accounts are statistically more likely to be spam, sock-puppet, or burner. The "gravity" formulation gives a smooth saturating boost — diminishing returns as accounts age — rather than a hard cliff. Used as an additive author-trust boost so threads from established members rank above identical content from accounts created last week.

## Academic source
**US Patent 8,972,390** (Google, 2015). "Ranking documents based on author trust." Inventor: Phil Stanhope et al. Assigned 3 March 2015. The patent's "author tenure factor" in claim 4 (exponential saturation curve over account age) is the basis for this signal. Companion academic source: **Adler, B. T. and de Alfaro, L. (2007).** "A Content-Driven Reputation System for the Wikipedia." *Proceedings of the 16th International Conference on World Wide Web (WWW 2007)*, pp. 261-270, DOI: `10.1145/1242572.1242608` — §3.2 derives the same exponential tenure boost from edit-survival statistics.

## Formula
For author `u` with account age `age_days(u)`, the gravity boost is the saturating exponential:
```
boost(u) = 1 − exp(−age_days(u) / τ)               (Patent claim 4, Eq. analogous to Adler & de Alfaro §3.2)
```

Where `τ` is the time-constant. Choosing `τ` controls the half-saturation point:
- `τ = 90 d` → 50% saturation at `~62 d`, 95% at `~270 d`
- `τ = 365 d` → 50% saturation at `~253 d`, 95% at `~1095 d`

Optional first-action gating (patent claim 6):
```
boost_gated(u) = boost(u) · 1{ first_post_date(u) ≤ today − 7 d }
```
to avoid rewarding accounts that are old but only just started posting.

Final additive boost is already in `[0, 1]`.

## Starting weight preset
```python
"account_age_gravity.enabled": "true",
"account_age_gravity.ranking_weight": "0.0",
"account_age_gravity.tau_days": "90.0",
"account_age_gravity.first_post_gate_days": "7",
"account_age_gravity.use_first_post_gate": "true",
```

## C++ implementation
- File: `backend/extensions/account_age_gravity.cpp`
- Entry: `void age_gravity(const double* age_days, int n, double tau, double* out_boost);`
- Complexity: `O(n)` — single elementwise `exp`
- Thread-safety: pure function on per-author array
- SIMD: `_mm256_exp_pd` via SVML or AVX2 polynomial approximation (4 ULP)
- Builds against pybind11

## Python fallback
`backend/apps/pipeline/services/account_age_gravity.py::age_gravity(...)` — `numpy.exp` over the age vector.

## Benchmark plan
| Authors | C++ target | Python target |
|---|---|---|
| 1 K | < 0.1 ms | < 1 ms |
| 100 K | < 5 ms | < 50 ms |
| 10 M | < 500 ms | < 5 s |

## Diagnostics
- Per-author `age_days`, `boost`, and gated `boost_gated`
- Histogram of `age_days` and `boost` across population
- Whether first-post gate suppressed any author (count + percentage)
- C++ vs Python badge

## Edge cases & neutral fallback
- Account creation date missing → neutral `0.0`, flag `unknown_age`
- Account age `< 0` (clock skew or imported bad data) → clamp to `0`, flag `negative_age_clamped`
- Account age `> 30 years` → boost saturates near `1.0`, no special handling
- First post gate active and `first_post_date` missing → treat as recent, gate trips, flag `unknown_first_post`
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
Account must have at least its creation date populated; below this returns neutral `0.0`. No minimum corpus size required.

## Budget
Disk: <1 MB  ·  RAM: <80 MB at 10 M authors (per-author float64 age + float64 boost)

## Scope boundary vs existing signals
FR-206 does NOT overlap with FR-204 author H-index (impact-based, not tenure-based) or FR-205 co-authorship PageRank (graph-based). It is also distinct from FR-201 AstroTurf detection — FR-206 is a *positive boost* for old accounts; FR-201 is a *penalty* for young + bursty accounts. The two are complementary and can be combined linearly.

## Test plan bullets
- unit tests: `age = 0` → `boost = 0`; `age = τ` → `boost ≈ 0.632`; `age = 5τ` → `boost ≈ 0.993`
- parity test: C++ vs Python `boost` within `1e-6`
- gate test: account age `1 year` but first post yesterday → `boost_gated = 0`
- monotonicity test: `boost` strictly non-decreasing in `age_days`
- integration test: ranking unchanged when `ranking_weight = 0.0`
- numeric stability test: `age = 1e9 d` does not overflow `exp`
