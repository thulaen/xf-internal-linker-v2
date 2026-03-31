# Weight Presets Operator Manual

## Simple Version

A weight preset is a saved ranking recipe.

It stores all of the live ranking settings in one named snapshot.

Use presets to:

- start from a known-good setup
- save your own experiments
- get back to a safe setup fast

The `Recommended` preset is the built-in starting point.

## Where the truth lives

There is now one backend source of truth for the recommended numbers:

- `backend/apps/suggestions/recommended_weights.py`

That file feeds:

- the `Recommended` system preset
- backend fallback defaults
- the Settings screen guidance

Migration `0017_refresh_recommended_feature_flags.py` updates older installs so the built-in preset matches the current recommendation.

## Recommended preset

The `Recommended` preset now turns on every shipped ranking feature in Settings.

Small but important note: the exact numbers below are not copied from a single outside paper. They are engineering starting points inferred from the cited sources below and from how this codebase implements each feature.

### Core blend

| Key | Recommended value | Plain-English reason |
| --- | --- | --- |
| `w_semantic` | `0.40` | Meaning match stays the biggest signal. |
| `w_keyword` | `0.25` | Exact words and forum jargon still matter. |
| `w_node` | `0.20` | Structural closeness gets a real voice. |
| `w_quality` | `0.15` | Quality helps without overpowering relevance. |

### Silo ranking

| Key | Recommended value | Plain-English reason |
| --- | --- | --- |
| `silo.mode` | `prefer_same_silo` | Softly prefers same-topic links without hard blocking. |
| `silo.same_silo_boost` | `0.05` | Gentle nudge toward same-silo destinations. |
| `silo.cross_silo_penalty` | `0.05` | Gentle nudge away from cross-silo destinations. |

If you have not assigned scopes to silo groups yet, this setting has little or no effect.

### March 2026 PageRank

| Key | Recommended value | Plain-English reason |
| --- | --- | --- |
| `weighted_authority.ranking_weight` | `0.10` | Authority helps, but it should not boss the whole rank. |
| `weighted_authority.position_bias` | `0.5` | Earlier links matter a bit more, but not too much. |
| `weighted_authority.empty_anchor_factor` | `0.6` | Empty anchors lose value, but are not thrown away. |
| `weighted_authority.bare_url_factor` | `0.35` | Naked URLs are weak anchor text, so they are discounted hard. |
| `weighted_authority.weak_context_factor` | `0.75` | Sidebar/footer-like links are discounted a bit. |
| `weighted_authority.isolated_context_factor` | `0.45` | Thin or isolated contexts are discounted more strongly. |

### Link freshness

| Key | Recommended value | Plain-English reason |
| --- | --- | --- |
| `link_freshness.ranking_weight` | `0.05` | Freshness is a light tie-breaker. |
| `link_freshness.recent_window_days` | `30` | One month is a simple balanced window. |
| `link_freshness.newest_peer_percent` | `0.25` | Compare against the freshest quarter of peers. |
| `link_freshness.min_peer_count` | `3` | Wait for a little history before scoring. |
| `link_freshness.w_recent` | `0.35` | Recent gains matter. |
| `link_freshness.w_growth` | `0.35` | Growth speed matters just as much. |
| `link_freshness.w_cohort` | `0.20` | Peer comparison is helpful, but secondary. |
| `link_freshness.w_loss` | `0.10` | Link loss is a light penalty, not a hammer. |

### Phrase matching

| Key | Recommended value | Plain-English reason |
| --- | --- | --- |
| `phrase_matching.ranking_weight` | `0.08` | Matching phrases should matter, but not become absolute. |
| `phrase_matching.enable_anchor_expansion` | `true` | Let the system discover useful anchor phrases. |
| `phrase_matching.enable_partial_matching` | `true` | Small wording differences should not kill good matches. |
| `phrase_matching.context_window_tokens` | `8` | Enough nearby words to judge context without too much noise. |

### Learned anchors

| Key | Recommended value | Plain-English reason |
| --- | --- | --- |
| `learned_anchor.ranking_weight` | `0.05` | Keep learned anchors light at first. |
| `learned_anchor.minimum_anchor_sources` | `2` | Need more than one source before trusting a pattern. |
| `learned_anchor.minimum_family_support_share` | `0.15` | Ask for some family support, but not too much. |
| `learned_anchor.enable_noise_filter` | `true` | Filter generic junk anchors like `click here`. |

### Rare-term propagation

| Key | Recommended value | Plain-English reason |
| --- | --- | --- |
| `rare_term_propagation.enabled` | `true` | Safe to keep on from day one. |
| `rare_term_propagation.ranking_weight` | `0.05` | Helps thin pages without overpowering stronger signals. |
| `rare_term_propagation.max_document_frequency` | `3` | Only very rare terms are borrowed. |
| `rare_term_propagation.minimum_supporting_related_pages` | `2` | One odd page should not decide. |

### Field-aware relevance

| Key | Recommended value | Plain-English reason |
| --- | --- | --- |
| `field_aware_relevance.ranking_weight` | `0.10` | Title/body alignment deserves a moderate voice. |
| `field_aware_relevance.title_field_weight` | `0.40` | Titles are usually the clearest short summary. |
| `field_aware_relevance.body_field_weight` | `0.30` | Body text matters, but titles still lead. |
| `field_aware_relevance.scope_field_weight` | `0.15` | Scope labels are supporting evidence. |
| `field_aware_relevance.learned_anchor_field_weight` | `0.15` | Learned anchor wording helps, but stays secondary. |

### GA4 + Search Console

| Key | Recommended value | Plain-English reason |
| --- | --- | --- |
| `ga4_gsc.ranking_weight` | `0.05` | First-party behavior data should help break ties, not overrule relevance. |

### Click distance

| Key | Recommended value | Plain-English reason |
| --- | --- | --- |
| `click_distance.ranking_weight` | `0.07` | Structural depth is a light tie-breaker. |
| `click_distance.k_cd` | `4.0` | Deep pages should score noticeably lower than shallow ones. |
| `click_distance.b_cd` | `0.75` | Heavy smoothing keeps the signal stable. |
| `click_distance.b_ud` | `0.25` | URL depth is light extra evidence only. |

### Feedback-driven reranking

| Key | Recommended value | Plain-English reason |
| --- | --- | --- |
| `explore_exploit.enabled` | `true` | The feature is on by default now. |
| `explore_exploit.ranking_weight` | `0.08` | Feedback should nudge, not dominate. |
| `explore_exploit.exploration_rate` | `1.41421356237` | Balanced UCB-style exploration start for this implementation. |

### Near-duplicate clustering

| Key | Recommended value | Plain-English reason |
| --- | --- | --- |
| `clustering.enabled` | `true` | Keeps duplicates from crowding the top results. |
| `clustering.similarity_threshold` | `0.04` | Strict duplicate cutoff. |
| `clustering.suppression_penalty` | `20.0` | Strongly pushes redundant versions down the list. |

### Slate diversity

| Key | Recommended value | Plain-English reason |
| --- | --- | --- |
| `slate_diversity.enabled` | `true` | Prevents nearly identical top-3 slates. |
| `slate_diversity.diversity_lambda` | `0.65` | Relevance still leads, but variety matters. |
| `slate_diversity.score_window` | `0.30` | Only diversify candidates that are still close to the best score. |
| `slate_diversity.similarity_cap` | `0.90` | Flags near-clones in diagnostics. |

## Using the presets card

### Load a preset

Click `Load`.

That overwrites all live in-scope ranking settings at once.

The UI asks for confirmation first.

### Save your own preset

Click `Save current as new preset`.

Type a name.

Click `Save`.

Important: this saves the live values that are already stored in the backend. If you changed a field on the page but did not click that card's normal `Save` button yet, that unsaved edit is not part of the preset.

### Rename a user preset

Only user presets can be renamed.

System presets stay read-only.

### Delete a user preset

Deleting a preset does not change live settings.

It only removes that saved snapshot.

## Weight history

The history card records:

- preset loads
- rollbacks
- R auto-tune changes

Rollback restores the full previous snapshot for that history row.

It does not delete old history.

It writes a brand-new history row for the rollback itself.

## Research sources

These sources explain the product direction behind the recommended starts:

- Google SEO Starter Guide: [developers.google.com/search/docs/fundamentals/seo-starter-guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide)
- Google ranking systems guide, including freshness systems: [developers.google.com/search/docs/appearance/ranking-systems-guide](https://developers.google.com/search/docs/appearance/ranking-systems-guide)
- Google duplicate URL guidance: [developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls)
- PageRank paper: [research.google.com/pubs/archive/334.pdf](https://research.google.com/pubs/archive/334.pdf)
- Maximal Marginal Relevance paper: [cs.cmu.edu/~jgc/publication/The_Use_MMR_Diversity_Based_LTMIR_1998.pdf](https://www.cs.cmu.edu/~jgc/publication/The_Use_MMR_Diversity_Based_LTMIR_1998.pdf)

For GA4/Search Console and feedback reranking, the product direction also comes from first-party analytics practice and classic exploration/exploitation theory. The exact starting values here are implementation-specific inferences for this codebase, not vendor-published magic numbers.
