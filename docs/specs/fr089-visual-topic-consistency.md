# FR-089 - Visual-Topic Consistency Score

## Confirmation

- **Backlog confirmed**: `FR-089 - Visual-Topic Consistency Score` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No image-text coherence or visual consistency signal exists in the current ranker. The closest signal is `FR-040` (multimedia boost), which rewards the presence of images. FR-089 measures whether the images on a page are topically consistent with the page's text -- a fundamentally different quality axis.
- **Repo confirmed**: `ContentItem.distilled_text` and page image URLs are available at pipeline time.

## Source Summary

### Patent: US20140279220A1 -- Visual-Topic Consistency Score (Pinterest)

**Plain-English description of the patent:**

The patent describes measuring the consistency between visual content (images) and textual content on a page. Pages where images reinforce the text topic are higher quality than pages where images are generic stock photos unrelated to the content.

**What is adapted for this repo:**

- "image embeddings" are computed using a lightweight CLIP-lite model (4-bit quantized, CPU-only);
- "text embedding" is the existing page embedding from the pipeline;
- cosine similarity between mean image embedding and text embedding measures coherence.

## Plain-English Summary

Simple version first.

Some pages have images that match their topic -- an article about cooking shows pictures of food. Some pages use generic stock photos that have nothing to do with the content.

FR-089 measures this visual-topic consistency. If a page's images are topically aligned with its text, the page is higher quality. If the images are generic filler, the page scores lower.

Pages without images default to neutral.

## Problem Statement

Today the ranker rewards the presence of images (FR-040) but does not check whether those images are relevant to the page topic. A page with irrelevant stock photos scores the same as a page with topic-specific illustrations.

FR-089 closes this gap by measuring image-text topical coherence.

## Goals

FR-089 should:

- add a separate, explainable, bounded visual consistency signal;
- compute CLIP-lite embeddings for page images at index time;
- measure cosine similarity between mean image embedding and text embedding;
- keep pages without images neutral at `no_image_default` (0.5);
- keep ranking impact additive, bounded, and off by default.

## Non-Goals

FR-089 does not:

- modify FR-040 (multimedia boost);
- perform image recognition or classification;
- require GPU -- CLIP-lite is CPU-only with 4-bit quantization;
- implement production code in the spec pass.

## Math-Fidelity Note

### Signal definition

Let:

- `I = {img_1, ..., img_k}` = images on the destination page
- `emb_img(i)` = CLIP-lite embedding of image `i` (d-dimensional, 4-bit quantized on CPU)
- `emb_text` = existing text embedding of the page from the pipeline
- `mean_img_emb = (1/k) * sum(emb_img(i) for i in I)` = mean image embedding

**Cosine similarity:**

```text
cos_sim = (mean_img_emb . emb_text) / (||mean_img_emb||_2 * ||emb_text||_2)
```

**Score:**

```text
score_visual_consistency = max(0, cos_sim)
```

Clipped at 0 because negative cosine similarity means the images are anti-correlated with the text (very unusual, should be treated as zero consistency).

This naturally falls in `[0, 1]`.

**Neutral centering:**

```text
score_final = 0.5 + 0.5 * score_visual_consistency
```

**No-image fallback:**

```text
score_visual_consistency = no_image_default    (default 0.5)
```

Used when:

- page has no images;
- image embeddings failed to compute;
- feature is disabled.

### Why CLIP-lite

CLIP-lite is a lightweight variant of the CLIP model that:

- runs on CPU (no GPU required);
- uses 4-bit quantization for minimal RAM (~50 MB);
- produces embeddings that capture semantic image-text relationships;
- is deterministic and reproducible.

### Ranking hook

```text
score_visual_component =
  max(0.0, min(1.0, 2.0 * (score_final - 0.5)))
```

```text
score_final += visual_consistency.ranking_weight * score_visual_component
```

## Scope Boundary Versus Existing Signals

FR-089 must stay separate from:

- `FR-040` multimedia boost -- rewards image presence, not image-text coherence.
- `score_semantic` -- measures text-to-text similarity, not image-to-text.
- `FR-082` structural duplicate -- measures HTML structure, not visual content.

## Inputs Required

- Page image URLs -- from `ContentItem` or crawl data
- CLIP-lite model (4-bit quantized, CPU) -- bundled with the backend
- Existing text embedding -- already available from the pipeline

## Settings And Feature-Flag Plan

### Operator-facing settings

Recommended keys (from `recommended_weights.py`):

- `visual_consistency.enabled`
- `visual_consistency.ranking_weight`
- `visual_consistency.no_image_default`

Defaults:

- `enabled = true`
- `ranking_weight = 0.02`
- `no_image_default = 0.5`

## Diagnostics And Explainability Plan

Required fields:

- `score_visual_consistency`
- `visual_consistency_state` (`computed`, `neutral_feature_disabled`, `neutral_no_images`, `neutral_processing_error`)
- `image_count` -- number of images on the page
- `cosine_similarity` -- raw cosine sim between mean image and text embeddings
- `has_images` -- boolean

Plain-English review helper text should say:

- `Visual-topic consistency measures whether the images on this page match its text content.`
- `A high score means images reinforce the topic. A low score means images are generic or unrelated.`
- `Pages without images default to neutral.`

## Storage / Model / API Impact

### Content model

Add:

- `score_visual_consistency: FloatField(default=0.5)`
- `visual_consistency_diagnostics: JSONField(default=dict, blank=True)`

### Backend API

Add:

- `GET /api/settings/visual-consistency/`
- `PUT /api/settings/visual-consistency/`

## Recommended Preset Integration

### `recommended_weights.py` entries (already forward-declared)

```python
"visual_consistency.enabled": "true",
"visual_consistency.ranking_weight": "0.02",
"visual_consistency.no_image_default": "0.5",
```
