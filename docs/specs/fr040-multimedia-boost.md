# FR-040 - Multimedia Boost — Content Richness Signal

## Confirmation

- `FR-040` is a real backlog item in `FEATURE-REQUESTS.md`.
- It is queued for `Phase 43`.
- This spec is written before implementation because the user explicitly requested the build blueprint in advance.
- Repo confirmed:
  - FR-021 defines the value model that this FR extends;
  - FR-024 added the sixth signal slot (`engagement_signal`);
  - FR-025 added the seventh signal slot (`co_occurrence_signal`);
  - no multimedia richness signal exists anywhere in the scoring pipeline today;
  - `ContentItem.distilled_text` already stores cleaned body text (used for word-count estimation);
  - no `multimedia_metadata` field exists on `ContentItem` yet — this FR introduces it;
  - the XenForo sync (`backend/apps/xenforo/`) and WordPress sync (`backend/apps/wordpress/`) are the two places where raw HTML content is available at ingest time.

## Scope Statement

This FR adds exactly two things:

1. A `multimedia_metadata` JSON field on `ContentItem`, populated during content sync.
2. An eighth signal slot called `multimedia_signal` in the FR-021 value model.

| What changes | Where |
|---|---|
| New `multimedia_metadata` JSONField | `ContentItem` model + both sync services |
| New Django migration | `backend/apps/content/migrations/` |
| New `multimedia_signal` computation | FR-021 value model service only |
| New fields in `value_model_diagnostics` | `Suggestion` JSON field only |
| New settings fields | `GET/PUT /api/settings/value-model/` only |
| New settings card controls | FR-021 settings card only |

**Hard boundaries — nothing else is touched:**

- `score_final` in the main ranker is not modified.
- FR-024 `engagement_signal` is not modified or reweighted.
- FR-025 `co_occurrence_signal` is not modified.
- The existing seven value model signals are not modified by default.
- HTML is never fetched or parsed at pipeline time. Parsing happens at sync time only.
- The sync services are modified only to extract and store multimedia metadata — no sync logic or scheduling is changed.

## Source Summary

### Research basis

Search engine and recommendation system research consistently identifies video and image richness as a quality signal. The key findings, with sources, are:

**Video**
- Pages with video keep users **2.6× longer** than pages without (Wistia, 2021–2022 dataset, 100 highest-traffic pages).
- Pages combining text + images + video + schema achieve **317% higher selection rates** in Google AI Overviews (industry data, 2024–2025).
- Google's VideoObject structured data unlocks video rich snippets in SERPs, which Google's own documentation confirms improves click-through and indexation speed.
- Google patent `US8189685B1` (*Ranking Video Articles*) explicitly encodes video engagement (broadcast source, watch time, user ratings, replay rate, quality) as ranking factors — confirming video quality is a first-class signal in Google's own systems.

**Images**
- Google's Image SEO documentation confirms alt text is a ranking signal: "Google uses alt text along with computer vision algorithms and the contents of the page to understand the subject matter." The first 16 words of alt text are factored into page ranking.
- Google's Helpful Content guidance cites original photographs (not stock images) as "corroborating evidence of first-hand experience" under E-E-A-T — a direct quality signal.
- The Bing RankMM model (official Bing Search Quality Insights blog, October 2021) uses a deep multimodal ranking model that takes query + image + webpage context jointly.
- Images without explicit `width` and `height` attributes cause Cumulative Layout Shift (CLS), which is a confirmed Google Core Web Vitals penalty — making CLS hygiene a measurable proxy for image implementation quality.

**Decorative images are explicitly not rewarded**
- Google has stated there is no magic image count. Raw image count does not boost ranking.
- Stock photo CDN images (Getty, Shutterstock, Unsplash, Pexels) appear on thousands of sites and provide no uniqueness signal.
- The signal rewards *quality and implementation quality*, not quantity.

### Key insight adapted for internal linking

A destination page that is visually rich — video explaining the topic, images illustrating key points, properly described with alt text — is more valuable to a reader than a wall of plain text covering the same topic. Multimedia richness is a proxy for content investment and a predictor of lower bounce and higher dwell time, complementing the behavioural evidence already captured by `engagement_signal` (FR-024).

## Data Model Change

### New field on `ContentItem`

```python
# backend/apps/content/models.py

multimedia_metadata = models.JSONField(
    null=True,
    blank=True,
    default=None,
    help_text=(
        "Multimedia richness metadata extracted from raw HTML at sync time. "
        "Set by the XenForo and WordPress sync services. "
        "Null until the content item has been synced at least once after FR-040 is deployed."
    ),
)
```

### Shape of `multimedia_metadata`

```json
{
  "image_count": 3,
  "images_with_descriptive_alt": 2,
  "images_decorative": 1,
  "images_from_stock_cdn": 0,
  "has_video": true,
  "video_provider": "youtube",
  "has_video_schema": false,
  "word_count_at_extraction": 1420,
  "extracted_at": "2026-04-04T12:00:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `image_count` | int | Total `<img>` tags with `width` or `height` ≥ 100px (excludes tracking pixels) |
| `images_with_descriptive_alt` | int | `<img>` tags where `alt` is non-empty and not in the decorative-image set |
| `images_decorative` | int | `<img>` tags where `alt=""` (intentional blank — W3C decorative pattern) |
| `images_from_stock_cdn` | int | Images whose `src` domain matches a known stock CDN list (see below) |
| `has_video` | bool | True when a `<video>` tag or known video iframe is present |
| `video_provider` | str \| null | `"youtube"`, `"vimeo"`, `"native"`, `"other"`, or `null` |
| `has_video_schema` | bool | True when a `VideoObject` JSON-LD block is found in the page |
| `word_count_at_extraction` | int | Word count of `distilled_text` snapshot at extraction time |
| `extracted_at` | ISO 8601 str | UTC timestamp of the extraction run |

### Stock CDN detection list (hardcoded constant, not user-configurable)

```python
STOCK_CDN_HOSTNAMES = frozenset({
    "images.unsplash.com",
    "media.istockphoto.com",
    "gettyimages.com",
    "shutterstock.com",
    "stock.adobe.com",
    "dreamstime.com",
    "depositphotos.com",
    "alamy.com",
    "pexels.com",
    "pixabay.com",
})
```

### Where extraction runs

Add a `extract_multimedia_metadata(html: str, distilled_word_count: int) -> dict` helper in a new file:

```
backend/apps/content/multimedia_extractor.py
```

Call it from both sync services after HTML cleaning, before saving:

```python
# In XenForo sync and WordPress sync save path:
item.multimedia_metadata = extract_multimedia_metadata(
    raw_html,
    len(item.distilled_text.split()),
)
```

The extractor must use `html.parser` (stdlib `html.parser` or `BeautifulSoup` with `html.parser` backend — whichever is already a project dependency). Never import `lxml` unless it is already in `requirements.txt`.

## Multimedia Signal Formula

### Component 1 — Video component (weight 0.40)

Video is the strongest single multimedia quality signal per the research above.

```python
def compute_video_component(
    has_video: bool,
    video_provider: str | None,
    has_video_schema: bool,
) -> float:
    """
    Returns a score in [0, 1].

    0.0 — no video
    0.6 — video present (unknown or 'other' provider, no schema)
    0.75 — YouTube or Vimeo or native <video> (no schema)
    0.85 — YouTube or Vimeo + VideoObject schema
    1.0 — full package: YouTube/Vimeo + VideoObject schema (best case)

    Rationale: YouTube embeds generate Google video rich snippets more
    reliably than other providers. Schema adds indexation speed.
    """
    if not has_video:
        return 0.0

    base = 0.6
    if video_provider in {"youtube", "vimeo", "native"}:
        base = 0.75
    if has_video_schema and video_provider in {"youtube", "vimeo", "native"}:
        base = 1.0
    elif has_video_schema:
        base = min(base + 0.10, 1.0)

    return base
```

### Component 2 — Alt text coverage (weight 0.25)

Alt text is a confirmed Google ranking signal and an accessibility requirement.

```python
def compute_alt_coverage_component(
    image_count: int,
    images_with_descriptive_alt: int,
    images_decorative: int,
) -> float:
    """
    Returns a score in [0, 1].

    Decorative images (alt="") are excluded from both numerator and
    denominator — they are correctly implemented per W3C and should
    not penalise the page.

    No images → 0.5 neutral (no penalty for text-only pages).
    """
    scoreable_images = image_count - images_decorative
    if scoreable_images <= 0:
        return 0.5  # neutral: text-only page or all images are decorative

    coverage = images_with_descriptive_alt / scoreable_images

    if coverage >= 0.80:
        return 1.0
    elif coverage >= 0.50:
        return 0.5
    else:
        return 0.0
```

### Component 3 — Image presence (weight 0.20)

Baseline signal: does the page have any meaningful images at all?

```python
def compute_image_presence_component(
    image_count: int,
    images_from_stock_cdn: int,
) -> float:
    """
    Returns a score in [0, 1].

    Penalises pages where all images are stock CDN images (low originality).
    Rewards pages with original or mixed imagery.
    """
    if image_count == 0:
        return 0.0

    original_images = image_count - images_from_stock_cdn

    if original_images >= 3:
        return 1.0
    elif original_images >= 1:
        return 0.7
    elif image_count >= 3:
        # Has images but all stock — low but not zero
        return 0.3
    else:
        return 0.2
```

### Component 4 — Image-to-word ratio (weight 0.15)

Guards against sparse content padded with images, and against walls of text with no visuals.

```python
def compute_image_word_ratio_component(
    image_count: int,
    word_count: int,
) -> float:
    """
    Returns a score in [0, 1].

    Optimal: one image per 200–600 words.
    Too many images for the word count = lower score (padded content).
    Too few images for a long article = lower score.
    No images or zero words = 0.5 neutral.

    words_per_image thresholds:
        200–600   → 1.0  (optimal)
        100–199   → 0.6  (over-imaged)
        601–1000  → 0.7  (could use more visuals)
        > 1000    → 0.3  (long form, visually sparse)
    """
    if image_count == 0 or word_count <= 0:
        return 0.5  # neutral: no data to judge

    words_per_image = word_count / image_count

    if 200 <= words_per_image <= 600:
        return 1.0
    elif 100 <= words_per_image < 200:
        return 0.6
    elif 600 < words_per_image <= 1000:
        return 0.7
    else:
        return 0.3
```

### Complete `multimedia_signal` function

```python
def compute_multimedia_signal(
    content_item: ContentItem,
    *,
    fallback: float = 0.5,
) -> tuple[float, dict]:
    """
    Returns (multimedia_signal, diagnostics_dict).

    multimedia_signal is bounded [0, 1].

    Falls back cleanly to `fallback` (default 0.5) when:
    - multimedia_metadata is None (item not yet synced post-FR-040)
    - multimedia_metadata is malformed

    Component weights:
        video        0.40
        alt_coverage 0.25
        image_pres   0.20
        img_wrd_ratio 0.15
    """
    meta = content_item.multimedia_metadata
    if not meta:
        return fallback, {"multimedia_fallback_used": True}

    try:
        video_c = compute_video_component(
            meta["has_video"],
            meta.get("video_provider"),
            meta.get("has_video_schema", False),
        )
        alt_c = compute_alt_coverage_component(
            meta["image_count"],
            meta["images_with_descriptive_alt"],
            meta["images_decorative"],
        )
        pres_c = compute_image_presence_component(
            meta["image_count"],
            meta["images_from_stock_cdn"],
        )
        ratio_c = compute_image_word_ratio_component(
            meta["image_count"],
            meta["word_count_at_extraction"],
        )
    except (KeyError, TypeError, ZeroDivisionError):
        return fallback, {"multimedia_fallback_used": True, "multimedia_parse_error": True}

    signal = (
        0.40 * video_c
        + 0.25 * alt_c
        + 0.20 * pres_c
        + 0.15 * ratio_c
    )
    signal = max(0.0, min(1.0, signal))  # safety clamp

    return signal, {
        "multimedia_signal": signal,
        "video_component": video_c,
        "alt_coverage_component": alt_c,
        "image_presence_component": pres_c,
        "image_word_ratio_component": ratio_c,
        "image_count": meta["image_count"],
        "images_with_descriptive_alt": meta["images_with_descriptive_alt"],
        "images_decorative": meta["images_decorative"],
        "images_from_stock_cdn": meta["images_from_stock_cdn"],
        "has_video": meta["has_video"],
        "video_provider": meta.get("video_provider"),
        "has_video_schema": meta.get("has_video_schema", False),
        "word_count_at_extraction": meta["word_count_at_extraction"],
        "multimedia_fallback_used": False,
    }
```

## Updated Value Model Formula

```
value_score = (
    w_relevance    × relevance_signal
  + w_traffic      × traffic_signal
  + w_freshness    × freshness_signal
  + w_authority    × authority_signal
  + w_engagement   × engagement_signal      (FR-024)
  + w_cooccurrence × co_occurrence_signal   (FR-025)
  + w_multimedia   × multimedia_signal      ← new
  - w_penalty      × penalty_signal
)
```

Default weight: `w_multimedia = 0.10`

The existing seven signals are not reweighted. The multimedia signal is purely additive. The value model's output is normalised before the main ranker sees it, so `score_final` bounds are unaffected.

## Settings API Changes

Extend `GET/PUT /api/settings/value-model/` with:

- `multimedia_signal_enabled` (bool, default: `true`)
  - When `false`, `multimedia_signal` returns the fallback value (0.5) and has no effect on ranking.
- `w_multimedia` (float, default: `0.10`)
  - Weight of the multimedia signal in the value model formula.
- `multimedia_fallback_value` (float, default: `0.5`)
  - Value used for pages where `multimedia_metadata` is null (not yet re-synced after FR-040 deployment).

## Diagnostics Changes

Extend `value_model_diagnostics` JSON on `Suggestion` (already defined by FR-021) with:

```json
{
  "relevance_signal": 0.82,
  "traffic_signal": 0.68,
  "freshness_signal": 0.74,
  "authority_signal": 0.55,
  "engagement_signal": 0.71,
  "co_occurrence_signal": 0.60,
  "multimedia_signal": 0.78,
  "penalty_signal": 0.0,
  "weights": {
    "w_relevance": 0.40,
    "w_traffic": 0.30,
    "w_freshness": 0.10,
    "w_authority": 0.10,
    "w_engagement": 0.10,
    "w_cooccurrence": 0.15,
    "w_multimedia": 0.10,
    "w_penalty": 0.50
  },
  "value_score": 0.741,
  "video_component": 1.0,
  "alt_coverage_component": 1.0,
  "image_presence_component": 0.7,
  "image_word_ratio_component": 1.0,
  "image_count": 4,
  "images_with_descriptive_alt": 3,
  "images_decorative": 1,
  "images_from_stock_cdn": 0,
  "has_video": true,
  "video_provider": "youtube",
  "has_video_schema": true,
  "word_count_at_extraction": 1650,
  "multimedia_fallback_used": false
}
```

## Settings UI

Add to the existing **Graph Candidate Generation & Value Scoring** settings card (FR-021):

Under a new sub-section: **Multimedia Richness Signal**

- Toggle: **Enable multimedia signal** (on/off, default: on).
- Slider: **Multimedia weight** (0.0 – 0.5, default: 0.1).
- Read-only status line: **"N pages have multimedia metadata"** showing how many `ContentItem` rows have a non-null `multimedia_metadata` field. Helps the operator track re-sync progress after first deployment.

## Review UI Changes

On the suggestion review detail panel, extend the value model breakdown to show:

- `Multimedia signal`: score.
- `Video`: Yes/No + provider + schema badge if present.
- `Images`: count, original vs stock split.
- `Alt text coverage`: percentage of non-decorative images with descriptive alt.
- `Image-to-word ratio`: words per image (e.g. "1 image per 412 words").
- "No multimedia data — using neutral fallback" when `multimedia_fallback_used = true`.

## Dependencies

- FR-021 (Graph value model) — this FR modifies FR-021's value model service.
- FR-024 (Engagement signal) — expected to be implemented first (defines Slot 6). If not yet deployed, adjust the formula order.
- FR-025 (Co-occurrence signal) — expected to be implemented first (defines Slot 7). If not yet deployed, adjust the formula order.
- Django migration required for the `multimedia_metadata` field on `ContentItem`.

## Deployment Notes

After deployment, existing `ContentItem` rows will have `multimedia_metadata = null` until a re-sync runs. During this period, all pages return the fallback score (0.5). This is neutral — it does not penalise unsynced pages.

Full coverage is achieved by either:

1. Waiting for scheduled incremental syncs to naturally pass through all content items, or
2. Running a one-off management command that re-extracts metadata from stored HTML for all existing items.

Option 2 is faster but requires the raw HTML to be stored on `ContentItem`. If it is not, Option 1 is the only path. Implement Option 2 only if raw HTML is already persisted.

## Test Plan

### Extractor unit tests (`test_multimedia_extractor.py`)

- HTML with one `<img alt="a kitten">` returns `image_count=1`, `images_with_descriptive_alt=1`, `images_decorative=0`.
- HTML with `<img alt="">` returns `images_decorative=1`, `image_count=0` (excluded from scoreable count).
- HTML with `<img src="https://images.unsplash.com/photo.jpg">` returns `images_from_stock_cdn=1`.
- HTML with `<img width="1" height="1">` is excluded from `image_count` (tracking pixel filter).
- YouTube iframe (`src="https://www.youtube.com/embed/..."`) returns `has_video=true`, `video_provider="youtube"`.
- Vimeo iframe returns `video_provider="vimeo"`.
- `<video>` tag returns `video_provider="native"`.
- JSON-LD with `"@type": "VideoObject"` returns `has_video_schema=true`.
- HTML with no images and no video returns expected zero values.

### Signal computation unit tests

- `compute_video_component(False, None, False)` → `0.0`
- `compute_video_component(True, "youtube", True)` → `1.0`
- `compute_video_component(True, "other", False)` → `0.6`
- `compute_alt_coverage_component(0, 0, 0)` → `0.5` (neutral)
- `compute_alt_coverage_component(4, 4, 0)` → `1.0`
- `compute_alt_coverage_component(4, 0, 4)` → `0.5` (all decorative, neutral)
- `compute_alt_coverage_component(4, 1, 0)` → `0.0` (25% coverage)
- `compute_image_presence_component(0, 0)` → `0.0`
- `compute_image_presence_component(3, 0)` → `1.0`
- `compute_image_presence_component(3, 3)` → `0.3` (all stock)
- `compute_image_word_ratio_component(0, 1000)` → `0.5` (neutral)
- `compute_image_word_ratio_component(3, 900)` → `1.0` (300 words/image)
- `compute_image_word_ratio_component(10, 200)` → `0.6` (20 words/image — over-imaged)
- `compute_image_word_ratio_component(1, 2000)` → `0.3` (2000 words/image — sparse)
- `multimedia_signal` is bounded `[0.0, 1.0]` for all valid inputs.
- `multimedia_metadata = None` returns `(0.5, {"multimedia_fallback_used": True})`.
- `multimedia_signal_enabled = false` returns `0.5` across the board.

### Integration tests

- Value model formula with `w_multimedia=0.10` produces correct weighted output.
- `value_model_diagnostics` on new `Suggestion` rows contains all multimedia fields.
- Existing five/six/seven signal computations produce identical output before and after this FR.
- Settings API returns and accepts all three new multimedia fields.

### Manual verification

- Sync a content item with known video and image content. Confirm `multimedia_metadata` is populated.
- Confirm high-multimedia destination pages score higher in value model pre-ranking.
- Confirm `multimedia_signal_enabled = false` produces `multimedia_signal = 0.5` on all suggestions.
- Confirm the settings card sub-section renders correctly.
- Confirm the "N pages have multimedia metadata" counter updates after a sync run.

## Acceptance Criteria

- `multimedia_signal` is the eighth slot in the FR-021 value model.
- It is computed exclusively from `ContentItem.multimedia_metadata`, populated at sync time. No HTML is fetched or parsed at pipeline time.
- Missing data falls back cleanly to `0.5` (neutral).
- All parameters are configurable and documented in the settings card.
- Suggestion diagnostics show the full multimedia breakdown.
- `score_final` in the main ranker is unchanged.
- Django migration is included.

## Out-of-Scope Follow-Up

- Per-image ML quality scoring (original vs stock detection beyond CDN hostname matching).
- Image dimension or resolution as a direct quality proxy (no image metadata is stored by current sync).
- Scroll-depth correlation with multimedia placement (FR-016 collects `scroll_50` as a boolean trigger — not continuous).
- Detecting autoplay video with sound (intrusive interstitial — a future penalty candidate).
- Infographic detection via image aspect ratio or file size heuristics.
