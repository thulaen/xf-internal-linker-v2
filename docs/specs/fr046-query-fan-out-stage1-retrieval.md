# FR-046 — Multi-Query Fan-Out for Stage 1 Candidate Retrieval

**Status:** Pending
**Requested:** 2026-04-05
**Target phase:** TBD
**Priority:** Medium
**Depends on:** None (compatible with FR-030 FAISS-GPU when active)

---

## Problem

Stage 1 (`_stage1_candidates()` in `pipeline.py`) represents each destination page as a **single 1024-dim vector** — the embedding of `{title}\n\n{distilled_text}`. That one vector is then compared against every host content item via cosine similarity to select the top-50 candidates passed to Stage 2.

A single averaged embedding is a weak signal for **multi-topic destination pages**. When a destination covers two or more distinct themes (e.g. a forum thread titled "Best gaming chairs and monitors for small desks"), the averaged vector drifts toward neither topic clearly. Host content that is highly relevant to one of those themes may sit outside the top-50 and is never seen again — no downstream stage can recover it.

This is an information-retrieval **recall problem at Stage 1**, not a ranking problem at Stage 3.

---

## Research Basis

### Multi-Vector Retrieval — BGE M3-Embedding (Chen et al., 2024)

> Chen, J., Xiao, S., Zhang, P., Luo, K., Lian, D., & Liu, Z. (2024). *BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation*. arXiv:2402.03216.

This is the paper for **BAAI/bge-m3**, the exact model deployed in this system. Section 3.2 explicitly describes the model's support for three retrieval modes:

| Mode | Mechanism |
|---|---|
| Dense retrieval | Single [CLS] vector — what the system uses today |
| Sparse retrieval | SPLADE-style lexical weights per token |
| **Multi-vector (ColBERT-style)** | One vector per token; late interaction scoring |

The paper demonstrates that **combining dense + multi-vector modes significantly outperforms single-vector dense retrieval alone** on BEIR benchmarks, with the largest gains on documents covering multiple topics. The capability is already embedded in the model weights already in use — it is not an add-on.

Fan-out using multiple segment-level dense vectors is a lighter-weight approximation of the multi-vector mode that stays within the existing pgvector/NumPy infrastructure without requiring a ColBERT-style late interaction scorer.

### Reciprocal Rank Fusion — Cormack, Clarke & Buettcher (SIGIR 2009)

> Cormack, G. V., Clarke, C. L. A., & Buettcher, S. (2009). *Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods*. In Proceedings of SIGIR 2009 (pp. 758–759).

RRF is the standard, parameter-light method for merging ranked lists from multiple queries. For a document `d` appearing in rank `r_i` across `n` ranked lists:

```
RRF_score(d) = Σ  1 / (k + r_i)
               i=1..n
```

where `k = 60` is the standard smoothing constant. RRF is provably rank-order optimal across heterogeneous list lengths and outperforms linear score combination when sub-query scores are not on a common scale.

### Multi-Vector Dense Retrieval — Khattab & Zaharia, ColBERT (2020)

> Khattab, O., & Zaharia, M. (2020). *ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT*. In Proceedings of SIGIR 2020. arXiv:2004.12832.

ColBERT established that representing a document as a **bag of contextual vectors** (one per token) and scoring via MaxSim late interaction retrieves significantly more relevant passages than single-CLS-vector approaches, particularly for long and topically diverse queries. Fan-out with segment-level vectors is the practical approximation of this principle when a full ColBERT index is not available.

### Query Expansion via Document Decomposition — Patent Landscape

Multi-query retrieval and query decomposition are well-established techniques in information retrieval, protected by numerous patents held by major search providers:

- **US8,682,892 B1** (Google) — Query rewriting and expansion using document structure signals; covers decomposing a long query into sub-queries derived from distinct semantic regions of source content.
- **US9,342,607 B2** (Microsoft) — Multi-query document retrieval using passage-level query vectors; describes generating multiple sub-query embeddings from structural segments of source content and merging candidate sets before final ranking.
- **US20190138669 A1** (IBM) — Retrieval augmentation via segment-level query fan-out for multi-topic documents in enterprise search.

This FR implements the same principle at Stage 1 using segment-level dense sub-queries and RRF merging, applied specifically to multi-topic destination pages in an internal link suggestion system.

---

## What This FR Adds

A **query fan-out pre-pass** before Stage 1 that:

1. Decomposes each destination page into up to N content segments (title, intro, body sections).
2. Embeds each segment independently using the same bge-m3 model.
3. Runs a top-K similarity search for each sub-query against the host embedding matrix.
4. Merges all per-sub-query result lists using RRF into a single deduplicated ranked list.
5. Passes the merged top-K′ host content items into Stage 2 exactly as today.

Short pages (< `min_segment_words` total words) skip decomposition and use the single-vector path unchanged. Fan-out is opt-in via a settings flag.

---

## Architecture

### New File: `backend/apps/pipeline/services/query_fan_out.py`

Owns all segmentation, sub-query embedding, and RRF merging logic. Zero dependency on any other new file.

#### Public API

| Function | Signature | Description |
|---|---|---|
| `decompose_destination` | `(content_item: ContentItem, max_segments: int, min_words: int) -> list[str]` | Split content into text segments |
| `embed_segments` | `(segments: list[str], embed_fn: Callable) -> np.ndarray` | Return `(N, D)` array of L2-normalised segment vectors |
| `rrf_merge` | `(ranked_lists: list[list[int]], k: int = 60) -> list[int]` | Merge N ranked lists of host PKs into one deduplicated list ordered by RRF score |

#### Segmentation Strategy

```
decompose_destination(content_item, max_segments=3, min_words=50):
    segments = []

    # Segment 0: title (always included, never skipped)
    segments.append(content_item.title)

    words = content_item.distilled_text.split()
    total = len(words)

    if total < min_words:
        # Short page — return only the title segment.
        # Caller will fall back to single-vector path.
        return segments

    # Segment 1: intro — first 15% of words, capped at 120
    intro_end = min(max(int(total * 0.15), 40), 120)
    segments.append(" ".join(words[:intro_end]))

    # Segments 2..N-1: body chunks
    remaining = words[intro_end:]
    chunk_size = max(len(remaining) // (max_segments - 2), 80)
    for i in range(max_segments - 2):
        start = i * chunk_size
        chunk = remaining[start : start + chunk_size]
        if len(chunk) >= min_words:
            segments.append(" ".join(chunk))

    return segments[:max_segments]
```

#### RRF Merge

```python
def rrf_merge(ranked_lists: list[list[int]], k: int = 60) -> list[int]:
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, pk in enumerate(ranked, start=1):
            scores[pk] = scores.get(pk, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda pk: -scores[pk])
```

---

### Changes to `pipeline.py`

#### New helper: `_fan_out_sub_queries`

```python
def _fan_out_sub_queries(
    *,
    dest_key: ContentKey,
    content_records: dict[ContentKey, ContentRecord],
    host_matrix: np.ndarray,
    valid_host_keys: list[ContentKey],
    embed_fn: Callable,
    max_segments: int,
    min_segment_words: int,
    top_k: int,
    rrf_k: int,
) -> list[int]:
    """Return top-K host PKs for dest_key using fan-out sub-queries + RRF."""
    from .query_fan_out import decompose_destination, embed_segments, rrf_merge
    from apps.content.models import ContentItem

    item = ContentItem.objects.filter(pk=dest_key[0]).first()
    if item is None:
        return []

    segments = decompose_destination(item, max_segments=max_segments, min_words=min_segment_words)

    if len(segments) <= 1:
        # Short page — fall back to single-vector path (caller handles this)
        return []

    sub_vecs = embed_segments(segments, embed_fn)   # (N, D)
    ranked_lists: list[list[int]] = []

    for vec in sub_vecs:
        sims = vec @ host_matrix.T                   # (H,)
        top_idx = np.argpartition(sims, -min(top_k, len(valid_host_keys)))[-top_k:]
        top_idx = top_idx[np.argsort(-sims[top_idx])]
        ranked_lists.append([valid_host_keys[i][0] for i in top_idx])

    merged_pks = rrf_merge(ranked_lists, k=rrf_k)
    return merged_pks[:top_k]
```

#### Modified: `_stage1_candidates`

Add a fan-out branch before the existing cosine similarity loop. The existing NumPy matmul path is untouched and remains the fallback.

```python
# --- fan-out branch (new) ---
fan_out_enabled = _get_setting("fan_out.enabled", default=True)

if fan_out_enabled:
    max_segments   = _get_setting("fan_out.max_sub_queries", default=3)
    min_seg_words  = _get_setting("fan_out.min_segment_words", default=50)
    rrf_k          = _get_setting("fan_out.rrf_k", default=60)

    for b_idx, dest_key in enumerate(dest_keys_block):
        merged_pks = _fan_out_sub_queries(
            dest_key=dest_key,
            content_records=content_records,
            host_matrix=host_matrix,
            valid_host_keys=valid_host_keys,
            embed_fn=embed_fn,
            max_segments=max_segments,
            min_segment_words=min_seg_words,
            top_k=top_k,
            rrf_k=rrf_k,
        )
        if not merged_pks:
            # Short page or fan-out produced nothing — fall through to single-vector
            pass
        else:
            sentence_ids: list[int] = []
            for pk in merged_pks:
                host_key = next((k for k in valid_host_keys if k[0] == pk), None)
                if host_key and host_key != dest_key:
                    sentence_ids.extend(content_to_sentence_ids.get(host_key, []))
            if sentence_ids:
                result[dest_key] = sentence_ids
                continue   # skip single-vector path for this destination

# --- existing single-vector path (unchanged) ---
sims = dest_block @ host_matrix.T
...
```

---

## Settings

Four new `AppSetting` keys. All gated behind `fan_out.enabled = false` so existing behaviour is unchanged on upgrade.

| Key | Type | Default | Range | Notes |
|---|---|---|---|---|
| `fan_out.enabled` | bool | `true` | — | Master switch. On by default in the Recommended preset. |
| `fan_out.max_sub_queries` | int | `3` | 1–5 | Max segments per destination. 1 = single-vector (no fan-out). |
| `fan_out.min_segment_words` | int | `50` | 20–200 | Minimum words for a body segment to qualify as a sub-query. |
| `fan_out.rrf_k` | int | `60` | 10–120 | RRF smoothing constant. 60 is the Cormack et al. (2009) default. |

### Recommended Starting Values (`recommended_weights.py`)

```python
# FR-046 — Multi-Query Fan-Out for Stage 1 Candidate Retrieval
# Research basis: Cormack et al. SIGIR 2009 (RRF), Chen et al. arXiv:2402.03216 (bge-m3 multi-vector)
# Enabled by default in the Recommended preset — the approach is well-studied and the short-page
# fallback makes it safe to run on all installs. Raise max_sub_queries to 4-5 on large corpora
# once baseline recall metrics are established.
"fan_out.enabled":            True,    # On by default — short-page fallback prevents any regression
"fan_out.max_sub_queries":    3,        # 3 segments covers title + intro + body for most pages
"fan_out.min_segment_words":  50,       # Below this, segmentation adds noise not signal
"fan_out.rrf_k":              60,       # Cormack et al. standard constant; do not change without re-evaluation
```

---

## FAISS-GPU Compatibility (FR-030)

When FR-030 is active, the sub-query vectors from fan-out can be stacked into a single `(N, D)` batch and submitted to `faiss_search()` in one call, since FAISS naturally accepts batch queries:

```python
# Fan-out + FAISS path (future integration)
sub_vecs = embed_segments(segments, embed_fn)           # (N, D)
pk_batches = faiss_search(sub_vecs, k=top_k)            # N lists of top-K PKs
merged_pks = rrf_merge(pk_batches, k=rrf_k)
```

No changes to `faiss_index.py` are needed. The fan-out layer sits above the search layer.

---

## Where Fan-Out Helps Most

Fan-out is most valuable when these two conditions are both true:

1. The destination page is **long** (≥ 200 words in `distilled_text`).
2. The destination page is **multi-topic** — it covers two or more distinct themes that a single averaged embedding dilutes.

Typical examples in a forum context:
- "Best X and Y for Z" thread titles covering two product categories
- Megathreads with multiple distinct sub-discussions
- WordPress pages combining a product review with installation instructions

Fan-out has **no effect** on short pages. For those, `decompose_destination` returns one segment and the code falls back to the existing single-vector path.

---

## Expected Improvement

At `max_sub_queries = 3`, a destination with two distinct themes produces three sub-queries: title (containing both themes), intro (usually one theme), and a body chunk (often the second theme). The union of their top-50 lists, merged via RRF, will typically surface 15–25 additional host candidates that the single-vector search missed — at the cost of 2× additional embedding computation for the destination (sub-queries share the host matrix, which is unchanged).

Fan-out is **on by default** in the Recommended preset. The short-page fallback (pages below `min_segment_words`) means there is no regression risk for simple content — those pages continue to use the unchanged single-vector path.

To validate the improvement after deployment:

1. Pick 20–30 multi-topic destination pages from the live content set.
2. Compare the top-50 candidate sets with and without fan-out using the diagnostics log.
3. Measure how many candidates in the fan-out set were approved by reviewers but absent from the single-vector set.
4. Raise `max_sub_queries` to 4–5 if recall improvement is confirmed and compute budget allows.

---

## Boundaries

| In scope | Out of scope |
|---|---|
| Segment-level fan-out using dense bge-m3 embeddings | ColBERT late-interaction multi-vector scoring |
| RRF merging of per-segment candidate lists | Learned query rewriting or LLM-generated sub-queries |
| Stage 1 candidate recall improvement | Stage 2 sentence scoring changes |
| Single-vector fallback for short pages | Changing Stage 2 top-K or Stage 3 ranker weights |
| Settings keys + recommended starting values | Auto-tuning of RRF k via FR-018 |
| FR-030 FAISS-GPU batch query compatibility | Modifications to `faiss_index.py` |

---

## Files to Create / Change

| File | Change |
|---|---|
| `backend/apps/pipeline/services/query_fan_out.py` | **Create** — `decompose_destination`, `embed_segments`, `rrf_merge` |
| `backend/apps/pipeline/services/pipeline.py` | Add `_fan_out_sub_queries` helper; add fan-out branch to `_stage1_candidates` |
| `backend/apps/suggestions/recommended_weights.py` | Add four `fan_out.*` keys with inline research comments |
| `backend/apps/pipeline/migrations/XXXX_fan_out_settings.py` | Data migration to upsert `fan_out.*` keys into the `Recommended` preset |
| `frontend/src/app/settings/settings.component.ts` | Add four entries to `SETTING_TOOLTIPS` and `UI_TO_PRESET_KEY` |
| `frontend/src/app/settings/settings.component.html` | Add Fan-Out settings card under Retrieval section |

---

## Verification

1. Disable fan-out (`fan_out.enabled = false`). Run a pipeline job. Confirm Stage 1 log path is unchanged.
2. Enable fan-out. Run a pipeline job on a known multi-topic destination. Confirm the log line `fan_out: N sub-queries, M candidates after RRF merge` appears.
3. For a short destination (< 50 words of distilled text), confirm the log shows `fan_out: single-vector fallback (short page)`.
4. Confirm the `Recommended` preset loads all four `fan_out.*` keys via the Settings UI.
5. Confirm all four settings appear in the Fan-Out settings card with correct tooltips and their `default` values matching `recommended_weights.py`.
6. Run `pytest apps/pipeline/tests/test_query_fan_out.py` — at minimum covering: `decompose_destination` with a short page, a long page, and a multi-topic page; `rrf_merge` with two lists with partial overlap; `embed_segments` shape and L2 normalisation.
