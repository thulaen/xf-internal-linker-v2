# FR-190 — Host Age Boost

## Overview
Newly registered domains carry meaningfully higher spam risk than long-lived ones; conversely, hosts that have been around for years and accumulated organic backlinks deserve a small authority bonus. A sigmoid activation on host age (years since first crawl or WHOIS creation date) gives a smooth, bounded boost that floors near zero for brand-new hosts and saturates near one for hosts older than the operator-chosen threshold. Complements `fr007-link-freshness-authority` because freshness measures the *page* age while host-age boost measures the *host* age.

## Academic source
Full citation: **Ward, J. et al. (2015).** "Information retrieval based on historical data." US Patent No. **8,972,390 B2**. Filed Mar. 22, 2010; granted Mar. 3, 2015. Assignee: Google Inc. Claims 1, 4, and 12 describe age-based score boosting using a sigmoid activation. Cross-confirmed against the 2024 **Google API Content Warehouse leak** (May 2024), attribute `siteAuthority.hostAgeInDays` confirmed in the `CompressedQualitySignals` proto.

## Formula
US 8,972,390 B2, Claim 4: a sigmoid activation centred at threshold `τ` with slope `β`, applied to host age in days:

```
boost(h) = 1 / (1 + exp(−β · (age(h) − τ)))

where
  age(h) = days since first observation of host h
           (WHOIS creation date, or first crawl date if WHOIS unavailable)
  τ      = age threshold in days; default 365 (one year)
  β      = sigmoid slope; default 0.005 (gives transition window of ~400 days)
```

Properties:
- `age = 0` → `boost ≈ 0.135` (newborn host, near floor)
- `age = τ` → `boost = 0.5` (neutral midpoint)
- `age = τ + 600` → `boost ≈ 0.953` (well-aged host)

## Starting weight preset
```python
"host_age.enabled": "true",
"host_age.ranking_weight": "0.0",
"host_age.threshold_days": "365",
"host_age.slope_beta": "0.005",
```

## C++ implementation
- File: `backend/extensions/host_age.cpp`
- Entry: `double host_age_boost(int age_days, int tau, double beta)`
- Complexity: O(1) per host
- Thread-safety: pure; no shared state
- SIMD: AVX2 batched sigmoid via fast `exp` approximation when scoring large host vectors
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/host_age.py::compute_host_age_boost` using `numpy` vectorised sigmoid (`scipy.special.expit`).

## Benchmark plan

| Size | Hosts | C++ target | Python target |
|---|---|---|---|
| Small | 100 | 0.005 ms | 0.05 ms |
| Medium | 10,000 | 0.4 ms | 5 ms |
| Large | 1,000,000 | 35 ms | 400 ms |

## Diagnostics
- Per-host boost value (e.g. "Age boost: 0.78 (host 4.2 yrs)")
- Source of age signal: `whois | first_crawl | unknown`
- C++/Python badge
- Fallback flag when age unknown
- Debug fields: `age_days`, `threshold_days`, `slope_beta`, `age_source`

## Edge cases & neutral fallback
- Host age unknown → neutral 0.5, fallback flag set
- WHOIS lookup failed → fall back to first-crawl date
- Host older than 30 years (likely WHOIS error) → cap at 30 years
- Negative age (clock skew) → treat as 0

## Minimum-data threshold
Either WHOIS creation date or first-crawl date must be available; if both missing return neutral 0.5.

## Budget
Disk: 0.1 MB  ·  RAM: 0.5 MB

## Scope boundary vs existing signals
Distinct from `fr007-link-freshness-authority` (page-level recency of the destination URL) and from `fr050-seasonality-temporal-demand` (cyclic temporal demand). Host-age boost is a per-host trust prior derived solely from registration or first-observation date.

## Test plan bullets
- Unit: age = 0 returns boost ≈ 0.135
- Unit: age = 365 returns boost = 0.5 with default τ
- Unit: age = 1000 returns boost ≈ 0.953
- Parity: C++ vs Python on 1,000-host fixture within 1e-9
- Edge: WHOIS missing falls back to first-crawl date
- Edge: unknown age returns neutral 0.5 with fallback flag
- Integration: boost contributes additively when weight > 0
- Regression: ranking unchanged when weight = 0.0
