# FR-191 — Subdomain Diversity Penalty

## Overview
A common spam pattern is to spin up dozens of low-content subdomains under a single registered host (`a.spam.example`, `b.spam.example`, …) where each subdomain hosts thin, near-duplicate pages. Counting the fraction of low-content subdomains under a given host gives a cheap penalty signal that catches this pattern without any link-graph work. Complements `fr189-badrank-inverse-pagerank` because BadRank catches spammy outbound link patterns while subdomain diversity penalty catches spammy hosting topology.

## Academic source
Full citation: **Bharat, K., Chang, B.-W., Henzinger, M. R., & Ruhl, M. (2001).** "Who links to whom: Mining linkage between web sites." In *Proceedings of the 2001 IEEE International Conference on Data Mining (ICDM '01)*, pp. 51-58. DOI: `10.1109/ICDM.2001.989501`. The earlier methodological work, **Bharat, K., Henzinger, M., et al. (1998)**, frames host vs. subdomain aggregation in the SIGIR '98 paper cited under FR-186; the WWW 2001 follow-up extends the idea to subdomain-level analysis.

## Formula
Bharat et al. (2001), Section 4: penalise hosts where most subdomains carry insufficient content. Define `low_content(s) = 1` iff subdomain `s` has fewer than `θ` indexed pages with non-boilerplate body length above `λ` characters:

```
penalty(H) = (num_low_content_subdomains(H) / num_subdomains(H)) · γ

where
  num_subdomains(H)              = |{ s : s is a subdomain of H }|
  num_low_content_subdomains(H)  = |{ s : low_content(s) = 1 }|
  γ                              = penalty scale factor in [0, 1]
                                   default 1.0
  θ                              = page-count threshold; default 5
  λ                              = body-length threshold; default 500 chars
```

Final ranker contribution is the inverse: `1 − penalty(H)` so high diversity earns full credit and dense low-content topology earns near-zero.

## Starting weight preset
```python
"subdomain_diversity.enabled": "true",
"subdomain_diversity.ranking_weight": "0.0",
"subdomain_diversity.gamma": "1.0",
"subdomain_diversity.page_threshold": "5",
"subdomain_diversity.body_length_threshold": "500",
```

## C++ implementation
- File: `backend/extensions/subdomain_diversity.cpp`
- Entry: `double subdomain_diversity_penalty(const std::vector<SubdomainStats>& subs, double gamma, int theta, int lambda)`
- Complexity: O(|subdomains|) per host
- Thread-safety: pure on input slice; no shared state
- SIMD: not warranted (small per-host loops)
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/subdomain_diversity.py::compute_subdomain_diversity_penalty` using a precomputed Postgres aggregate over `ContentItem` grouped by `host_aggregate.subdomain`.

## Benchmark plan

| Size | Subdomains | C++ target | Python target |
|---|---|---|---|
| Small | 10 | 0.005 ms | 0.1 ms |
| Medium | 200 | 0.05 ms | 2 ms |
| Large | 5,000 | 1.2 ms | 40 ms |

## Diagnostics
- Per-host penalty value (e.g. "Subdomain penalty: 0.82 — 41/50 thin subs")
- Sample list of low-content subdomains
- C++/Python badge
- Fallback flag when subdomain count below minimum
- Debug fields: `num_subdomains`, `num_low_content`, `theta`, `lambda`

## Edge cases & neutral fallback
- Single subdomain (just `www.example.com`) → neutral 0.5 (insufficient diversity to evaluate)
- All subdomains content-rich → `penalty = 0`, ranker contribution = 1.0
- All subdomains thin → `penalty = γ`, ranker contribution = `1 − γ`
- Host with subdomain wildcards (DNS) but few crawled → fall back to neutral

## Minimum-data threshold
At least 3 distinct subdomains must be observed before signal contributes; otherwise fall back to neutral 0.5.

## Budget
Disk: 0.2 MB  ·  RAM: 1 MB

## Scope boundary vs existing signals
Distinct from `fr187-host-trustrank` (link-graph propagation), `fr189-badrank-inverse-pagerank` (inverse-PR), and `fr054-boilerplate-content-ratio` (per-page boilerplate). Subdomain diversity penalty is a host-topology signal computed without traversing the link graph.

## Test plan bullets
- Unit: 10 subdomains, 9 thin → penalty = 0.9
- Unit: 10 subdomains, 0 thin → penalty = 0
- Parity: C++ vs Python on 1,000-host fixture within 1e-9
- Edge: single subdomain returns neutral 0.5 with fallback flag
- Edge: subdomain count < 3 returns neutral 0.5
- Integration: `1 − penalty` contributes additively when weight > 0
- Regression: ranking unchanged when weight = 0.0
