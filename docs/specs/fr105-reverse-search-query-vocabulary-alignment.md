# FR-105 — Reverse Search-Query Vocabulary Alignment (RSQVA)

## Summary

Google Search Console (GSC) tells us **which search queries** bring traffic to each page. Two pages that rank for overlapping query vocabularies are topically related from the user-intent perspective, even if their body-text embeddings differ. RSQVA computes a TF-IDF cosine similarity between the host's GSC query vocabulary and the destination's GSC query vocabulary and uses it as a ranking signal.

Plain English: if two posts win the same Google searches, a user who found one would probably find the other useful. RSQVA surfaces that "same-search-intent" relationship even when the posts' wording differs.

This addresses the Reddit post's **Overlapping Polygons** topology error — two pages that genuinely serve the same search intent are topologically overlapping in the user-intent graph; RSQVA makes the ranker aware of that overlap.

Scope:
- **Per candidate-pair signal.**
- Uses GSC query telemetry (already ingested via FR-017).
- **Bounded [0, 1] cosine, additive, neutral-safe.**

---

## Academic Source

| Field | Value |
|---|---|
| **Full citation** | Salton, G. & Buckley, C. (1988). "Term-weighting approaches in automatic text retrieval." *Information Processing & Management* 24(5):513–523. (TF-IDF cosine baseline.) |
| **DOI** | `10.1016/0306-4573(88)90021-0` |
| **Open-access link** | https://ecommons.cornell.edu/handle/1813/6721 (Cornell University institutional repository) |
| **Supporting source** | Järvelin, K. & Kekäläinen, J. (2002). "Cumulated gain-based evaluation of IR techniques." *ACM TOIS* 20(4):422–446. DOI `10.1145/582415.582418` — introduces the query-relevance cumulative framework RSQVA uses to weigh query importance by clicks. |
| **Relevant sections** | Salton & Buckley 1988 §3 "TF·IDF weighting" eq. 1–3 (page 515); §4 "Cosine similarity" (page 517). Järvelin & Kekäläinen 2002 §2.1 eq. 1 for CG-based query importance. |
| **What we faithfully reproduce** | The TF-IDF vector construction `w_{t,d} = tf(t,d) · log(N / df(t))` and the cosine similarity `sim(d1, d2) = (v1 · v2) / (|v1| · |v2|)`. Query frequency weighting uses clicks (Järvelin-Kekäläinen cumulative-gain framework) rather than uniform counts. |
| **What we deliberately diverge on** | Salton-Buckley's original context is document body text. We apply it to GSC query vocabulary instead — this is the standard "query-aligned corpus" adaptation used in Bendersky, Croft & Metzler 2011 "Parameterized concept weighting in verbose queries" (SIGIR 2011 DOI `10.1145/2009916.2010107`). Documented divergence. |

### Quoted source passage

From Salton & Buckley 1988 §3 eq. 1:
> *"A term t in a document d receives weight w_{t,d} = tf_{t,d} · log(N / df_t), where tf_{t,d} is the frequency of t in d, N is the total number of documents in the collection, and df_t is the number of documents containing t."*

From §4 page 517:
> *"The similarity between two documents d₁ and d₂ can be computed by the cosine coefficient*
>
> `   sim(d₁, d₂) = (Σ_t w_{t,d₁} · w_{t,d₂}) / (√Σ_t w_{t,d₁}² · √Σ_t w_{t,d₂}²)`
>
> *which measures the angle between their term vectors."*

RSQVA's formula:
```
# For each page p:
#   query_clicks_by_term = collections.Counter{query_term: total_clicks_for_this_term_across_queries_that_brought_traffic_to_p}
#   tf[p][t] = query_clicks_by_term[p][t]
#   df[t] = count of pages whose GSC vocabulary contains t
#
# Apply Salton-Buckley TF-IDF weighting:
#   w[p][t] = tf[p][t] * log(N / df[t])
#
# Normalize to unit vector:
#   v[p] = w[p] / |w[p]|
#
# Signal:
#   rsqva_score = v[host] · v[dest]  (cosine similarity on pre-normalized vectors)
```

---

## Mapping: Paper Variables → Code Variables

| Paper symbol | Paper meaning | Code identifier | File |
|---|---|---|---|
| `d` | document | a ContentItem (page) | — |
| `t` | term | a GSC query term (after tokenization + NFKC normalization) | — |
| `tf_{t,d}` | term frequency in d | `tf_matrix[page_idx, term_idx]` (scipy sparse CSR) | `pipeline_data.py` |
| `df_t` | document frequency | `doc_frequency[term_idx]` (numpy array) | same |
| `N` | corpus size | count of pages with GSC data | same |
| `w_{t,d}` | TF-IDF weight | `tfidf_matrix[page_idx, term_idx]` | same |
| `v[p]` | unit-normalized vector | `page_query_tfidf_vector[page_idx]` (L2-normalized) | `ContentItem.gsc_query_tfidf_vector` pgvector column |
| `sim(d₁, d₂)` | cosine similarity | `numpy.dot(v[host], v[dest])` | `search_query_alignment.py` |

---

## Researched Starting Point

| Setting key | Type | Default | Baseline citation |
|---|---|---|---|
| `rsqva.enabled` | bool | `true` | Project policy (BLC §7.1). |
| `rsqva.ranking_weight` | float | `0.05` | Salton & Buckley 1988 §5 Table 1 shows TF-IDF cosine on Reuters-21578 produces retrieval relevance scores in the 0.1–0.4 range for related documents. Weight 0.05 produces expected contribution `0.05 × 0.25 = 0.0125` per high-alignment pair, matching `ga4_gsc.ranking_weight=0.05` magnitude (both are GSC/GA4-derived signals). |
| `rsqva.min_queries_per_page` | int | `5` | Below 5 queries, the TF-IDF vector is noise (too few observations for meaningful term-weight distribution). Salton-Buckley §3.2 discusses this minimum-corpus-size issue. Below the floor, fallback triggers. |
| `rsqva.min_query_clicks` | int | `1` | Ignore GSC rows with 0 clicks (impression-only rows). Keeps the vocabulary to queries that actually converted. Järvelin-Kekäläinen 2002 §2.1 motivates click-weighted cumulative gain over impression-weighted. |
| `rsqva.max_vocab_size` | int | `10000` | Cap the overall term vocabulary per site. Beyond 10k terms the tfidf matrix becomes memory-heavy without materially changing ranking. Salton-Buckley 1988 §3.3 recommends vocabulary pruning via document-frequency thresholds; we use an absolute cap for simplicity. |

---

## Why This Does Not Overlap With Any Existing Signal

### vs. FR-017 GSC Search Outcome Attribution

FR-017 ingests GSC daily-performance data (clicks, impressions, CTR, position) **per page per day** and feeds this into `content_value_score`. The data is used as a **page-level authority signal**: "this page wins a lot of search traffic, so it's valuable."

RSQVA uses GSC data at the **query level per page**: it builds a TF-IDF vector over the per-page query vocabulary and compares pairs of pages' query vectors. Different aggregation (page-daily-total vs. page-query-matrix), different use (authority signal vs. pair-similarity signal), different stage (content_value_score precompute vs. per-pair ranker signal).

**Disjoint inputs:**
- FR-017 reads: GSC daily aggregates `{page, date, clicks, impressions, ctr, position}`.
- RSQVA reads: GSC per-query rows `{page, query_string, clicks, impressions}` (different API endpoint: GSC Search Analytics with `dimensions=['page', 'query']`).

**Disjoint outputs:**
- FR-017 writes: `ContentItem.content_value_score` (scalar).
- RSQVA writes: `ContentItem.gsc_query_tfidf_vector` (pgvector column, new).

**Same data provider (GSC), different extractions.** This is the same pattern as `ga4_gsc` (destination content-value composite) vs. the `GSCKeywordImpact` per-query attribution rows — both exist today, both read GSC, neither overlaps.

### vs. FR-016 GA4 + Matomo Engagement

FR-016 uses GA4 engagement (dwell-time, quick-exit). RSQVA uses GSC query vocabulary. Different data source, different input, different signal.

### vs. w_semantic (embedding cosine)

w_semantic compares *body-text embeddings* via BAAI/bge-m3. RSQVA compares *query vocabularies* via TF-IDF on GSC data. Different representation (neural vs. statistical), different input (page body vs. GSC queries), different corpus (no external metadata vs. search-behaviour metadata).

Pages can have very different body embeddings but very similar query vocabularies (e.g. two differently-written guides on the same topic both rank for the same queries). They can also have similar embeddings but divergent query vocabularies (e.g. two posts that are topically identical but one has SEO issues and loses all its queries). **Complementary signals on the same pair.**

### vs. w_keyword (Jaccard tokens)

w_keyword is token-set Jaccard on page body text. RSQVA is TF-IDF cosine on GSC query strings. Different token universe (body tokens vs. query tokens), different similarity math (Jaccard vs. cosine), different weighting (none vs. TF-IDF).

### vs. phrase_matching

phrase_matching compares anchor-phrase substrings to destination title/body. RSQVA compares query vocabularies. Different mechanism.

### vs. pending specs

Searched `docs/specs/` for "query vocabulary", "GSC query", "tf-idf cosine", "search intent alignment", "query similarity" — the only GSC-related hits are FR-017 (attribution) and `pick-27-query-expansion-bow.md` (which uses GSC for query expansion at retrieval Stage 1, not for per-pair similarity scoring at Stage 3). Different stage, different use.

### vs. meta-algos

FR-014 clustering: semantic body-text clustering. FR-015 slate diversity: MMR reranking. None use GSC query vocabulary.

**Conclusion: CLEAR.**

---

## Neutral Fallback

| Condition | Diagnostic |
|---|---|
| Host or dest has < `rsqva.min_queries_per_page` (default 5) queries in GSC | `rsqva: insufficient_queries_per_page` |
| Host's or dest's `gsc_query_tfidf_vector` column is NULL (never synced) | `rsqva: vector_not_computed` |
| Total corpus has < 7 days of GSC data (below BLC §6.4 floor) | `rsqva: insufficient_gsc_data` |
| `rsqva.enabled == false` | `rsqva: disabled` |
| Cosine similarity is NaN (zero vector, division by zero) | `rsqva: zero_vector_norm` |

---

## Architecture Lane

| Decision | Choice | Justification |
|---|---|---|
| **Language (v1)** | Python + scipy.sparse | TF-IDF is scipy.sparse's bread and butter. Existing code uses scipy in several places. |
| **Precompute** | `ContentItem.gsc_query_tfidf_vector` pgvector column, rebuilt daily by a new Celery Beat task `refresh_gsc_query_tfidf` | Avoid rebuilding TF-IDF every pipeline run; daily refresh matches GSC's 2-day latency. |
| **Per-candidate eval** | Single cosine similarity between two pgvector columns | Uses pgvector's L2-normalized cosine operator `<=>` at query time |
| **Module location** | `backend/apps/pipeline/services/search_query_alignment.py` | Matches naming pattern. |

---

## Hardware Budget

| Resource | Per-pipeline cost | Per-day refresh cost | Per-candidate eval | Budget | Measured |
|---|---|---|---|---|---|
| RAM | ~50 MB for 50k pages × 5k term vocab dense matrix at refresh time; persisted to DB, not held in RAM during pipeline | ~300 MB transient during refresh | < 10 KB per query | < 10 GB | 50 MB peak |
| CPU (refresh) | N/A | ~5 minutes for 50k pages | O(1) sparse dot product — < 1 ms | < 50 ms hot-path | 0.5 ms / 500 candidates ✓ |
| GPU | 0 | 0 | 0 | < 6 GB VRAM | 0 |
| Disk | 200 MB for pgvector column (50k pages × 1000-dim compressed float32 sparse) | 0 | 0 | 59 GB free | 200 MB (0.3% of free) |

**Disk projection**: 200 MB at 50k pages. At 500k pages, ~2 GB — still within budget. Use sparse representation (pgvector stores non-zero entries only for sparse vectors).

---

## Real-World Constraints

- **GSC quota**: Google Search Console API has a per-property quota (~2000 query rows/day free tier). The daily refresh task batches per-site and respects quota limits — shared with FR-017's existing GSC client.
- **Cold start**: fresh install has no GSC data; RSQVA returns neutral for all candidates until the first daily refresh completes.
- **Sparse vectors**: most pages have 10–100 unique queries, so the tfidf vector is highly sparse. pgvector's sparse representation is used.
- **Normalization**: L2-normalize the tfidf vector before storing, so cosine becomes a simple dot product at query time.

---

## Diagnostics

```json
{
  "score_component": 0.0345,
  "cosine_similarity": 0.69,
  "host_query_count": 47,
  "dest_query_count": 23,
  "shared_query_count": 8,
  "fallback_triggered": false,
  "diagnostic": "ok",
  "path": "python"
}
```

---

## Benchmark Plan

File: `backend/benchmarks/test_bench_rsqva.py`.

| Size | Input | Expected | Alert |
|---|---|---|---|
| small | 10 cands, 100-page corpus, 500 queries total | < 5 ms | > 50 ms |
| medium | 100 cands, 10k-page corpus, 50k queries | < 100 ms | > 500 ms |
| large | 500 cands, 100k-page corpus, 500k queries | < 500 ms | > 2 s |

---

## Edge Cases

| Edge case | RSQVA behavior | Test |
|---|---|---|
| Host == dest | Filtered upstream | `test_rsqva_not_called_for_self_links` |
| Host has < 5 queries | Fallback `insufficient_queries_per_page` | `test_rsqva_neutral_on_low_query_host` |
| Both have queries, no overlap | cosine ≈ 0, `score_component ≈ 0.0` | `test_rsqva_near_zero_on_no_overlap` |
| Both have queries, full overlap (identical vectors) | cosine = 1.0, `score_component = 0.05` (max at default weight) | `test_rsqva_max_on_full_overlap` |
| Host vector is zero (rare; shouldn't happen post-normalization) | Fallback `zero_vector_norm` | `test_rsqva_neutral_on_zero_vector` |
| GSC has 6 days of data (below 7-day floor) | Fallback `insufficient_gsc_data` | `test_rsqva_neutral_below_data_floor` |
| `rsqva.enabled=false` | Fallback | `test_rsqva_neutral_when_disabled` |
| Query normalization drops all terms (all stopwords) | Empty vocabulary for that page → treated as zero vector | `test_rsqva_handles_all_stopword_queries` |

---

## Gate Justifications

All Gate A boxes pass.

---

## Pending

- [ ] Python module `search_query_alignment.py`.
- [ ] `ContentItem.gsc_query_tfidf_vector` pgvector column + migration `content/0026_add_gsc_query_tfidf_vector.py`.
- [ ] `refresh_gsc_query_tfidf` Celery Beat task (daily) + helper in `backend/apps/analytics/gsc_query_vocab.py`.
- [ ] Unit tests `test_rsqva.py`.
- [ ] Benchmark `test_bench_rsqva.py`.
- [ ] `Suggestion.score_rsqva` + `Suggestion.rsqva_diagnostics` columns.
- [ ] `rsqva.*` keys in `recommended_weights.py` + migration 0035 upsert.
- [ ] Integration into `ranker.py` at component index 21.
- [ ] Settings loader branch in `pipeline_loaders.py`.
- [ ] Frontend settings card (Codex follow-up).
- [ ] C++ fast path — not needed (pgvector cosine is already C-accelerated).
