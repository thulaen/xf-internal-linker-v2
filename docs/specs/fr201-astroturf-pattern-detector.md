# FR-201 - AstroTurf Pattern Detector

## Overview
"AstroTurfing" is when a coordinated set of accounts pretends to be a grass-roots movement — a small group amplifies the same content while looking independent. The classic signals are: extreme retweet/share-to-original ratio, very young accounts, bursty posting, and a tight mention/reply network. This signal computes a per-user feature vector for those four dimensions and combines them into a single anomaly score via a weighted ensemble. Used as a multiplicative penalty on author trust.

## Academic source
**Ratkiewicz, Jacob; Conover, Michael; Meiss, Mark; Gonçalves, Bruno; Flammini, Alessandro; Menczer, Filippo (2011).** "Detecting and Tracking Political Abuse in Social Media." *Proceedings of the 5th International AAAI Conference on Weblogs and Social Media (ICWSM 2011)*, pp. 297-304. The four-feature ensemble in §3 — share-to-original ratio, account age, temporal burstiness, mention-network clustering — is the basis for this signal. Companion paper: Ratkiewicz et al., WWW 2011 Companion, "Truthy: Mapping the Spread of Astroturf in Microblog Streams", DOI: `10.1145/1963192.1963301`.

## Formula
Let `u` be a user with posts `P(u)`, of which `O(u)` are originals and `S(u) = P(u) \ O(u)` are shares/quotes.

**Feature 1 — share-to-original ratio:**
```
f₁(u) = |S(u)| / max(1, |O(u)|)
```

**Feature 2 — account-age penalty (younger = more suspicious):**
```
f₂(u) = exp(−age_days(u) / τ_age),   τ_age = 30
```

**Feature 3 — temporal burstiness (Kleinberg 2002 burst score):**
```
f₃(u) = max_t  burst(u, t) = max_t  log( λ_high(u, t) / λ_low(u, t) )
```
where `λ_high`, `λ_low` are the two-state HMM rate parameters fit per user.

**Feature 4 — mention-network clustering coefficient:**
```
f₄(u) = 2 · |E(N(u))| / (|N(u)| · (|N(u)| − 1))
```
where `N(u)` = users mentioned by `u`, `E(N(u))` = edges within `N(u)` in the mention graph.

**Combined astroturf score:**
```
astro(u) = w₁·f₁(u) + w₂·f₂(u) + w₃·f₃(u) + w₄·f₄(u)        (paper §3, weights tuned by grid search)

astro_penalty(u) = sigmoid(α · (astro(u) − τ)),   α = 4.0, τ = 0.50
```

## Starting weight preset
```python
"astroturf.enabled": "true",
"astroturf.ranking_weight": "0.0",
"astroturf.w_share_ratio": "0.30",
"astroturf.w_account_age": "0.20",
"astroturf.w_burstiness": "0.30",
"astroturf.w_clustering": "0.20",
"astroturf.tau_age_days": "30.0",
"astroturf.tau_decision": "0.50",
"astroturf.alpha_sigmoid": "4.0",
```

## C++ implementation
- File: `backend/extensions/astroturf_detector.cpp`
- Entry: `void astro_features(const UserPosts* posts, int n_users, const MentionGraph& mentions, double* out_features, double* out_score);`
- Complexity: `O(n_users · avg_posts) + O(|E_mentions|)` for clustering
- Thread-safety: per-user feature computation parallelised via OpenMP; mention graph read-only
- Burst HMM uses Welford-online variance to stay single-pass
- Builds against pybind11

## Python fallback
`backend/apps/pipeline/services/astroturf.py::compute_astroturf(...)` — uses `numpy` for HMM and `networkx` for clustering coefficient.

## Benchmark plan
| Users | C++ target | Python target |
|---|---|---|
| 1 K | < 50 ms | < 1 s |
| 10 K | < 500 ms | < 15 s |
| 100 K | < 5 s | < 4 min |

## Diagnostics
- Per-user feature vector `(f₁, f₂, f₃, f₄)` and combined `astro(u)`
- Top-10 most-burst-like accounts
- Per-feature contribution to final score
- C++ vs Python badge

## Edge cases & neutral fallback
- User with `< 5` posts → neutral `0.0`, flag `too_few_posts`
- User with no mentions → `f₄ = 0` (clustering undefined, treated as zero)
- Account age `> 5` years → `f₂` saturates at `exp(−1825/30) ≈ 0`
- Mention graph empty → skip `f₄`, re-normalise weights
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
`≥ 5` posts per user AND `≥ 7 days` of posting history before the score is trusted; below this returns neutral `0.0`.

## Budget
Disk: <2 MB  ·  RAM: <60 MB at 100 K users (per-user feature struct + mention CSR)

## Scope boundary vs existing signals
FR-201 does NOT overlap with FR-200 SybilGuard — that uses graph mixing time. FR-201 uses *behavioural* features (timing, share ratio, mention clustering). It is also distinct from FR-202 clickbait classifier (text-only) and FR-206 account-age gravity (positive boost for old accounts; FR-201 is a penalty for young + bursty accounts).

## Test plan bullets
- unit tests: lone organic poster (low all features), bot-like account (high `f₁` + low `f₂`), burst account (high `f₃`)
- parity test: C++ vs Python combined score within `1e-3`
- regression test: legitimate news-aggregator users (high `f₁` by design) must be allow-listed
- integration test: ranking unchanged when `ranking_weight = 0.0`
- weight-sum test: `w₁ + w₂ + w₃ + w₄ = 1.0` enforced at config load
- HMM determinism test: fixed seed + fixed posts → identical `f₃`
