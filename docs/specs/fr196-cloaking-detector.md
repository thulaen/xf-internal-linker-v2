# FR-196 - Cloaking Detector

## Overview
Cloaking is the spam tactic of serving one version of a page to a search-engine crawler and a different version to a human browser. Within a forum corpus this also covers user-agent-targeted redirects and conditional script injection. The signal compares the rendered content seen by a browser user-agent against the content seen by a bot user-agent of the *same* URL — if the two differ materially, the page is suspicious. Used as a multiplicative penalty in the final ranker so cloaked candidates fall below clean ones.

## Academic source
**Wu, Baoning and Davison, Brian D. (2005).** "Cloaking and Redirection: A Preliminary Study." *Proceedings of the 1st International Workshop on Adversarial Information Retrieval on the Web (AIRWeb 2005)*, pp. 7-16, in conjunction with WWW 2005. DOI: `10.1145/1060745.1060754`. The paper introduces the bot-vs-browser fetch comparison and shingle-based dissimilarity score that this signal implements.

## Formula
From Wu & Davison (2005), Eq. 1:

```
cloak_score(u) = 1 − sim(C_browser(u), C_bot(u))

sim(A, B) = |shingles(A) ∩ shingles(B)| / |shingles(A) ∪ shingles(B)|       (Jaccard, k-shingle=4)
```

Where:
- `C_browser(u)` = visible text fetched with a browser User-Agent
- `C_bot(u)` = visible text fetched with a Googlebot User-Agent
- `shingles(X)` = set of overlapping `k`-grams over normalised tokens (`k = 4`)
- `cloak_score ∈ [0, 1]` — `0` = identical, `1` = completely different

Optional cosine variant for low-shingle docs:
```
sim_cos(A, B) = (v_A · v_B) / (||v_A|| · ||v_B||)         where v = tf-idf vector
```

Final penalty applied at rank time:
```
cloak_penalty(u) = max(0, 1 − cloak_score(u))           ← multiplied into raw rank score
```

## Starting weight preset
```python
"cloaking.enabled": "true",
"cloaking.ranking_weight": "0.0",
"cloaking.shingle_k": "4",
"cloaking.threshold": "0.30",
"cloaking.use_cosine_fallback": "true",
```

## C++ implementation
- File: `backend/extensions/cloaking_detector.cpp`
- Entry: `double cloak_score(const char* text_browser, const char* text_bot, int shingle_k);`
- Complexity: `O(|A| + |B|)` shingle hash + `O(min(|A|,|B|))` set intersection
- Thread-safety: pure function on byte buffers
- SIMD: `_mm256_crc32_u64` shingle hashing, `xxhash` fallback
- Builds against pybind11 like other detectors

## Python fallback
`backend/apps/pipeline/services/cloaking.py::detect_cloaking(...)` — used when extension unavailable or for ad-hoc checks.

## Benchmark plan
| Documents | C++ target | Python target |
|---|---|---|
| 10 (1KB ea) | < 0.5 ms | < 5 ms |
| 100 (1KB ea) | < 5 ms | < 50 ms |
| 500 (5KB ea) | < 50 ms | < 500 ms |

## Diagnostics
- Raw `cloak_score` per URL
- Browser vs bot text length, shingle overlap count, Jaccard ratio
- Whether cosine fallback was triggered
- Crawl timestamp of each fetch (must be within 10 min of each other)

## Edge cases & neutral fallback
- Either fetch failed → neutral `0.0`, flag `fetch_failed`
- Both texts < 50 tokens → neutral `0.0`, flag `text_too_short`
- Identical bytes → `0.0`, flag `byte_identical`
- Cookie-wall page → strip cookie banners before comparing, flag `cookie_wall_stripped`
- NaN / Inf → `0.0`, flag `nan_clamped`

## Minimum-data threshold
≥ 50 tokens in *both* fetches before the score is trusted; below this returns neutral `0.0` with flag.

## Budget
Disk: <1 MB  ·  RAM: <8 MB (shingle sets capped at 4096 entries each)

## Scope boundary vs existing signals
FR-196 does NOT overlap with FR-198 (keyword stuffing) or FR-199 (content spin) — those compare a single rendered page against a corpus baseline. FR-196 compares two fetches of the *same* URL under different user agents. It also does not overlap with the canonical/duplicate detection in FR-014.

## Test plan bullets
- unit tests: identical pages, fully cloaked pages, partial cloaking
- parity test: C++ vs Python within `1e-4` Jaccard
- adversarial test: pages with random ad slots (must NOT trigger cloaking)
- integration test: ranking unchanged when `ranking_weight = 0.0`
- regression test: cookie-wall pages do not trip the detector
- timing test: comparison completes within 50 ms for 5 KB pages
