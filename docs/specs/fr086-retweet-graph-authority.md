# FR-086 - Retweet Graph Authority

## Confirmation

- **Backlog confirmed**: `FR-086 - Retweet Graph Authority` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No reshare-graph authority signal exists in the current ranker. The closest signals are FR-006 (link-graph PageRank) and FR-074 (influence score on referral graph). FR-086 computes PageRank specifically on the reshare/amplification graph -- a third distinct graph structure.
- **Repo confirmed**: GA4 social sharing and reshare data can be derived from referral and event data.

## Source Summary

### Patent: US8370326B2 -- Retweet Graph Authority (Twitter)

**Plain-English description of the patent:**

The patent describes computing authority scores specifically from the retweet (reshare) graph. Unlike general PageRank (which uses hyperlink structure) or social influence (which uses follower networks), retweet-graph authority measures how content is amplified through sharing chains. Pages shared by users who are themselves frequently reshared carry more authority.

**What is adapted for this repo:**

- "retweet graph" maps to GA4 social share events and referral chains specifically identified as sharing actions;
- Personalized PageRank is computed on this reshare-specific graph;
- distinct from link-graph PageRank (FR-006) and referral-graph influence (FR-074).

## Plain-English Summary

Simple version first.

When someone shares a page, and then someone shares that share, and then someone shares that -- the page sits at the root of an amplification chain. Pages at the centre of many amplification chains have demonstrated content that people actively want to spread.

FR-086 computes PageRank on this sharing/amplification graph. It is distinct from link-graph authority (FR-006, based on internal links) and referral influence (FR-074, based on general traffic flow).

## Problem Statement

Today the ranker uses link-graph PageRank (editorial structure) and referral influence (traffic flow). Neither captures the specific amplification patterns from social sharing. A page might have few internal links but be heavily reshared on social platforms.

FR-086 closes this gap by computing authority from the reshare graph.

## Goals

FR-086 should:

- add a separate, explainable, bounded reshare-graph authority signal;
- compute Personalized PageRank on the reshare graph;
- normalize to `[0, 1]` relative to corpus maximum;
- keep pages with no reshare data neutral at `0.5`.

## Non-Goals

FR-086 does not:

- modify FR-006 (link-graph PageRank) or FR-074 (influence score);
- connect to social media APIs;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `G_share = (V, E_share)` be the reshare graph where edges represent sharing/amplification events
- `w(i, j)` = number of reshare events from user/page `i` to user/page `j`
- `d = 0.15` (damping factor, matching FR-074)

**Reshare-graph PageRank:**

```text
PR_share(i) = d / |V| + (1 - d) * sum(PR_share(j) * w(j, i) / out_degree(j) for j in in_neighbors(i))
```

Computed via power iteration until convergence (`||PR_new - PR_old||_1 < 1e-6`).

**Normalized score:**

```text
score_retweet_authority = 0.5 + 0.5 * (PR_share(page) / max(PR_share(v) for v in V))
```

**Neutral fallback:**

```text
score_retweet_authority = 0.5
```

Used when:

- page has no reshare edges;
- reshare data unavailable;
- feature is disabled.

### Ranking hook

```text
score_retweet_component =
  max(0.0, min(1.0, 2.0 * (score_retweet_authority - 0.5)))
```

```text
score_final += retweet_authority.ranking_weight * score_retweet_component
```

## Scope Boundary Versus Existing Signals

FR-086 must stay separate from:

- `FR-006` link-graph PageRank -- uses internal link graph, not reshare graph.
- `FR-074` influence score -- uses general referral graph, not sharing-specific graph.
- `FR-069` viral depth -- measures depth of sharing chains, not graph centrality.

## Inputs Required

- GA4 social share events and reshare referral chains
- Reshare graph construction from event data

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `retweet_authority.enabled`
- `retweet_authority.ranking_weight`
- `retweet_authority.damping`
- `retweet_authority.lookback_days`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `damping = 0.15`
- `lookback_days = 90`

## Diagnostics And Explainability Plan

Required fields:

- `score_retweet_authority`
- `retweet_authority_state` (`computed`, `neutral_feature_disabled`, `neutral_no_reshare_data`, `neutral_processing_error`)
- `raw_pagerank` -- unnormalized PageRank value on reshare graph
- `corpus_max_pagerank` -- normalization denominator
- `reshare_edge_count` -- number of reshare edges involving this page

Plain-English review helper text should say:

- `Retweet graph authority measures this page's centrality in the social sharing network.`
- `A high score means the page is at the centre of many sharing chains.`

## Storage / Model / API Impact

### Content model

Add:

- `score_retweet_authority: FloatField(default=0.5)`
- `retweet_authority_diagnostics: JSONField(default=dict, blank=True)`

### Backend API

Add:

- `GET /api/settings/retweet-authority/`
- `PUT /api/settings/retweet-authority/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"retweet_authority.enabled": "true",
"retweet_authority.ranking_weight": "0.02",
"retweet_authority.damping": "0.15",
"retweet_authority.lookback_days": "90",
```
