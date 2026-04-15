# FR-179 — Normalized Pointwise Mutual Information (NPMI)

## Overview
NPMI is the bounded variant of PMI: divide PMI by `−log P(x, y)` and the result lies in `[−1, +1]`. The fixed scale removes PMI's notorious overweighting of rare-pair coincidences and produces a value that is comparable across corpora and pair families. NPMI is the standard collocation/association measure in modern computational linguistics. For internal linking, NPMI is the preferred form when blending association into a weighted ranking sum because its scale is stable and intuitive. Complements `fr178-pointwise-mutual-information` (raw PMI) and `fr180-log-likelihood-ratio-term-association` (LLR for significance).

## Academic source
Bouma, G. "Normalized (pointwise) mutual information in collocation extraction." *Proceedings of the German Society for Computational Linguistics and Language Technology Conference (GSCL 2009)*, pp. 31–40, 2009. URL: https://svn.spraakdata.gu.se/repos/gerlof/pub/www/Docs/npmi-pfd.pdf. Earlier mention: Schütze, H. (1992) and various unpublished notes.

## Formula
From Bouma (2009), Eq. 4 — NPMI is PMI divided by negative log of the joint probability:

```
NPMI(x, y) = PMI(x, y) / ( − log P(x, y) )

where
  PMI(x, y) = log( P(x, y) / ( P(x) · P(y) ) )       (FR-178)
  P(x, y)   = count(x, y) / N
```

Range: `NPMI ∈ [−1, +1]`.
- `NPMI = +1` ⇒ perfect co-occurrence (`x` and `y` always appear together)
- `NPMI = 0`  ⇒ independence
- `NPMI = −1` ⇒ never co-occur

Convenient mapping for ranking blends (already in `[0, 1]`):

```
NPMI_ranking(x, y) = max(0, NPMI(x, y))
```

## Starting weight preset
```python
"npmi.enabled": "true",
"npmi.ranking_weight": "0.0",
"npmi.window_size_W": "10",
"npmi.log_base": "2",
"npmi.smoothing_epsilon": "0.5",
"npmi.clamp_negative_to_zero": "true",
```

## C++ implementation
- File: `backend/extensions/npmi.cpp`
- Entry: `double npmi(uint64_t count_xy, uint64_t count_x, uint64_t count_y, uint64_t total_n)`
- Complexity: O(1) per pair given counts; reuses PMI scaffolding from FR-178
- Thread-safety: pure function; lookup tables read-only
- Builds via pybind11; single division by `-log(p_joint)` after PMI

## Python fallback
`backend/apps/pipeline/services/npmi.py::compute_npmi` using FR-178's PMI followed by `pmi / (-math.log2(p_joint))`.

## Benchmark plan

| Size | pairs evaluated | C++ target | Python target |
|---|---|---|---|
| Small | 1,000 | 0.005 ms | 0.5 ms |
| Medium | 100,000 | 0.4 ms | 50 ms |
| Large | 10,000,000 | 30 ms | 4,500 ms |

## Diagnostics
- NPMI value rendered as "NPMI: 0.62 (strong association)"
- Underlying PMI and `−log P(x, y)` shown side-by-side
- C++/Python badge
- Debug fields: `pmi`, `joint_log_prob`, `clamped_to_zero` (boolean), `window_size_W`

## Edge cases & neutral fallback
- `count(x, y) = 0` ⇒ undefined `−log(0)` ⇒ apply add-ε smoothing (default ε = 0.5)
- `count(x, y) = N` (perfect co-occurrence) ⇒ `−log P(x,y) → 0` ⇒ NPMI tends to +1 by definition; clip to +1 to avoid 0/0
- `P(x, y) = P(x) · P(y)` (independence) ⇒ PMI = 0 ⇒ NPMI = 0
- `clamp_negative_to_zero`: when ranking-blending, set `NPMI ← max(0, NPMI)` so anti-correlation does not erroneously penalise via negative weight
- Single-event corpus (`N = 1`) ⇒ degenerate; neutral fallback

## Minimum-data threshold
Need `count(x) ≥ 5` and `count(y) ≥ 5` and `count(x, y) ≥ 3` for stable NPMI; otherwise neutral 0.5.

## Budget
Disk: shared with FR-178 sketch · RAM: same lookup tables

## Scope boundary vs existing signals
NPMI strictly extends `fr178-pointwise-mutual-information` by normalising to a fixed range. NPMI is the *recommended* form for ranking blends; raw PMI is exposed only for diagnostics. Distinct from `fr180-log-likelihood-ratio-term-association` which provides a *significance test*, not a normalised effect size.

## Test plan bullets
- Unit: perfect co-occurrence ⇒ NPMI = +1
- Unit: independent pair ⇒ NPMI ≈ 0
- Unit: zero joint count after smoothing ⇒ NPMI strongly negative (close to −1)
- Range: NPMI always in `[−1, +1]` for any input
- Parity: C++ vs Python within 1e-6 on 1,000 pairs
- Edge: degenerate `P(x,y) = 1` clipped to NPMI = +1
- Integration: deterministic across runs given fixed sketch
- Regression: top-50 ranking unchanged when weight = 0.0
