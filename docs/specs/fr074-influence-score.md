# FR-074 - Influence Score

## Confirmation

- **Backlog confirmed**: `FR-074 - Influence Score` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No social influence or reshare-graph authority signal exists in the current ranker. The closest existing signal is `score_authority` (link-graph PageRank via FR-006). FR-074 measures authority in the social reshare graph -- a fundamentally different graph structure.
- **Repo confirmed**: GA4 referral and sharing data is already ingested via the analytics sync pipeline.

## Source Summary

### Patent: US20140019539A1 -- Influence Score (Google)

**Plain-English description of the patent:**

The patent describes computing influence scores for entities (users, content) based on how content propagates through a social network. Influence is measured by the reach and authority of reshare chains -- content shared by influential people who are themselves reshared carries more weight than content shared by inactive accounts.

**Repo-safe reading:**

The patent uses Google+ social graph data. This repo uses GA4 referral chains and session data as a proxy. The reusable core idea is:

- build a reshare graph from referral chain data;
- compute PageRank on the reshare graph (not the link graph);
- pages with high reshare-graph centrality have demonstrated social influence.

**What is adapted for this repo:**

- "social graph" maps to GA4 referral chains (page-to-page traffic flow);
- PageRank is computed on this referral graph, separate from the internal link graph;
- damping factor set to 0.15 (standard PageRank default).

## Plain-English Summary

Simple version first.

Some pages are influential hubs in the referral network -- lots of other pages send traffic to them, and the pages sending traffic are themselves highly trafficked. This is like PageRank, but computed on the traffic-flow graph rather than the internal link graph.

FR-074 computes this social influence score. It rewards destination pages that sit at central positions in the referral network -- pages that people actually share and reference, not just pages that happen to have many internal links.

Think of it this way: FR-006 asks "does this page have many internal links pointing to it?" FR-074 asks "does this page receive traffic from influential referral sources?"

## Problem Statement

Today the ranker uses link-graph PageRank (FR-006) for authority. This measures internal link structure, which is under editorial control and may not reflect actual traffic patterns. A page with many internal links but no real traffic appears authoritative when it may not be.

FR-074 closes this gap by computing authority from actual referral traffic patterns.

## Goals

FR-074 should:

- add a separate, explainable, bounded social influence score;
- compute PageRank on the GA4 referral graph at index time;
- use damping factor 0.15 (standard);
- normalize scores to `[0, 1]` relative to the corpus maximum;
- keep pages with no referral data neutral at `0.5`;
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-074 does not:

- modify the link-graph PageRank (FR-006);
- build a real-time social network;
- track individual users;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `G = (V, E)` be the referral graph where vertices are pages and edges represent referral traffic
- `w(i, j)` = number of referral sessions from page `i` to page `j` in the lookback window
- `d = 0.15` (damping factor)

**Referral-graph PageRank:**

```text
PR(i) = d / |V| + (1 - d) * sum(PR(j) * w(j, i) / sum(w(j, k) for k in out(j)) for j in in(i))
```

Computed via power iteration until convergence (`||PR_new - PR_old||_1 < 1e-6`).

**Normalized score:**

```text
score_influence = 0.5 + 0.5 * (PR(page) / max(PR(v) for v in V))
```

This maps:

- lowest-centrality page -> `score ~ 0.5`
- highest-centrality page -> `score = 1.0`

**Neutral fallback:**

```text
score_influence = 0.5
```

Used when:

- page has no referral edges;
- GA4 referral data is unavailable;
- feature is disabled.

### Why separate from link-graph PageRank

The link graph is editorial (controlled by content authors). The referral graph is behavioural (driven by actual user traffic). They capture different kinds of authority. A page can have high link-graph rank but low referral-graph rank (well-linked but rarely visited) or vice versa.

### Ranking hook

```text
score_influence_component =
  max(0.0, min(1.0, 2.0 * (score_influence - 0.5)))
```

```text
score_final += influence_score.ranking_weight * score_influence_component
```

Default: `ranking_weight = 0.0` -- diagnostics only until validated.

## Scope Boundary Versus Existing Signals

FR-074 must stay separate from:

- `FR-006` weighted link graph -- uses internal link graph, not referral graph.
- `FR-069` viral propagation depth -- measures sharing chain depth, not graph centrality.
- `FR-070` viral recipient ranking -- measures visitor quality, not page centrality.
- `FR-086` retweet graph authority -- uses reshare/retweet-specific graph, not general referral graph.

Hard rule: FR-074 must not modify the link-graph PageRank computation or its stored values.

## Inputs Required

- GA4 referral session data (source page -> destination page traffic flows)
- Page-level referral counts -- from existing analytics sync

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `influence_score.enabled`
- `influence_score.ranking_weight`
- `influence_score.damping`
- `influence_score.lookback_days`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `damping = 0.15`
- `lookback_days = 90`

Bounds:

- `0.0 <= ranking_weight <= 0.10`
- `0.05 <= damping <= 0.50`
- `7 <= lookback_days <= 365`

## Diagnostics And Explainability Plan

Required fields:

- `score_influence`
- `influence_state` (`computed`, `neutral_feature_disabled`, `neutral_no_referral_data`, `neutral_processing_error`)
- `raw_pagerank` -- unnormalized PageRank value
- `corpus_max_pagerank` -- max PR in corpus (normalization denominator)
- `inbound_referral_count` -- number of pages referring traffic to this page
- `outbound_referral_count` -- number of pages this page refers traffic to

Plain-English review helper text should say:

- `Influence score measures this page's centrality in the referral traffic network.`
- `A high score means the page receives traffic from other influential pages -- a sign of genuine authority.`

## Storage / Model / API Impact

### Content model

Add:

- `score_influence: FloatField(default=0.5)`
- `influence_diagnostics: JSONField(default=dict, blank=True)`

### PipelineRun snapshot

Add FR-074 settings and algorithm version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/influence-score/`
- `PUT /api/settings/influence-score/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"influence_score.enabled": "true",
"influence_score.ranking_weight": "0.02",
"influence_score.damping": "0.15",
"influence_score.lookback_days": "90",
```

**Why these values:**

- `ranking_weight = 0.02` -- conservative. Referral-graph authority is derived data and should be validated before increasing weight.
- `damping = 0.15` -- standard PageRank damping. Higher values spread authority more uniformly; lower values concentrate it at hub pages.
- `lookback_days = 90` -- three months of referral data gives a stable graph without stale edges dominating.
