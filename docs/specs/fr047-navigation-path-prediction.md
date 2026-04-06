# FR-047 — Navigation Path Prediction

**Status:** Pending
**Requested:** 2026-04-06
**Target phase:** TBD
**Priority:** Medium
**Depends on:** FR-016 (GA4 integration for page_view event data)

---

## Confirmation

- `FR-047` is a new backlog item being added to `FEATURE-REQUESTS.md` in this session.
- Repo confirmed:
  - no ranking signal currently models ordered navigation sequences;
  - `FR-025` (session co-occurrence) checks whether two pages appear in the same session but ignores visit order;
  - `FR-024` (engagement signal) measures dwell time on individual pages, not transitions between pages;
  - GA4 `page_view` events already flow into the system via `FR-016`, providing the raw session-ordered data this signal needs.

## Current Repo Map

### Existing nearby behaviour signals

- `FR-025` session co-occurrence
  - counts how many sessions contain both page A and page B;
  - it treats sessions as unordered sets — `{A, B}` is the same as `{B, A}`;
  - it cannot detect that users commonly navigate from A to B but rarely from B to A.

- `FR-024` engagement signal
  - measures how long users stay on a single page;
  - it does not model transitions between pages.

- `FR-023` hot decay
  - measures traffic recency and volume;
  - it does not model which pages users visit before or after a given page.

### Gap this FR closes

The repo cannot currently detect that users frequently navigate from page A to page C through an intermediate page X (A → X → C), and recommend a direct A → C link to shortcut the journey.

Co-occurrence knows "A and C appear together in sessions" but cannot tell you "users go FROM A TO C" (directional) or "users take a detour through X to get there" (indirect path).

## Source Summary

### Patent: US7584181B2 — Implicit Links Search Enhancement System and Method

Plain-English read:

- the patent mines user access logs to find pages that users visit in sequence;
- sequential visit patterns create an "implicit link" between pages even when no explicit hyperlink exists;
- these implicit links are used to build a secondary link graph that improves retrieval and ranking;
- the strength of an implicit link is proportional to how often the sequential visit pattern is observed.

Repo-safe takeaway:

- ordered navigation sequences contain directional information that unordered co-occurrence misses;
- the useful raw facts are transition counts between page pairs within sessions;
- the math is a first-order Markov transition matrix — no complex deep learning required.

### Academic basis: Markov chain models for web navigation

Plain-English read:

- a first-order Markov chain models the probability of visiting page B next, given that the user is currently on page A;
- transition probabilities are estimated by counting how often users go from A to B, divided by total exits from A;
- higher-order patterns (A → X → C shortcuts) are captured by multiplying transition matrices or by direct multi-hop counting.

Repo-safe takeaway:

- transition probabilities are cheap to compute from existing GA4 session data;
- multi-hop shortcut detection only requires comparing direct vs. indirect path probabilities;
- the signal is strongest for high-traffic pages with clear user journeys.

## Plain-English Summary

Simple version first.

Users leave footprints as they move through a site.
Those footprints form paths.
Some paths have shortcuts that do not exist yet as links.

FR-047 watches the paths users actually take and finds places where a direct link would save them steps.

Example:

- Users on the "Gaming Chairs" page often click to "Desk Accessories", then click to "Monitor Arms".
- There is no direct link from "Gaming Chairs" to "Monitor Arms".
- FR-047 detects this common A → X → C pattern and boosts "Monitor Arms" as a link destination for the "Gaming Chairs" page.

## Problem Statement

Today the ranker knows which pages appear together in sessions (FR-025) but not the direction or sequence of those visits. It cannot detect:

1. **Directional intent:** users go from A to B far more than from B to A.
2. **Navigation shortcuts:** users frequently reach C from A via a multi-hop detour through intermediate pages.
3. **Journey completion:** which destination pages tend to be the "final stop" in user journeys originating from a given source page.

FR-047 adds an ordered-sequence signal so the ranker can recommend links that match real user navigation intent.

## Goals

FR-047 should:

- build a first-order Markov transition matrix from GA4 page_view event sequences;
- compute directional transition probabilities between page pairs;
- detect high-value indirect paths (shortcuts) where no direct link exists;
- produce a bounded suggestion-level score that boosts destinations users are already navigating toward;
- stay neutral when session data is missing, sparse, or below confidence thresholds;
- fit the repo without requiring real-time streaming — batch daily aggregation is fine.

## Non-Goals

FR-047 does not:

- replace or modify FR-025 (co-occurrence remains a separate, complementary signal);
- use real-time clickstream data — daily batch aggregation is sufficient for v1;
- model individual user profiles or personalize per-visitor;
- require deep learning or sequence models — first-order Markov chains are the v1 scope;
- modify GA4 data ingestion — it consumes existing page_view events already imported by FR-016.

## Math-Fidelity Note

### Input data

Use GA4 `page_view` events grouped by `ga_session_id`, ordered by `event_timestamp`.

Let:

- `S` = set of all sessions with at least 2 page_view events in the lookback window
- `S_i` = ordered sequence of page URLs in session `i`: `[p_1, p_2, ..., p_n]`

### Step 1 — build transition counts

For every session `S_i`, extract consecutive page pairs:

```text
For each session [p_1, p_2, ..., p_n]:
  For j = 1 to n-1:
    T[p_j][p_{j+1}] += 1
```

Where `T[a][b]` is the raw count of transitions from page `a` to page `b`.

### Step 2 — compute transition probabilities

For each source page `a`:

```text
exits(a) = Σ T[a][b]  for all b
           b

P(b | a) = T[a][b] / max(exits(a), 1)
```

`P(b | a)` is the probability that a user on page `a` navigates to page `b` next.

### Step 3 — detect indirect shortcuts

For a candidate link from source `s` to destination `d`, compute the indirect path probability through all possible intermediate pages:

```text
P_indirect(d | s) = Σ P(x | s) * P(d | x)  for all intermediate pages x ≠ s, x ≠ d
                    x
```

The shortcut value is the gap between indirect reachability and direct reachability:

```text
shortcut_value(s, d) = max(0, P_indirect(d | s) - P_direct(d | s))
```

Where `P_direct(d | s) = P(d | s)` from Step 2.

A high shortcut value means users are already trying to get from `s` to `d` but have to take a detour.

### Step 4 — combined navigation score

Blend the direct transition signal and the shortcut signal:

```text
raw_nav_score(s, d) = w_direct * P_direct(d | s) + w_shortcut * shortcut_value(s, d)
```

Recommended defaults:

- `w_direct = 0.6` — direct transitions are the strongest evidence
- `w_shortcut = 0.4` — shortcuts are valuable but noisier

### Step 5 — normalize to [0, 1]

Per source page, normalize across all candidate destinations:

```text
max_raw(s) = max(raw_nav_score(s, d))  for all d in candidate set
             d

nav_norm(s, d) = raw_nav_score(s, d) / max(max_raw(s), ε)
```

Where `ε = 1e-9` prevents division by zero.

### Step 6 — bounded score

```text
score_navigation_path = 0.5 + 0.5 * nav_norm(s, d)
```

Neutral fallback:

```text
score_navigation_path = 0.5
```

Used when:

- feature disabled;
- source page has fewer than `min_sessions` total sessions;
- transition count `T[s][d]` (direct or indirect) is below `min_transition_count`;
- no GA4 page_view data available.

### Step 7 — confidence gate

To prevent noisy scores from low-traffic pages:

```text
confidence(s, d) = min(1.0, T_total(s, d) / min_transition_count)
```

Where `T_total(s, d)` is the sum of direct and indirect transition evidence.

Apply confidence damping:

```text
score_navigation_path_damped = 0.5 + confidence(s, d) * (score_navigation_path - 0.5)
```

This smoothly blends toward neutral (0.5) when evidence is thin.

### Ranking hook

```text
score_navigation_path_component =
  max(0.0, min(1.0, 2.0 * (score_navigation_path_damped - 0.5)))
```

```text
score_final += navigation_path.ranking_weight * score_navigation_path_component
```

Default:

- `ranking_weight = 0.0`

## Scope Boundary Versus Existing Signals

FR-047 must stay separate from:

- `FR-025` session co-occurrence
  - FR-025 counts co-presence in sessions (unordered);
  - FR-047 models ordered navigation sequences and directional transitions.

- `FR-024` engagement signal
  - FR-024 measures single-page dwell time;
  - FR-047 measures page-to-page transitions.

- `FR-023` hot decay
  - FR-023 measures traffic volume and recency;
  - FR-047 measures navigation direction and path structure.

- `FR-016` / `FR-017` GA4/GSC content value
  - FR-016/017 aggregate pageviews and search metrics;
  - FR-047 uses the raw event stream to extract transition sequences, not aggregate counts.

Hard rule:

- FR-047 must not mutate GA4 import data, session records, or other feature caches.

## Inputs Required

FR-047 v1 can use:

- GA4 `page_view` events with `ga_session_id` and `event_timestamp` (already imported by FR-016)
- `ContentItem` page URLs for mapping events to content items
- existing `ExistingLink` graph for determining whether a direct link already exists (optional enrichment for shortcut detection)

Explicitly disallowed in v1:

- real-time event streaming;
- per-user personalization or user-level profiles;
- external clickstream providers;
- higher-order Markov models (second-order or above) — keep to first-order in v1.

## Data Model Plan

Add to `ContentItem`:

- `navigation_transition_data` — JSON field caching the top-K outbound transition probabilities for this page (avoids recomputing from raw events on every pipeline run)

Add to `Suggestion`:

- `score_navigation_path`
- `navigation_path_diagnostics`

Add new model:

- `NavigationTransition` — stores aggregated transition counts between page pairs: `source_content_item`, `dest_content_item`, `direct_count`, `indirect_count`, `transition_probability`, `shortcut_value`, `last_computed`

## Settings And Feature-Flag Plan

Recommended keys:

- `navigation_path.enabled`
- `navigation_path.ranking_weight`
- `navigation_path.lookback_days`
- `navigation_path.min_sessions`
- `navigation_path.min_transition_count`
- `navigation_path.w_direct`
- `navigation_path.w_shortcut`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `lookback_days = 90`
- `min_sessions = 50`
- `min_transition_count = 5`
- `w_direct = 0.6`
- `w_shortcut = 0.4`

## Diagnostics And Explainability Plan

Diagnostics should include:

- `source_sessions_count`
- `direct_transition_count`
- `direct_probability`
- `top_indirect_paths` (cap 3, each showing intermediate page and hop probabilities)
- `shortcut_value`
- `raw_nav_score`
- `confidence`
- `fallback_state`

Plain-English helper text:

- "Navigation path prediction boosts destinations that users are already navigating toward, including pages they reach through multi-hop detours."

## Native Performance Plan

This is a later ranking-affecting FR, so it must plan a native fast path.

### C++ default path

Add a native Markov transition matrix builder and scorer that processes session sequences and computes transition probabilities in batch.

Suggested file:

- `backend/extensions/navpath.cpp`

### Python fallback

Add:

- `backend/apps/pipeline/services/navigation_path.py`

The Python and C++ paths must produce the same bounded scores for the same session data.

### Visibility requirement

Expose:

- native enabled / fallback enabled;
- why fallback is active;
- whether native batch computation is materially faster.

## Backend Touch Points

- `backend/apps/content/models.py`
- `backend/apps/suggestions/models.py`
- `backend/apps/core/views.py`
- `backend/apps/pipeline/services/navigation_path.py`
- `backend/apps/pipeline/services/ranker.py`
- `backend/apps/pipeline/tasks.py`
- `backend/extensions/navpath.cpp`

## Verification Plan

Later implementation must verify at least:

1. pages with high direct transition probability from the source outrank pages with no transition evidence;
2. shortcut detection correctly identifies indirect paths (A → X → C) and boosts C for source A;
3. pages below `min_sessions` or `min_transition_count` receive the neutral 0.5 fallback;
4. `ranking_weight = 0.0` leaves ranking unchanged;
5. confidence damping smoothly blends toward neutral for low-evidence pairs;
6. C++ and Python paths produce identical scores;
7. diagnostics explain why a destination scored high, low, or neutral.
