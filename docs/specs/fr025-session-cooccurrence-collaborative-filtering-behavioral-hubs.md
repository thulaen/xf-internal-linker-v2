# FR-025 - Session Co-Occurrence Collaborative Filtering & Behavioral Hub Clustering

## Confirmation

- `FR-025` is a real backlog item in `FEATURE-REQUESTS.md`.
- It is queued for `Phase 28`.
- This spec is written before implementation because the user explicitly requested the build blueprint in advance.
- Repo confirmed:
  - FR-016 establishes GA4 credentials and the analytics sync infrastructure — this FR reuses those credentials for a new, independent session-level data fetch;
  - `SearchMetric` stores page-level daily GA4 data but does NOT store session-level reading sequences;
  - FR-021 builds an article-entity graph based on text co-occurrence — this FR builds a separate `SessionCoOccurrencePair` graph based on user reading behaviour;
  - FR-014 clusters near-duplicate content by embedding distance — this FR introduces a separate `BehavioralHub` model for behaviour-driven article grouping;
  - no session-level co-occurrence data, co-occurrence matrix, item-to-item association scores, or behavioural hub clustering exists anywhere in the codebase today.

## Scope Statement

This FR has three parts. Each part has a hard boundary.

| Part | What it does | Where it lives | What it must NOT do |
|---|---|---|---|
| 1. Session co-occurrence pipeline | Fetches GA4 session-level page-view sequences and builds a pairwise co-occurrence matrix | New `backend/apps/cooccurrence/` app | Must not modify FR-016 telemetry pipeline or `SearchMetric` |
| 2. Co-occurrence signal | Adds a seventh signal slot (`co_occurrence_signal`) to the FR-021 value model | FR-021 value model service only | Must not touch `score_final`, must not merge with FR-016 telemetry |
| 3. Behavioral hub clustering | Detects hub clusters from co-occurrence data and allows hard-linking hub members | New `BehavioralHub` model and hub review UI | Must not merge with or replace FR-014 `ContentCluster` |

**Ideas merged into this FR:**
- Amazon Item-to-Item Collaborative Filtering → Part 2 (pairwise co-occurrence as a value model signal).
- Spotify Discover Weekly Co-Occurrence → Part 3 (behavioral hub detection and hard-linking).
- Both require the same underlying data pipeline (Part 1). Building them separately would duplicate that pipeline.

## Current Repo Map

### Analytics and sync infrastructure (reused by Part 1)

- `backend/apps/analytics/models.py`
  - `SearchMetric` — page-level daily aggregates; does NOT store session paths.
- GA4 credentials stored in `AppSetting` (added by FR-016).
- GA4 Data API client (added by FR-016 analytics sync service).

### FR-021 value model (modified by Part 2)

- `backend/apps/knowledge_graph/services.py`
  - current formula has six signals after FR-024: `relevance`, `traffic`, `freshness`, `authority`, `engagement`, `penalty`.
  - this FR adds a seventh: `co_occurrence_signal`.
  - `co_occurrence_signal` is a PAIRWISE signal (specific to a source-destination pair), unlike `traffic`, `freshness`, and `authority` which are destination-only signals.
  - FR-021 already has one pairwise signal precedent: `relevance_signal` (embedding cosine similarity between source and destination).

### FR-014 near-duplicate clustering (NOT modified — complementary)

- `backend/apps/content/models.py`
  - `ContentCluster` — groups near-duplicate content by embedding distance (> 0.96 similarity).
  - `ContentItem.cluster`, `ContentItem.is_canonical`.
- FR-014 clusters are about deduplication. `BehavioralHub` (added here) is about co-navigation. They can coexist on the same `ContentItem`.

### Gaps

- No session-level GA4 data fetch.
- No co-occurrence matrix storage.
- No `BehavioralHub` model.
- No co-occurrence signal in the value model.

## Workflow Drift / Doc Mismatch Found During Inspection

- FR-016 spec collects `suggestion_link_click` and `suggestion_destination_view` events — these are suggestion-driven clicks only, not general browsing paths. This FR fetches all page-view sequences from GA4 sessions, which is a different and wider dataset.
- FR-021 value model formula in the spec lists five signals; FR-024 adds a sixth. This FR adds a seventh. All are additive. The formula is designed to be extended.
- FR-014 spec explicitly limits clustering to near-duplicates (similarity > 0.96). `BehavioralHub` has no similarity threshold — it is driven purely by co-navigation frequency. No mismatch.

## Source Summary

### Amazon: Item-to-Item Collaborative Filtering (US Patent 6,266,649)

Amazon's approach: instead of matching users to users (expensive), match items to items based on purchase co-occurrence. If 80% of people who buy A also buy B, link A to B directly.

Adapted for internal linking: if users who read Article A frequently also read Article B in the same session, A and B are co-occurrence neighbors. Link strength = `co_occurrence_count / max(sessions_containing_A, sessions_containing_B)`.

### Spotify: Discover Weekly Playlist Co-Occurrence

Spotify's approach: two songs that appear together in many user-created playlists are considered related, even if they are different genres.

Adapted for internal linking: treat each user session as a "playlist." Articles that appear together in many sessions form a behavioral cluster — a hub. Hub members should be hard-linked to each other, bypassing normal suggestion flow for the hub's strongest pairs.

### Key insight from merging both

Both approaches need the same co-occurrence matrix. Amazon uses it to score pairwise link strength (Part 2). Spotify uses it to detect community structure — groups of articles frequently consumed together (Part 3). One data pipeline, two complementary outputs.

### What was clear

- GA4's Data API supports session-level queries with `sessionId` and `pagePath` dimensions.
- The resulting data is sparse — a typical site will have at most thousands of meaningful pairs, not millions.
- Storage footprint is small: a co-occurrence table with 50,000 pairs takes under 10 MB.
- The co-occurrence signal is a pairwise signal. It belongs in the FR-021 value model pre-ranking pass alongside `relevance_signal`, not in `score_final`.
- Behavioral hubs must be kept separate from FR-014 near-duplicate clusters. They serve different purposes: deduplication vs co-navigation grouping.

### What remained ambiguous

- Whether GA4 session data should be fetched via the Data API directly or via a BigQuery export when available. Spec uses the Data API for first pass; BigQuery is noted as a future upgrade.
- Whether hub detection should use a community-detection algorithm (Louvain, connected components) or a simpler threshold-based approach. Spec uses threshold-based connected components for the first pass.
- Minimum session threshold to form a valid co-occurrence pair (default: 5 co-sessions).

## Problem Definition

Simple version first.

Right now the linker finds related articles by asking: "does this article contain similar words or entities?" It does not ask: "do real users naturally navigate from this article to that one?"

Two articles about completely different topics might be read together constantly by your actual audience. The linker would never suggest that link because the text signals say "not related." But your readers clearly think they are.

The fix is to watch the paths real users take through the site and use those paths as a link signal. If readers who visit Article A also visit Article B in the same sitting — often, consistently, across many sessions — that is a strong signal that a direct link belongs there.

This FR adds:

1. A data pipeline that fetches those session paths from GA4 and builds a co-occurrence count for every article pair.
2. A co-occurrence score that feeds into the FR-021 value model pre-ranking pass — boosting candidates that real users have already shown they navigate to.
3. A behavioral hub detector that finds groups of articles frequently consumed together and lets operators hard-link them as a content hub.

---

## Part 1 — Session Co-Occurrence Data Pipeline

### New backend app

Add: `backend/apps/cooccurrence/`

Files:

- `backend/apps/cooccurrence/models.py`
- `backend/apps/cooccurrence/services.py`
- `backend/apps/cooccurrence/tasks.py`
- `backend/apps/cooccurrence/views.py`
- `backend/apps/cooccurrence/serializers.py`

### Data models

#### `SessionCoOccurrencePair`

Stores the co-occurrence count for every article pair observed in GA4 session data.

Fields:

- `source_content_item` (ForeignKey → ContentItem, indexed)
- `dest_content_item` (ForeignKey → ContentItem, indexed)
- `co_session_count` (IntegerField)
  - number of sessions in which both articles were viewed.
- `source_session_count` (IntegerField)
  - number of sessions in which the source article was viewed (denominator for Jaccard).
- `dest_session_count` (IntegerField)
  - number of sessions in which the destination article was viewed.
- `jaccard_similarity` (FloatField)
  - `co_session_count / (source_session_count + dest_session_count - co_session_count)`
  - bounded [0, 1].
- `lift` (FloatField)
  - `P(A ∩ B) / (P(A) × P(B))`
  - values > 1.0 mean articles are co-read more than chance predicts.
- `last_computed_at` (DateTimeField)
- `data_window_start` (DateField)
- `data_window_end` (DateField)
- `created_at`, `updated_at`

Unique constraint: `(source_content_item, dest_content_item)`.

Note: pairs are stored directionally. A→B and B→A are separate rows, which allows asymmetric co-occurrence patterns (users often go from A to B but rarely from B to A).

#### `SessionCoOccurrenceRun`

Stores metadata about each co-occurrence computation run.

Fields:

- `run_id` (UUID)
- `status` (CharField: `running`, `completed`, `failed`)
- `data_window_start` (DateField)
- `data_window_end` (DateField)
- `sessions_processed` (IntegerField)
- `pairs_written` (IntegerField)
- `ga4_rows_fetched` (IntegerField)
- `started_at`, `completed_at`
- `error_message` (TextField, blank)

### GA4 session-level data fetch

The GA4 Data API supports session-level page-view reports.

Query dimensions:
- `sessionId` — unique session identifier.
- `pagePath` — the URL path of each viewed page.
- `date` — to support windowed fetches.

Query metrics:
- `sessions` — session count per path (used for marginal counts).

Fetch strategy:

1. For each date in the configured window, fetch `(sessionId, pagePath)` pairs.
2. For each session, collect all page paths viewed.
3. Resolve each path to a `ContentItem` by URL matching.
4. Emit all unique pairs `(A, B)` where A ≠ B and both are known `ContentItem` rows.
5. Aggregate into `co_session_count`, `source_session_count`, `dest_session_count`.
6. Compute `jaccard_similarity` and `lift`.
7. Upsert `SessionCoOccurrencePair` rows.

Privacy note:
- Session IDs are used only for co-occurrence grouping and discarded after aggregation.
- No individual user ID, IP address, or personal data is stored.
- Only content item pairs and aggregate counts are persisted.

### Celery task

- `compute_session_cooccurrence` Celery task:
  - fetches GA4 session data for the configured window;
  - builds and upserts `SessionCoOccurrencePair` rows;
  - prunes pairs below the minimum co-session threshold;
  - writes a `SessionCoOccurrenceRun` record;
  - emits an FR-019 alert if the run fails.
  - Default schedule: weekly (co-occurrence data changes slowly).
  - Can also be triggered on-demand.

### Minimum thresholds

- `min_co_session_count` (default: 5) — pairs with fewer than 5 co-sessions are discarded as noise.
- `min_jaccard` (default: 0.05) — pairs below this Jaccard score are discarded.
- `data_window_days` (default: 90) — how far back to look in GA4 session data.

---

## Part 2 — Co-Occurrence Signal in FR-021 Value Model

### Scope

This part adds one new signal slot to the FR-021 value model: `co_occurrence_signal`.

It is a pairwise signal. It is non-zero only for source-destination pairs that have a recorded `SessionCoOccurrencePair` row.

For pairs with no co-occurrence data, it returns the neutral fallback (default: `0.5`).

### Signal computation

```python
def compute_co_occurrence_signal(
    source_content_item: ContentItem,
    dest_content_item: ContentItem,
    min_co_sessions: int = 5,
    fallback: float = 0.5,
    site_max_jaccard: float,  # pre-computed max Jaccard across all pairs for normalization
) -> float:
    """
    Returns a [0, 1] bounded co-occurrence signal for the source → dest pair.

    Uses the stored SessionCoOccurrencePair.jaccard_similarity for normalization.
    Pairs with co_session_count < min_co_sessions are treated as missing (fallback).
    Pairs with no SessionCoOccurrencePair row return fallback.
    """
```

Why Jaccard for the signal (not raw co_session_count):

- Raw co-session counts are biased toward high-traffic pages. A popular page will co-occur with everything simply because it appears in many sessions.
- Jaccard similarity controls for marginal popularity: it measures how *exclusively* two articles are read together relative to how often each is read alone.
- A niche pair with 10 co-sessions out of 12 total sessions each (Jaccard = 0.83) is a stronger signal than a popular pair with 50 co-sessions out of 5,000 total sessions (Jaccard = 0.01).

### Updated value model formula

```
value_score = (
    w_relevance      × relevance_signal
  + w_traffic        × traffic_signal
  + w_freshness      × freshness_signal
  + w_authority      × authority_signal
  + w_engagement     × engagement_signal       (added by FR-024)
  + w_cooccurrence   × co_occurrence_signal    ← new
  - w_penalty        × penalty_signal
)
```

Default weight: `w_cooccurrence = 0.15`

### Why 0.15 default weight

Co-occurrence is a direct behavioural signal — it reflects actual reader intent. It deserves a somewhat higher default weight than the structural signals (`freshness` at 0.1, `authority` at 0.1, `engagement` at 0.1) but should not dominate over relevance (0.4). A default of 0.15 gives it meaningful influence while keeping relevance primary.

### Lift as a diagnostic (not used in scoring)

`lift` is stored on `SessionCoOccurrencePair` but is not used in the signal computation. It is displayed in diagnostics only. It helps operators understand whether the co-occurrence is meaningful: a lift of 1.0 means random chance, a lift of 5.0 means these articles are five times more likely to be co-read than chance predicts.

### New settings fields

Add to `GET/PUT /api/settings/value-model/`:

- `co_occurrence_signal_enabled` (bool, default: `true`)
- `w_cooccurrence` (float, default: `0.15`)
- `co_occurrence_fallback_value` (float, default: `0.5`)
- `co_occurrence_min_co_sessions` (int, default: `5`)

### New diagnostics fields

Extend `value_model_diagnostics` on `Suggestion`:

```json
{
  "co_occurrence_signal": 0.72,
  "co_session_count": 34,
  "jaccard_similarity": 0.18,
  "lift": 4.2,
  "co_occurrence_fallback_used": false
}
```

---

## Part 3 — Behavioral Hub Clustering

### What a behavioral hub is

A behavioral hub is a group of articles that real users frequently navigate between in the same session.

Example: if users consistently read articles X, Y, and Z together — regardless of what the text says — those three articles form a behavioral hub. Once detected, the operator can hard-link all hub members to each other with a "Readers also explore:" block.

This is different from FR-014 near-duplicate clustering:

| | FR-014 `ContentCluster` | FR-025 `BehavioralHub` |
|---|---|---|
| Signal | Embedding distance (text similarity) | Session co-occurrence (reader behaviour) |
| Purpose | Deduplication — suppress redundant candidates | Navigation grouping — surface co-read articles |
| Effect on ranking | Suppresses non-canonical cluster members | No suppression — promotes hub links |
| Manual override | Yes | Yes |

A content item can belong to both a `ContentCluster` (near-duplicate) and a `BehavioralHub` (co-navigation group). They coexist.

### New models

#### `BehavioralHub`

- `hub_id` (UUID)
- `name` (CharField — auto-generated or operator-named)
- `detection_method` (CharField: `threshold_connected_components`, `manual`)
- `min_jaccard_used` (FloatField — threshold at detection time)
- `member_count` (IntegerField)
- `auto_link_enabled` (BooleanField, default: `false`)
  - When true, hub members are hard-linked to each other at the bottom of each article.
- `created_at`, `updated_at`

#### `BehavioralHubMembership`

- `hub` (ForeignKey → BehavioralHub)
- `content_item` (ForeignKey → ContentItem)
- `membership_source` (CharField: `auto_detected`, `manual_add`, `manual_remove_override`)
- `co_occurrence_strength` (FloatField — average Jaccard to other hub members)
- `created_at`

### Hub detection algorithm

Simple version first. Use threshold-based connected components.

1. Build an undirected graph where:
   - nodes = `ContentItem` rows.
   - edges = `SessionCoOccurrencePair` rows with `jaccard_similarity ≥ hub_min_jaccard` (default: `0.15`).
2. Find all connected components in this graph.
3. Discard components smaller than `hub_min_members` (default: 3).
4. Each qualifying component becomes a `BehavioralHub`.
5. Assign `BehavioralHubMembership` rows for all members.

This is intentionally simple. It requires no external graph library — just adjacency list traversal (BFS/DFS).

### Hub detection task

- `detect_behavioral_hubs` Celery task:
  - runs after `compute_session_cooccurrence` completes;
  - detects hubs using connected components;
  - upserts `BehavioralHub` and `BehavioralHubMembership` rows;
  - preserves manual overrides (`manual_remove_override` memberships are not overwritten);
  - logs hub count, member count, and changes since last run.

### Auto-linking

When `BehavioralHub.auto_link_enabled = true`, the app can inject a "Readers also explore:" block at the bottom of each hub member article.

**First pass implementation:**

This is surfaced as Suggestion rows with a special `candidate_origin = "behavioral_hub"` flag, not as a separate link injection mechanism. The existing suggestion review flow handles them.

Specifically: when a destination is a hub member of the source article's hub, and `auto_link_enabled` is true, that destination gets a strong `co_occurrence_signal` boost in the value model (already handled by Part 2) AND is flagged as a hub suggestion in diagnostics.

True automatic link injection (writing to the XenForo/WP content directly) is out of scope for this first pass.

### Hub management UI

Add a new page: `/behavioral-hubs`

Sections:

- **Hub list** — all detected hubs, sortable by member count and co-occurrence strength.
- **Hub detail** — member list with Jaccard scores and lift values.
- **Edit hub** — rename hub, manually add/remove members, toggle `auto_link_enabled`.
- **Merge hubs** — combine two manually when they overlap.

Hub detection settings panel (add to the settings page):

- Toggle: **Enable behavioral hub detection**.
- Number field: **Minimum Jaccard for hub edge** (default: 0.15).
- Number field: **Minimum members per hub** (default: 3).
- "Rebuild Hubs Now" button.
- Stats: hub count, total members, last detection run.

---

## REST API

### Co-occurrence data endpoints

- `GET /api/cooccurrence/pairs/` — list `SessionCoOccurrencePair` rows with filters: `source`, `min_jaccard`, `min_co_sessions`.
- `GET /api/cooccurrence/pairs/<source_id>/` — all pairs for a given source content item.
- `GET /api/cooccurrence/runs/` — list `SessionCoOccurrenceRun` records.
- `POST /api/cooccurrence/compute/` — trigger a manual co-occurrence computation run.

### Behavioral hub endpoints

- `GET /api/behavioral-hubs/` — list all hubs.
- `GET /api/behavioral-hubs/<hub_id>/` — hub detail with members.
- `PATCH /api/behavioral-hubs/<hub_id>/` — update hub name, `auto_link_enabled`.
- `POST /api/behavioral-hubs/<hub_id>/members/` — manually add a content item to a hub.
- `DELETE /api/behavioral-hubs/<hub_id>/members/<content_item_id>/` — manually remove.
- `POST /api/behavioral-hubs/detect/` — trigger hub detection.

### Settings endpoints

Extend `GET/PUT /api/settings/value-model/` for Part 2 settings (listed above).

Add `GET/PUT /api/settings/cooccurrence/`:

- `cooccurrence_enabled` (bool, default: `true`)
- `data_window_days` (int, default: `90`)
- `min_co_session_count` (int, default: `5`)
- `min_jaccard` (float, default: `0.05`)
- `hub_min_jaccard` (float, default: `0.15`)
- `hub_min_members` (int, default: `3`)
- `hub_detection_enabled` (bool, default: `true`)
- `schedule_weekly` (bool, default: `true`)
- `last_run_at` (datetime, read-only)
- `last_run_pairs_written` (int, read-only)
- `last_run_hubs_detected` (int, read-only)

---

## Alert Integration (FR-019)

Add two new event types to the FR-019 alert registry:

- `cooccurrence.run_failed` — co-occurrence computation task failed.
- `cooccurrence.run_completed` — run completed (info severity; includes pairs written count).

Emit via `emit_operator_alert()`. Use dedupe keys per run ID.

---

## Pipeline Integration

### Where co-occurrence fits

```
[Session Co-Occurrence Pipeline] (weekly, independent)
        ↓
[SessionCoOccurrencePair table updated]
        ↓
[FR-021 Value Model pre-ranking]
  ← co_occurrence_signal read per source-destination pair
        ↓
[Multi-signal scoring (FR-006 → FR-015)]
        ↓
[Diversity reranking (FR-015)]
        ↓
[Suggestions stored]
          ↑
[Behavioral Hub detection] (runs after co-occurrence pipeline)
  ← hub membership used to flag suggestions with candidate_origin = "behavioral_hub"
```

The co-occurrence pipeline is independent of the main suggestion pipeline. It runs weekly. The main pipeline reads the pre-computed `SessionCoOccurrencePair` rows at suggestion time — no live GA4 calls during pipeline runs.

---

## Dependencies

| This FR requires | Why |
|---|---|
| FR-016 (GA4 telemetry) | Reuses GA4 credentials and Data API client setup |
| FR-021 (Graph value model) | Part 2 adds a seventh signal to the FR-021 value model |
| FR-019 (Operator alerts) | Alert wiring for pipeline run events |

FR-024 (Read-Through Rate) is recommended before this FR because it defines the sixth signal slot. If FR-024 is not yet implemented, Part 2 adds the seventh slot assuming the sixth (`w_engagement`) is already defined. Adjust formula order if FR-024 is delayed.

---

## Test Plan

### Part 1 — Co-occurrence pipeline

- GA4 session fetch returns expected `(sessionId, pagePath)` pairs for test data.
- URL-to-ContentItem resolution handles trailing slashes, query strings, and unknown URLs.
- Pairs below `min_co_session_count` are discarded.
- `jaccard_similarity` is computed correctly: `co / (a + b - co)`.
- `lift` is computed correctly: `P(A∩B) / (P(A) × P(B))`.
- Upsert overwrites existing pair rows without duplicating.
- `SessionCoOccurrenceRun` record is written on completion and failure.
- Session IDs are not stored after aggregation.

### Part 2 — Co-occurrence signal

- Source-destination pair with known Jaccard produces expected normalized signal.
- Pair with `co_session_count < min_co_sessions` returns fallback.
- Pair with no `SessionCoOccurrencePair` row returns fallback.
- `co_occurrence_signal_enabled = false` returns fallback for all pairs.
- `value_model_diagnostics` contains all new co-occurrence fields.
- Existing six signal computations produce identical output before and after this FR.

### Part 3 — Behavioral hubs

- Connected components algorithm finds correct clusters for test adjacency data.
- Components smaller than `hub_min_members` are discarded.
- Hub detection preserves `manual_remove_override` memberships.
- `auto_link_enabled = true` flags hub-pair suggestions as `candidate_origin = "behavioral_hub"`.
- Hub management UI renders hub list, member detail, and edit actions.
- Manual add/remove persists and survives re-detection.

### Manual verification

- Run co-occurrence pipeline against a real GA4 property.
- Verify `SessionCoOccurrencePair` rows are populated.
- Run suggestion pipeline and verify some suggestions have `co_occurrence_signal > 0.5`.
- Run hub detection and verify at least one hub is created on real data.
- Confirm FR-014 `ContentCluster` assignments are unaffected.

---

## Acceptance Criteria

**Part 1:**
- Session co-occurrence pipeline fetches GA4 session data and builds `SessionCoOccurrencePair` rows.
- No personal data is stored.
- Pairs below noise thresholds are discarded.
- Runs are logged and failures fire FR-019 alerts.

**Part 2:**
- `co_occurrence_signal` is the seventh slot in the FR-021 value model.
- It uses Jaccard similarity from `SessionCoOccurrencePair`. It does not call GA4 at pipeline time.
- Missing pairs fall back cleanly to 0.5.
- Diagnostics show co-session count, Jaccard, and lift per suggestion.

**Part 3:**
- `BehavioralHub` and `BehavioralHubMembership` are detected and stored from co-occurrence data.
- Hubs are separate from FR-014 `ContentCluster` — a content item can belong to both.
- Operators can view, rename, edit, and merge hubs.
- `auto_link_enabled` flags hub suggestions with `candidate_origin = "behavioral_hub"`.
- Hub detection settings are configurable.

---

## Out-of-Scope Follow-Up

- True automatic link injection into XenForo/WP content without review.
- Community detection algorithms (Louvain, modularity optimisation) for more sophisticated hub grouping.
- Cross-device session stitching.
- BigQuery export as an alternative to the Data API for large properties.
- Per-session recency weighting (sessions from last 7 days count more than sessions from 90 days ago).
- Negative co-occurrence detection (articles users actively avoid visiting together).
