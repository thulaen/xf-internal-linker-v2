# FR-049 — Query Intent Funnel Alignment

**Status:** Pending
**Requested:** 2026-04-06
**Target phase:** TBD
**Priority:** Medium
**Depends on:** FR-016 (GA4 integration), FR-017 (GSC integration)

---

## Confirmation

- `FR-049` is a new backlog item being added to `FEATURE-REQUESTS.md` in this session.
- Repo confirmed:
  - no ranking signal currently models user intent stage or buyer-journey progression;
  - `FR-047` (navigation path prediction) models where users *actually go* based on observed transitions, but not where they *should logically go next* based on intent stage;
  - `FR-025` (session co-occurrence) detects pages appearing together in sessions, not sequential intent progression;
  - `FR-011` (field-aware relevance) scores title/body alignment, not intent-stage matching;
  - GSC query data imported by FR-017 provides the raw query strings needed to classify intent.

## Current Repo Map

### Existing nearby signals

- `FR-047` navigation path prediction
  - models observed page-to-page transitions;
  - it does not reason about *why* users navigate or what intent stage they are in.

- `FR-025` session co-occurrence
  - detects unordered page co-presence in sessions;
  - it does not model sequential funnel progression.

- `FR-013` explore/exploit feedback reranking
  - balances exploitation of known-good suggestions with exploration of untested ones;
  - it does not model intent stages or funnel logic.

- `FR-016` / `FR-017` GA4/GSC content value
  - aggregates traffic and search metrics;
  - it does not classify pages or queries by intent stage.

### Gap this FR closes

The repo cannot currently detect that a source page serves informational intent ("what is mechanical keyboard") and should link to a commercial-investigation page ("best mechanical keyboards 2026") rather than another informational page or a transactional checkout page. Without intent-stage awareness, the ranker treats all relevant destinations equally regardless of where they sit in the buyer journey.

## Source Summary

### Patent: WO2015200404A1 — Query Intent Identification from Reformulations

Plain-English read:

- the patent describes methods for classifying search queries into intent categories based on query reformulation patterns;
- when users refine queries, the progression reveals their underlying intent (browsing → researching → buying);
- intent classification can be used to select and rank results that match the user's current stage.

Repo-safe takeaway:

- query intent can be approximated from GSC query strings already in the system;
- the useful classification is a small set of intent stages, not a complex taxonomy;
- intent-stage matching between source and destination is a lightweight scoring operation.

### Patent: US20110289063A1 — Determining Query Intent

Plain-English read:

- the patent describes scoring queries by intent type using lexical features and click patterns;
- queries containing commercial modifiers ("best", "vs", "review", "buy", "price", "deal") strongly signal intent stage;
- the method uses token-level features rather than deep NLP, making it fast and deterministic.

Repo-safe takeaway:

- intent classification can be done with simple keyword pattern matching in v1;
- no external API or ML model is required for a useful first version;
- the signal can be refined later with learned classifiers if keyword patterns prove too coarse.

### Academic basis: Buyer journey / search funnel models

Plain-English read:

- the standard search marketing funnel has four stages: informational, commercial investigation, transactional, and navigational;
- users progress through stages as their intent matures;
- content that matches the next logical stage in the funnel converts better than content at a random stage.

Repo-safe takeaway:

- internal links that guide users forward through the funnel create better user journeys;
- the optimal link moves the user one stage forward, not two or backward;
- the math is a simple adjacency penalty on a 4-node funnel graph.

## Plain-English Summary

Simple version first.

People searching online go through stages.
First they ask "what is X?" (learning).
Then "which X is best?" (comparing).
Then "buy X" (purchasing).

FR-049 figures out which stage each page serves.
Then it boosts links that move users to the next logical stage.

Example:

- Source page: "What Are Mechanical Keyboards?" (informational)
- Good link target: "Best Mechanical Keyboards in 2026" (commercial investigation) — one stage forward
- Okay link target: "Mechanical Keyboard History" (informational) — same stage, no progression
- Poor link target: "Add Cherry MX Red to Cart" (transactional) — skips a stage

## Problem Statement

Today the ranker scores destinations by topical relevance, authority, engagement, and structural signals — but none of them model where the source and destination sit in the user's intent journey. Two destinations can be equally relevant and equally authoritative, but one moves the user logically forward through the funnel while the other keeps them at the same stage or jumps them ahead too far.

FR-049 adds an intent-stage alignment signal so the ranker can prefer links that create coherent user journeys.

## Goals

FR-049 should:

- classify each page into one of four intent stages using GSC query data and content keyword patterns;
- compute a funnel alignment score between source and destination based on intent-stage distance;
- boost links that move users one stage forward in the funnel;
- gently penalize links that skip stages or move backward;
- stay neutral when intent classification confidence is low or data is missing;
- use simple keyword pattern matching in v1 — no external NLP or ML models required.

## Non-Goals

FR-049 does not:

- replace or modify FR-047 (navigation path prediction remains a separate behavioural signal);
- build a full query classification ML model in v1 — keyword patterns are sufficient;
- handle per-user personalization or individual visitor intent;
- model funnels deeper than one stage forward — multi-hop journey optimization is out of scope;
- modify GSC data ingestion — it consumes existing query data already imported by FR-017.

## Math-Fidelity Note

### Intent stage taxonomy

Define four ordered intent stages:

```text
STAGES = {
  0: "navigational",    # user wants a specific page ("reddit login", "amazon")
  1: "informational",   # user wants to learn ("what is X", "how does X work")
  2: "commercial",      # user wants to compare ("best X", "X vs Y", "X review")
  3: "transactional"    # user wants to act ("buy X", "X discount", "X coupon")
}
```

### Step 1 — classify pages by intent stage

For each page, collect GSC queries that triggered impressions for that URL. Classify each query using keyword pattern matching:

```text
navigational_patterns = ["login", "sign in", "homepage", "official site", brand_name]
informational_patterns = ["what is", "how to", "why does", "guide", "tutorial",
                          "explain", "definition", "meaning", "example"]
commercial_patterns    = ["best", "top", "vs", "versus", "review", "comparison",
                          "alternative", "recommend", "which"]
transactional_patterns = ["buy", "price", "cost", "discount", "coupon", "deal",
                          "order", "purchase", "shop", "subscribe", "download",
                          "free trial", "sign up", "get started"]
```

For each query `q`, assign stage scores:

```text
stage_score(q, s) = count of patterns from stage s matched in q
```

Aggregate across all queries for a page `p`:

```text
page_stage_votes(p, s) = Σ  impression_weight(q) * stage_score(q, s)
                         q ∈ queries(p)
```

Where `impression_weight(q) = log(1 + impressions(q))` to prevent one high-impression query from dominating.

### Step 2 — assign primary intent stage

```text
primary_stage(p) = argmax  page_stage_votes(p, s)
                   s ∈ {0,1,2,3}
```

Compute classification confidence:

```text
total_votes(p) = Σ page_stage_votes(p, s)
                 s

confidence(p) = page_stage_votes(p, primary_stage(p)) / max(total_votes(p), ε)
```

Where `ε = 1e-9`.

If no GSC queries exist, fall back to content-only classification using the same keyword patterns against `ContentItem.title` and `ContentItem.distilled_text`, with `confidence(p) = 0.3` (low confidence for content-only classification).

### Step 3 — compute funnel distance

For a source page `s` and destination page `d`:

```text
stage_distance = primary_stage(d) - primary_stage(s)
```

Interpretation:

| `stage_distance` | Meaning | Quality |
|---|---|---|
| +1 | One stage forward | Optimal |
| 0 | Same stage | Neutral |
| +2 | Two stages forward | Acceptable but skips |
| -1 | One stage backward | Mild penalty |
| +3 | Three stages forward | Heavy skip penalty |
| -2 or worse | Far backward | Heavy penalty |

### Step 4 — funnel alignment score

Map stage distance to a score using a peaked function centred on +1:

```text
alignment_raw(s, d) = exp(-((stage_distance - optimal_offset)^2) / (2 * sigma^2))
```

Where:

- `optimal_offset = 1` — the ideal link moves users one stage forward
- `sigma = 1.2` — controls how quickly the score drops for non-optimal distances

This produces a Gaussian curve peaked at `stage_distance = +1`:

| `stage_distance` | `alignment_raw` |
|---|---|
| -2 | 0.026 |
| -1 | 0.245 |
| 0 | 0.707 |
| +1 | 1.000 |
| +2 | 0.707 |
| +3 | 0.245 |

### Step 5 — confidence-damped bounded score

Apply confidence damping from both source and destination classifications:

```text
joint_confidence = min(confidence(s), confidence(d))
```

```text
score_intent_funnel = 0.5 + 0.5 * joint_confidence * alignment_raw(s, d)
```

Score range:

- `0.5` = neutral (low confidence or poor alignment)
- `1.0` = high confidence, optimal one-stage-forward alignment

Neutral fallback:

```text
score_intent_funnel = 0.5
```

Used when:

- feature disabled;
- source or destination has no GSC queries and no classifiable content keywords;
- `joint_confidence` is below `min_confidence` threshold.

### Step 6 — navigational page exception

Navigational pages (stage 0) are typically brand/login pages that should not participate in funnel scoring. When either source or destination is classified as navigational with high confidence:

```text
if primary_stage(s) == 0 or primary_stage(d) == 0:
    if confidence >= navigational_confidence_threshold:
        score_intent_funnel = 0.5  # neutral, opt out
```

Recommended default:

- `navigational_confidence_threshold = 0.6`

### Ranking hook

```text
score_intent_funnel_component =
  max(0.0, min(1.0, 2.0 * (score_intent_funnel - 0.5)))
```

```text
score_final += intent_funnel.ranking_weight * score_intent_funnel_component
```

Default:

- `ranking_weight = 0.0`

## Scope Boundary Versus Existing Signals

FR-049 must stay separate from:

- `FR-047` navigation path prediction
  - FR-047 models where users *actually navigate* (observed Markov transitions);
  - FR-049 models where users *should logically go next* (intent funnel stages).

- `FR-025` session co-occurrence
  - FR-025 detects unordered page co-presence;
  - FR-049 models directed intent progression.

- `FR-013` explore/exploit
  - FR-013 balances known-good vs. untested suggestions;
  - FR-049 scores by intent-stage alignment.

- `FR-016` / `FR-017` GA4/GSC content value
  - FR-016/017 aggregate traffic metrics;
  - FR-049 classifies queries by intent type, not traffic volume.

- `score_semantic` (w_semantic)
  - semantic similarity measures topical overlap;
  - FR-049 measures intent-stage progression regardless of topic.

Hard rule:

- FR-049 must not mutate GSC import data, query records, or other feature caches.

## Inputs Required

FR-049 v1 can use:

- GSC query strings and impression counts per URL (already imported by FR-017)
- `ContentItem.title` and `ContentItem.distilled_text` for content-only fallback classification
- Keyword pattern lists for each intent stage (shipped as a static config, not a learned model)

Explicitly disallowed in v1:

- external intent classification APIs;
- ML-based query classifiers (v2 enhancement);
- per-user intent profiling;
- real-time query stream processing.

## Data Model Plan

Add to `ContentItem`:

- `intent_stage` — integer (0-3) primary intent classification
- `intent_confidence` — float classification confidence
- `intent_stage_votes` — JSON field storing per-stage vote counts for diagnostics

Add to `Suggestion`:

- `score_intent_funnel`
- `intent_funnel_diagnostics`

## Settings And Feature-Flag Plan

Recommended keys:

- `intent_funnel.enabled`
- `intent_funnel.ranking_weight`
- `intent_funnel.optimal_offset`
- `intent_funnel.sigma`
- `intent_funnel.min_confidence`
- `intent_funnel.navigational_confidence_threshold`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `optimal_offset = 1`
- `sigma = 1.2`
- `min_confidence = 0.25`
- `navigational_confidence_threshold = 0.6`

## Diagnostics And Explainability Plan

Diagnostics should include:

- `source_stage` and `source_stage_label`
- `source_confidence`
- `dest_stage` and `dest_stage_label`
- `dest_confidence`
- `stage_distance`
- `alignment_raw`
- `joint_confidence`
- `top_source_queries` (cap 3, showing query and classified stage)
- `top_dest_queries` (cap 3)
- `classification_method` ("gsc_queries" or "content_fallback")
- `fallback_state`

Plain-English helper text:

- "Intent funnel alignment boosts links that guide users forward through the search journey — from learning about a topic, to comparing options, to taking action."

## Native Performance Plan

This is a later ranking-affecting FR, so it must plan a native fast path.

### C++ default path

Add a native batch scorer that reads cached intent stages and computes Gaussian alignment scores across all suggestion pairs.

Suggested file:

- `backend/extensions/intentfunnel.cpp`

### Python fallback

Add:

- `backend/apps/pipeline/services/intent_funnel.py`

The Python and C++ paths must produce the same bounded scores for the same intent classifications.

### Visibility requirement

Expose:

- native enabled / fallback enabled;
- why fallback is active;
- whether native batch scoring is materially faster.

## Backend Touch Points

- `backend/apps/content/models.py`
- `backend/apps/suggestions/models.py`
- `backend/apps/core/views.py`
- `backend/apps/pipeline/services/intent_funnel.py`
- `backend/apps/pipeline/services/ranker.py`
- `backend/apps/pipeline/tasks.py`
- `backend/extensions/intentfunnel.cpp`

## Verification Plan

Later implementation must verify at least:

1. informational → commercial investigation link scores higher than informational → informational;
2. one-stage-forward alignment produces the maximum score;
3. two-stage skips and backward links produce lower but non-zero scores;
4. navigational pages opt out and receive neutral 0.5;
5. pages with no GSC data fall back to content-only classification with reduced confidence;
6. `ranking_weight = 0.0` leaves ranking unchanged;
7. confidence damping blends toward neutral for low-confidence classifications;
8. C++ and Python paths produce identical scores;
9. diagnostics explain the intent stage, distance, and alignment for each suggestion.
