"""Canonical research-backed starting weights for the Recommended preset.

These values are the single backend source of truth for the default ranking
starting point shown in Settings and used when older presets are missing newer
keys.
"""

from __future__ import annotations

RECOMMENDED_PRESET_WEIGHTS: dict[str, str] = {
    "w_semantic": "0.40",
    "w_keyword": "0.25",
    "w_node": "0.20",
    "w_quality": "0.15",
    "silo.mode": "prefer_same_silo",
    "silo.same_silo_boost": "0.05",
    "silo.cross_silo_penalty": "0.05",
    "weighted_authority.ranking_weight": "0.10",
    "weighted_authority.position_bias": "0.5",
    "weighted_authority.empty_anchor_factor": "0.6",
    "weighted_authority.bare_url_factor": "0.35",
    "weighted_authority.weak_context_factor": "0.75",
    "weighted_authority.isolated_context_factor": "0.45",
    "rare_term_propagation.enabled": "true",
    "rare_term_propagation.ranking_weight": "0.05",
    "rare_term_propagation.max_document_frequency": "3",
    "rare_term_propagation.minimum_supporting_related_pages": "2",
    "field_aware_relevance.ranking_weight": "0.10",
    "field_aware_relevance.title_field_weight": "0.40",
    "field_aware_relevance.body_field_weight": "0.30",
    "field_aware_relevance.scope_field_weight": "0.15",
    "field_aware_relevance.learned_anchor_field_weight": "0.15",
    "ga4_gsc.ranking_weight": "0.05",
    "click_distance.ranking_weight": "0.07",
    "click_distance.k_cd": "4.0",
    "click_distance.b_cd": "0.75",
    "click_distance.b_ud": "0.25",
    "explore_exploit.enabled": "true",
    "explore_exploit.ranking_weight": "0.08",
    "explore_exploit.exploration_rate": "1.41421356237",
    "clustering.enabled": "true",
    "clustering.similarity_threshold": "0.04",
    "clustering.suppression_penalty": "20.0",
    "slate_diversity.enabled": "true",
    "slate_diversity.diversity_lambda": "0.65",
    "slate_diversity.score_window": "0.30",
    "slate_diversity.similarity_cap": "0.90",
    "link_freshness.ranking_weight": "0.05",
    "link_freshness.recent_window_days": "30",
    "link_freshness.newest_peer_percent": "0.25",
    "link_freshness.min_peer_count": "3",
    "link_freshness.w_recent": "0.35",
    "link_freshness.w_growth": "0.35",
    "link_freshness.w_cohort": "0.20",
    "link_freshness.w_loss": "0.10",
    "phrase_matching.ranking_weight": "0.08",
    "phrase_matching.enable_anchor_expansion": "true",
    "phrase_matching.enable_partial_matching": "true",
    "phrase_matching.context_window_tokens": "8",
    "learned_anchor.ranking_weight": "0.05",
    "learned_anchor.minimum_anchor_sources": "2",
    "learned_anchor.minimum_family_support_share": "0.15",
    "learned_anchor.enable_noise_filter": "true",
    # FR-038 — Information Gain Scoring
    # Forward-declared: these keys are inert until FR-038 is implemented and reads them.
    # A new migration (or manual DB update) is needed to push these into the seeded preset.
    # Research basis: US11354342B2. Starting weight is conservative (0.03) because this
    # signal is unvalidated on real content. Run diagnostics first, then raise to 0.05
    # once sample_novel_tokens look sensible across a live pipeline run.
    "information_gain.enabled": "true",
    "information_gain.ranking_weight": "0.03",
    "information_gain.min_source_chars": "200",
    # FR-039 — Entity Salience Match
    # Forward-declared: same note as FR-038 above — inert until FR-039 is implemented.
    # Research basis: US9251473B2. Starting weight is 0.04 — slightly higher than FR-038
    # because entity salience is a well-established IR signal and TF-IDF arithmetic is
    # deterministic and easy to inspect. max_site_document_frequency=20 allows moderately
    # common terms to qualify as salient, which is appropriate for a forum site where even
    # product names can appear on 10–15 pages.
    "entity_salience.enabled": "true",
    "entity_salience.ranking_weight": "0.04",
    "entity_salience.max_salient_terms": "10",
    "entity_salience.max_site_document_frequency": "20",
    "entity_salience.min_source_term_frequency": "2",
    # FR-040 - Multimedia Boost
    # Forward-declared: inert until FR-040 is implemented and reads these keys.
    # Research basis: Google image/video quality guidance, alt-text usage, and
    # multimedia-engagement studies. Starting weight is 0.10 because FR-040
    # belongs to the value-model family and should be material enough to reward
    # richer destinations without overpowering semantic fit or authority.
    "multimedia_signal_enabled": "true",
    "w_multimedia": "0.10",
    "multimedia_fallback_value": "0.5",
    # FR-041 - Originality Provenance Scoring
    # Forward-declared: inert until FR-041 is implemented and reads these keys.
    # Research basis: US8707459B2 plus lexical near-duplicate provenance math
    # using shingles, resemblance, and containment. Starting weight is 0.03
    # because the signal is narrow by design: it should gently prefer the
    # earliest, most source-like page within a near-copy family, not override
    # broader relevance or authority signals across unrelated pages.
    "originality_provenance.enabled": "true",
    "originality_provenance.ranking_weight": "0.03",
    "originality_provenance.resemblance_threshold": "0.55",
    "originality_provenance.containment_threshold": "0.80",
    # FR-042 - Fact Density Scoring
    # Forward-declared: inert until FR-042 is implemented and reads these keys.
    # Research basis: factual-density literature plus US9286379B2 document-quality
    # framing. Starting weight is 0.04 because this is a broadly useful quality
    # signal, but it still relies on heuristic fact-like sentence detection and
    # may be noisy on conversational forum content until calibrated on live data.
    "fact_density.enabled": "true",
    "fact_density.ranking_weight": "0.04",
    "fact_density.min_word_count": "120",
    "fact_density.density_cap_per_100_words": "8.0",
    "fact_density.filler_penalty_weight": "0.35",
    # FR-043 - Semantic Drift Penalty
    # Forward-declared: inert until FR-043 is implemented and reads these keys.
    # Research basis: Hearst TextTiling segmentation plus US8185378B2 text-
    # coherence ideas. Starting weight is 0.03 because this is a subtractive
    # quality guardrail and should begin conservatively to avoid over-penalizing
    # long forum pages, compilations, or pages with legitimate multi-section flow.
    "semantic_drift.enabled": "true",
    "semantic_drift.ranking_weight": "0.03",
    "semantic_drift.tokens_per_sequence": "20",
    "semantic_drift.block_size_in_sequences": "6",
    "semantic_drift.anchor_similarity_threshold": "0.18",
    "semantic_drift.min_word_count": "180",
    # FR-044 - Internal Search Intensity Signal
    # Forward-declared: inert until FR-044 is implemented and reads these keys.
    # Research basis: Matomo Site Search aggregates, burst-style trend math, and
    # US20050102259A1 query-trend analysis. Starting weight is 0.02 because this
    # signal is temporally noisy and query matching can overfire before operators
    # validate that active internal-search topics map cleanly onto destination pages.
    "internal_search.enabled": "true",
    "internal_search.ranking_weight": "0.02",
    "internal_search.recent_days": "3",
    "internal_search.baseline_days": "28",
    "internal_search.max_active_queries": "200",
    "internal_search.min_recent_count": "3",
    # FR-045 — Anchor Diversity & Exact-Match Reuse Guard
    # Forward-declared: inert until FR-045 is implemented and reads these keys.
    # Research basis: Google over-optimization penalty (Penguin) and anchor text
    # diversity best practices. Starting weight is 0.0 (guard-only mode) because
    # this signal is subtractive — it penalises repetitive anchors rather than
    # boosting diverse ones. Raise to 0.03 after confirming exact_match_share
    # thresholds are well-calibrated on the target site.
    "anchor_diversity.enabled": "true",
    "anchor_diversity.ranking_weight": "0.0",
    "anchor_diversity.min_history_count": "2",
    "anchor_diversity.max_exact_match_share": "0.40",
    "anchor_diversity.max_exact_match_count": "3",
    "anchor_diversity.hard_cap_enabled": "false",
    # FR-046 — Multi-Query Fan-Out for Stage 1 Candidate Retrieval
    # Forward-declared: inert until FR-046 is implemented and reads these keys.
    # Research basis: Cormack et al. 2009 reciprocal rank fusion and multi-query
    # decomposition for long-form documents. This FR modifies Stage 1 retrieval
    # (not scoring), so there is no ranking_weight — it affects which candidates
    # enter the pipeline, not how they are scored.
    "fan_out.enabled": "true",
    "fan_out.max_sub_queries": "3",
    "fan_out.min_segment_words": "50",
    "fan_out.rrf_k": "60",
    # FR-047 — Navigation Path Prediction
    # Forward-declared: inert until FR-047 is implemented and reads these keys.
    # Research basis: US7584181B2 (implicit links from user access patterns) plus
    # first-order Markov transition models on GA4 page_view sequences. Starting
    # weight is 0.04 because directional navigation data is a strong behavioural
    # signal, but it depends on sufficient GA4 session volume to be reliable.
    # Raise to 0.06 after validating that transition counts are stable across
    # pipeline runs on a live site with >50 sessions per source page.
    "navigation_path.enabled": "true",
    "navigation_path.ranking_weight": "0.04",
    "navigation_path.lookback_days": "90",
    "navigation_path.min_sessions": "50",
    "navigation_path.min_transition_count": "5",
    "navigation_path.w_direct": "0.6",
    "navigation_path.w_shortcut": "0.4",
    # FR-048 — Topical Authority Cluster Density
    # Forward-declared: inert until FR-048 is implemented and reads these keys.
    # Research basis: HITS hub/authority scoring, Majestic Topical Trust Flow,
    # HDBSCAN clustering on existing bge-m3 embeddings. Starting weight is 0.04
    # because topical depth is a well-established SEO signal but the cluster
    # quality depends on site size and content diversity. min_cluster_size=5
    # prevents noise clusters from inflating scores. Raise to 0.06 after
    # verifying that HDBSCAN produces stable, meaningful clusters on the target
    # site's embedding space.
    "topical_cluster.enabled": "true",
    "topical_cluster.ranking_weight": "0.04",
    "topical_cluster.min_cluster_size": "5",
    "topical_cluster.min_site_pages": "20",
    "topical_cluster.max_staleness_days": "14",
    "topical_cluster.fallback_value": "0.5",
    # FR-049 — Query Intent Funnel Alignment
    # Forward-declared: inert until FR-049 is implemented and reads these keys.
    # Research basis: WO2015200404A1 (query intent identification) and
    # US20110289063A1 (determining query intent). Starting weight is 0.03
    # because keyword-pattern intent classification is a coarse heuristic in v1
    # and the funnel model assumes a linear journey that not all content follows.
    # Raise to 0.05 after validating that GSC-based intent classification
    # produces stable, sensible stage assignments across a live site.
    "intent_funnel.enabled": "true",
    "intent_funnel.ranking_weight": "0.03",
    "intent_funnel.optimal_offset": "1",
    "intent_funnel.sigma": "1.2",
    "intent_funnel.min_confidence": "0.25",
    "intent_funnel.navigational_confidence_threshold": "0.6",
    # FR-050 — Seasonality & Temporal Demand Matching
    # Forward-declared: inert until FR-050 is implemented and reads these keys.
    # Research basis: US9081857B1 (freshness and seasonality-based content
    # determinations) plus classical seasonal decomposition. Starting weight is
    # 0.03 because seasonal scoring requires 12+ months of clean GA4/GSC data
    # and the signal is inherently noisy for sites with weak seasonal patterns.
    # Raise to 0.05 after confirming that seasonal_strength correctly separates
    # seasonal from perennial pages on a live site.
    "seasonality.enabled": "true",
    "seasonality.ranking_weight": "0.03",
    "seasonality.min_history_months": "12",
    "seasonality.min_seasonal_strength": "0.3",
    "seasonality.anticipation_window_months": "3",
    "seasonality.w_current": "0.7",
    "seasonality.w_anticipation": "0.3",
    "seasonality.index_cap": "3.0",
    # FR-021 - Graph-Based Link Candidate Generation
    "graph_candidate.enabled": "true",
    "graph_candidate.walk_steps_per_entity": "1000",
    "graph_candidate.min_stable_candidates": "50",
    "graph_candidate.min_visit_threshold": "3",
    "graph_candidate.top_k_candidates": "100",
    "graph_candidate.top_n_entities_per_article": "20",
    "value_model.enabled": "true",
    # Additive signal weights must sum to 1.0.
    # Rebalanced after FR-024 (engagement) and FR-025 (co-occurrence) were added.
    "value_model.w_relevance": "0.35",
    "value_model.w_traffic": "0.25",
    "value_model.w_freshness": "0.1",
    "value_model.w_authority": "0.1",
    "value_model.w_penalty": "0.5",
    "value_model.traffic_lookback_days": "90",
    "value_model.traffic_fallback_value": "0.5",
    # FR-024 - TikTok Read-Through Rate Engagement Signal
    "value_model.engagement_signal_enabled": "true",
    "value_model.w_engagement": "0.08",
    "value_model.engagement_lookback_days": "30",
    "value_model.engagement_words_per_minute": "200",
    "value_model.engagement_cap_ratio": "1.5",
    "value_model.engagement_fallback_value": "0.5",
    # FR-023 - Reddit Hot Decay
    # Forward-declared in C# HttpWorker (TrafficDecayService.cs) but was missing
    # from Django settings. Adapted from Reddit's Hot algorithm: recent traffic
    # momentum matters more than stale volume. gravity=0.05 is conservative;
    # raise to 0.08 after verifying that hot_score rankings are stable across
    # 7-day windows on a site with >100 daily active pages.
    "value_model.hot_decay_enabled": "true",
    "value_model.hot_gravity": "0.05",
    "value_model.hot_clicks_weight": "1.0",
    "value_model.hot_impressions_weight": "0.05",
    "value_model.hot_lookback_days": "90",
    # FR-025 - Session Co-Occurrence Signal
    "value_model.co_occurrence_signal_enabled": "true",
    "value_model.w_cooccurrence": "0.12",
    "value_model.co_occurrence_fallback_value": "0.5",
    "value_model.co_occurrence_min_co_sessions": "5",
    # =========================================================================
    # PATENT-BACKED RANKING SIGNALS (FR-051 to FR-059)
    # =========================================================================
    # FR-051 — Reference Context Scoring
    # Forward-declared: inert until FR-051 is implemented and reads these keys.
    # Research basis: US8577893B1 — "Ranking based on reference contexts" (Google,
    # 2013). Scores the ±5-token window around each link insertion point using
    # IDF-weighted rare-word overlap with the destination page. Starting weight is
    # 0.03 because this is a micro-context signal narrower than full-doc semantic
    # similarity; validate that window scores correlate with editorial approvals
    # before raising to 0.05. Reuses existing BM25 IDF vocabulary.
    # C++ extension: refcontext.cpp.
    "reference_context.enabled": "true",
    "reference_context.ranking_weight": "0.03",
    "reference_context.window_tokens": "5",
    "reference_context.idf_smoothing": "1",
    # FR-052 — Readability Level Matching
    # Forward-declared: inert until FR-052 is implemented and reads these keys.
    # Research basis: US20070067294A1 — "Readability and context identification
    # and exploitation" (Google, 2005). Flesch-Kincaid grade level comparison
    # between source and destination; soft penalty when grade levels differ by
    # more than max_grade_gap. Starting weight 0.02 — conservative quality
    # guardrail that prevents jarring difficulty jumps.
    "readability_match.enabled": "true",
    "readability_match.ranking_weight": "0.02",
    "readability_match.max_grade_gap": "3",
    "readability_match.penalty_per_grade": "0.10",
    # FR-053 — Passage-Level Relevance Scoring
    # Forward-declared: inert until FR-053 is implemented and reads these keys.
    # Research basis: US9940367B1 — "Scoring candidate answer passages" (Google,
    # 2018). Scores destinations at sub-document granularity by finding the best-
    # matching passage (~200 words) rather than the full page. Passage embeddings
    # stored as a separate int8-quantised FAISS index (~256 MB). Starting weight
    # 0.05 — passage similarity is more precise than full-doc similarity.
    # C++ extension: passagesim.cpp.
    "passage_relevance.enabled": "true",
    "passage_relevance.ranking_weight": "0.05",
    "passage_relevance.passages_per_page": "5",
    "passage_relevance.passage_words": "200",
    "passage_relevance.index_quantised": "true",
    # FR-054 — Boilerplate-to-Content Ratio
    # Forward-declared: inert until FR-054 is implemented and reads these keys.
    # Research basis: US8898296B2 — "Detection of boilerplate content" (Google,
    # 2014). Fraction of destination page that is main content vs. chrome.
    # Penalises destinations where 80%+ is template boilerplate. Computed at
    # crawl time from DOM zone extraction. Starting weight 0.02.
    "boilerplate_ratio.enabled": "true",
    "boilerplate_ratio.ranking_weight": "0.02",
    "boilerplate_ratio.boilerplate_threshold": "0.80",
    "boilerplate_ratio.min_content_chars": "200",
    # FR-055 — Reasonable Surfer Click Probability
    # Forward-declared: inert until FR-055 is implemented and reads these keys.
    # Research basis: US8117209B1 — "Ranking documents based on user behavior
    # and/or feature data" (Google, 2012). Scores each candidate by where the
    # link would appear: body zone, paragraph index, anchor length, emphasis.
    # Links in the body, near the top, with descriptive anchors score highest.
    # Starting weight 0.03.
    "reasonable_surfer.enabled": "true",
    "reasonable_surfer.ranking_weight": "0.03",
    "reasonable_surfer.zone_weight_body": "1.0",
    "reasonable_surfer.zone_weight_sidebar": "0.5",
    "reasonable_surfer.zone_weight_header": "0.3",
    "reasonable_surfer.zone_weight_footer": "0.2",
    "reasonable_surfer.emphasis_boost": "1.2",
    # FR-056 — Long-Click Satisfaction Ratio
    # Forward-declared: inert until FR-056 is implemented and reads these keys.
    # Research basis: US10229166B1 — "Modifying search result ranking based on
    # implicit user feedback" (Google, 2019). Ratio of sessions staying >30 s to
    # sessions bouncing within 10 s on the destination. Laplace-smoothed with
    # alpha=5 for cold pages. Starting weight 0.04 — strong behavioural signal
    # once sufficient GA4 session volume exists.
    "long_click_ratio.enabled": "true",
    "long_click_ratio.ranking_weight": "0.04",
    "long_click_ratio.long_session_seconds": "30",
    "long_click_ratio.short_session_seconds": "10",
    "long_click_ratio.laplace_alpha": "5",
    # FR-057 — Content-Update Magnitude
    # Forward-declared: inert until FR-057 is implemented and reads these keys.
    # Research basis: US8549014B2 — "Document scoring based on document content
    # update" (Google, 2013). Token symmetric-difference ratio between crawls.
    # Catches stale pages with misleading "last modified" timestamps. Starting
    # weight 0.02 — partly overlaps link_freshness; raise after confirming
    # independence on live data.
    "content_update.enabled": "true",
    "content_update.ranking_weight": "0.02",
    "content_update.max_staleness_days": "180",
    # FR-058 — N-gram Writing Quality Prediction
    # Forward-declared: inert until FR-058 is implemented and reads these keys.
    # Research basis: US9767157B2 — "Predicting site quality" (Google/Panda,
    # 2017). Kneser-Ney smoothed n-gram LM (2-to-5-grams) trained on known-good
    # pages; scores destinations by inverse perplexity. Catches auto-generated,
    # spun, or thin content. Starting weight 0.03.
    # C++ extension: ngramqual.cpp.
    "ngram_quality.enabled": "true",
    "ngram_quality.ranking_weight": "0.03",
    "ngram_quality.max_n": "5",
    "ngram_quality.kn_discount": "0.75",
    "ngram_quality.baseline_perplexity": "200.0",
    # FR-059 — Topic Purity Score
    # Forward-declared: inert until FR-059 is implemented and reads these keys.
    # Research basis: US20210004416A1 — "Extracting key phrase candidates and
    # producing topical authority ranking" (Google, 2020). Fraction of sentences
    # in a section whose embeddings exceed cosine-similarity threshold with the
    # section centroid. Sections with >90% on-topic content score highest.
    # Starting weight 0.04.
    "topic_purity.enabled": "true",
    "topic_purity.ranking_weight": "0.04",
    "topic_purity.on_topic_threshold": "0.50",
    "topic_purity.min_sentences": "5",
    # =========================================================================
    # STATISTICAL MODELS & LEARNING-TO-RANK (FR-060 to FR-065)
    # =========================================================================
    # FR-060 — ListNet Listwise Ranking
    # Forward-declared: inert until FR-060 is implemented and reads these keys.
    # Research basis: US7734633B2 — "Listwise Ranking" (Microsoft, 2010).
    # LightGBM model with objective=rank:ndcg trained on editor-approved/rejected
    # lists. Model output replaces composite score at inference — not additive.
    "listnet.enabled": "false",
    "listnet.n_estimators": "200",
    "listnet.num_leaves": "31",
    "listnet.learning_rate": "0.05",
    "listnet.min_training_samples": "500",
    "listnet.model_refresh_days": "30",
    # FR-061 — RankBoost Weight Optimisation (Weights-Only Mode)
    # Forward-declared: inert until FR-061 is implemented and reads these keys.
    # Research basis: US8301638B2 — "Automated Feature Selection Based on
    # RankBoost for Ranking" (Microsoft, 2012). Adjusts signal weights up or down
    # via AdaBoost on pairwise preferences from GSC, Matomo, and GA4 data.
    # NEVER drops a signal — floor weight enforced at min_weight_floor.
    "rankboost.enabled": "false",
    "rankboost.n_rounds": "100",
    "rankboost.learning_rate": "1.0",
    "rankboost.min_weight_floor": "0.01",
    "rankboost.data_sources": "gsc,matomo,ga4",
    "rankboost.retrain_days": "14",
    # FR-062 — Particle Thompson Sampling + Matrix Factorisation (PTS-MF)
    # Forward-declared: inert until FR-062 is implemented and reads these keys.
    # Research basis: US10332015B2 — "Particle Thompson Sampling for Online Matrix
    # Factorization Recommendation" (Adobe, 2019). Rao-Blackwellized particle
    # filter for online Bayesian matrix factorisation. Solves cold-start.
    "pts_mf.enabled": "false",
    "pts_mf.latent_dim": "20",
    "pts_mf.n_particles": "30",
    "pts_mf.prior_variance": "0.1",
    "pts_mf.resample_ess_threshold": "0.5",
    "pts_mf.model_refresh_days": "7",
    # FR-063 — Multi-Hyperplane Ranker Ensemble (MHR)
    # Forward-declared: inert until FR-063 is implemented and reads these keys.
    # Research basis: US8122015B2 — "Multi-Ranker For Search" (Microsoft, 2012).
    # 6 grade-pair SVMs (4 grades) with BordaCount aggregation. Learns that
    # features separating "great from good" differ from "good from bad".
    "mhr.enabled": "false",
    "mhr.n_grades": "4",
    "mhr.svm_c": "1.0",
    "mhr.svm_max_iter": "2000",
    "mhr.retrain_days": "30",
    # FR-064 — Spectral Relational Clustering (SRC)
    # Forward-declared: inert until FR-064 is implemented and reads these keys.
    # Research basis: US8185481B2 — "Spectral Clustering for Multi-Type
    # Relational Data" (SUNY, 2012). Joint Laplacian eigen decomposition on
    # page-anchor and page-query relation matrices.
    "spectral_rc.enabled": "false",
    "spectral_rc.n_clusters": "32",
    "spectral_rc.eigen_dim": "16",
    "spectral_rc.relation_weight_anchor": "0.5",
    "spectral_rc.relation_weight_query": "0.5",
    "spectral_rc.rebuild_days": "14",
    # FR-065 — Isotonic Regression Score Calibration
    # Forward-declared: inert until FR-065 is implemented and reads these keys.
    # Research basis: US9189752B1 — "Interpolating Isotonic Regression for Binary
    # Classification" (Google, 2015). Post-scoring calibration layer mapping raw
    # composite scores to calibrated probabilities via PAV + Delaunay interpolation.
    "isotonic_calibration.enabled": "false",
    "isotonic_calibration.min_training_samples": "200",
    "isotonic_calibration.retrain_days": "7",
    # =========================================================================
    # C++ META-ALGORITHMS (FR-066 to FR-068)
    # =========================================================================
    # FR-066 — SmoothRank: Direct Metric Optimisation (META-01)
    # Forward-declared: inert until FR-066 is implemented and reads these keys.
    # Research basis: US7895198B2 — "Gradient based optimization of a ranking
    # measure" (Yahoo, 2011). Differentiable NDCG approximation via sigmoid-based
    # position smoothing + gradient ascent. C++ ext: smoothrank.cpp.
    "smoothrank.enabled": "false",
    "smoothrank.sigma_init": "1.0",
    "smoothrank.sigma_min": "0.05",
    "smoothrank.sigma_anneal": "0.95",
    "smoothrank.learning_rate": "0.01",
    "smoothrank.n_epochs": "100",
    "smoothrank.retrain_days": "14",
    # FR-067 — Supervised Rank Aggregation via Markov Chains (META-02)
    # Forward-declared: inert until FR-067 is implemented and reads these keys.
    # Research basis: US7840522B2 — "Supervised rank aggregation based on
    # rankings" (Microsoft, Tie-Yan Liu, 2010). Learns per-source mixing weights
    # via SDP-optimised Markov chain stationary distributions. C++ ext: rankagg.cpp.
    "rank_aggregation.enabled": "false",
    "rank_aggregation.sdp_max_iter": "1000",
    "rank_aggregation.sdp_tol": "1e-6",
    "rank_aggregation.power_iter_max": "500",
    "rank_aggregation.power_iter_tol": "1e-6",
    "rank_aggregation.retrain_days": "14",
    # FR-068 — Cascade Telescoping Re-Ranking (META-03)
    # Forward-declared: inert until FR-068 is implemented and reads these keys.
    # Research basis: US7689615B2 — "Ranking results using multiple nested
    # ranking" (Microsoft, 2010). 3-stage cascade: all→200→50→10 via progressively
    # richer feature sets. Reduces compute 3-5x. C++ ext: cascade.cpp.
    "cascade_rerank.enabled": "false",
    "cascade_rerank.stage1_top_n": "200",
    "cascade_rerank.stage2_top_n": "50",
    "cascade_rerank.stage3_top_n": "10",
    "cascade_rerank.net_hidden_size": "32",
    "cascade_rerank.adam_lr": "0.001",
    "cascade_rerank.retrain_days": "14",
    # =========================================================================
    # SOCIAL MEDIA & TECH COMPANY PATENT SIGNALS (FR-069 to FR-090)
    # =========================================================================
    # FR-069 — Viral Propagation Depth
    # Research basis: US10152544B1 (Meta). Max sharing-hop depth before engagement
    # falls below 10% of peak. Computed at index time from GA4 referral chains.
    "viral_depth.enabled": "true",
    "viral_depth.ranking_weight": "0.02",
    "viral_depth.engagement_floor": "0.10",
    "viral_depth.lookback_days": "90",
    # FR-070 — Viral Content Recipient Ranking
    # Research basis: US9323850B1 (Google/YouTube). Scores content by how often
    # shared with high-influence recipients.
    "viral_recipient.enabled": "true",
    "viral_recipient.ranking_weight": "0.02",
    "viral_recipient.lookback_days": "90",
    # FR-071 — Large-Scale Sentiment Score
    # Research basis: US7996210B2 (Google). VADER compound polarity mapped [0,1].
    "sentiment_score.enabled": "true",
    "sentiment_score.ranking_weight": "0.02",
    "sentiment_score.controversy_threshold": "0.60",
    # FR-072 — Trending Content Velocity
    # Research basis: US20150169587A1 (Meta/CrowdTangle). 6-hour engagement
    # acceleration window. Updated every 6 hours.
    "trending_velocity.enabled": "true",
    "trending_velocity.ranking_weight": "0.02",
    "trending_velocity.window_hours": "6",
    "trending_velocity.refresh_hours": "6",
    # FR-073 — Professional Graph Proximity
    # Research basis: US20140244561A1 (LinkedIn). Jaccard of GA4 user-ID sets
    # between source and destination pages.
    "professional_proximity.enabled": "true",
    "professional_proximity.ranking_weight": "0.02",
    "professional_proximity.min_shared_users": "5",
    # FR-074 — Influence Score
    # Research basis: US20140019539A1 (Google). Personalised PageRank on social
    # reshare graph (distinct from link-graph PageRank).
    "influence_score.enabled": "true",
    "influence_score.ranking_weight": "0.02",
    "influence_score.damping": "0.15",
    "influence_score.lookback_days": "90",
    # FR-075 — Watch-Time Completion Rate
    # Research basis: US9098511B1 (Google/YouTube). Ratio of video completions
    # (>85% watched) to total plays, Laplace-smoothed.
    "watch_completion.enabled": "true",
    "watch_completion.ranking_weight": "0.02",
    "watch_completion.completion_threshold": "0.85",
    "watch_completion.laplace_alpha": "1",
    "watch_completion.no_video_default": "0.5",
    # FR-076 — Dwell-Time Interest Profile Match
    # Research basis: US20150127662A1 (Google). Audience attention-span matching
    # via mean session dwell time comparison.
    "dwell_profile_match.enabled": "true",
    "dwell_profile_match.ranking_weight": "0.02",
    "dwell_profile_match.decay_seconds": "60",
    # FR-077 — Geographic Engagement Concentration
    # Research basis: US20080086264A1 (Google). Herfindahl index across country
    # engagement shares. Low HHI = broad global appeal.
    "geo_concentration.enabled": "true",
    "geo_concentration.ranking_weight": "0.02",
    "geo_concentration.lookback_days": "90",
    # FR-078 — Community Upvote Velocity
    # Research basis: US20140244561A1 (Reddit-derived). First-hour upvote rate
    # vs. page's historical median first-hour velocity.
    "upvote_velocity.enabled": "true",
    "upvote_velocity.ranking_weight": "0.02",
    "upvote_velocity.first_hour_window": "1",
    "upvote_velocity.velocity_cap": "5.0",
    # FR-079 — Spam Account Interaction Filter
    # Research basis: WO2013140410A1. Penalises pages where engagement is
    # dominated by flagged/bot accounts.
    "spam_filter.enabled": "true",
    "spam_filter.ranking_weight": "0.02",
    "spam_filter.min_interactions": "10",
    # FR-080 — Content Freshness Decay Rate
    # Research basis: US8832088B1 (Google). Exponential decay fit on weekly
    # engagement. Slow-decay = evergreen, scores higher.
    "freshness_decay_rate.enabled": "true",
    "freshness_decay_rate.ranking_weight": "0.02",
    "freshness_decay_rate.history_weeks": "26",
    # FR-081 — Contextual Sentiment Alignment
    # Research basis: US20150286627A1 (Google). VADER compound comparison between
    # source insertion sentence and destination first paragraph.
    "sentiment_alignment.enabled": "true",
    "sentiment_alignment.ranking_weight": "0.02",
    # FR-082 — Structural Duplicate Detection Score
    # Research basis: US7734627B1 (Google). SimHash of HTML tag sequence; penalise
    # pages structurally similar to many others (template farms).
    "structural_dup.enabled": "true",
    "structural_dup.ranking_weight": "0.02",
    "structural_dup.simhash_bits": "64",
    "structural_dup.similarity_threshold": "0.90",
    # FR-083 — Anomalous Interaction Pattern Filter
    # Research basis: EP3497609B1. Z-score of engagement bursts; penalises one-
    # burst-then-silence artificial inflation patterns.
    "anomaly_filter.enabled": "true",
    "anomaly_filter.ranking_weight": "0.02",
    "anomaly_filter.burst_z_threshold": "3.0",
    # FR-084 — Hashtag Co-occurrence Strength
    # Research basis: US10698945B2 (Snap). PMI between topic tags on source and
    # destination pages.
    "hashtag_cooccurrence.enabled": "true",
    "hashtag_cooccurrence.ranking_weight": "0.02",
    "hashtag_cooccurrence.pmi_smoothing": "0.5",
    # FR-085 — Content Format Preference Signal
    # Research basis: US20190050433A1 (Snap). Format affinity scoring based on
    # GA4 event types (text vs. image vs. video preference).
    "format_preference.enabled": "true",
    "format_preference.ranking_weight": "0.02",
    "format_preference.mismatch_penalty": "0.50",
    # FR-086 — Retweet Graph Authority
    # Research basis: US8370326B2 (Twitter). Personalised PageRank on reshare
    # graph (distinct from link-graph and social influence score FR-074).
    "retweet_authority.enabled": "true",
    "retweet_authority.ranking_weight": "0.02",
    "retweet_authority.damping": "0.15",
    "retweet_authority.lookback_days": "90",
    # FR-087 — Reply Thread Depth Signal
    # Research basis: US8954500B2 (Twitter). Average comment thread depth;
    # deeper threads = genuine discussion.
    "reply_depth.enabled": "true",
    "reply_depth.ranking_weight": "0.02",
    "reply_depth.depth_cap": "5",
    # FR-088 — Save/Bookmark Rate
    # Research basis: US9256680B2 (Pinterest). saves / (views + 10) from GA4
    # bookmark_event / page_view.
    "bookmark_rate.enabled": "true",
    "bookmark_rate.ranking_weight": "0.02",
    "bookmark_rate.laplace_denominator": "10",
    # FR-089 — Visual-Topic Consistency Score
    # Research basis: US20140279220A1 (Pinterest). Cosine similarity between mean
    # image embedding (CLIP-lite, 4-bit CPU) and page text embedding.
    "visual_consistency.enabled": "true",
    "visual_consistency.ranking_weight": "0.02",
    "visual_consistency.no_image_default": "0.5",
    # FR-090 — Cross-Platform Engagement Correlation
    # Research basis: US20140244006A1 (Google). Counts platforms with simultaneous
    # engagement spikes (z > 2.0). Cross-platform resonance = genuine value.
    "cross_platform_engagement.enabled": "true",
    "cross_platform_engagement.ranking_weight": "0.02",
    "cross_platform_engagement.spike_z_threshold": "2.0",
    "cross_platform_engagement.lookback_days": "30",
    # =========================================================================
    # OPERATIONAL FEATURES (FR-091 to FR-096)
    # =========================================================================
    # FR-091 — C++ Extension Retrofit
    # Brings all 12 existing C++ extensions to CPP-RULES.md compliance.
    # Source of truth: backend/extensions/CPP-RULES.md
    # No ranking weight — this is a code quality enforcement feature.
    "cpp_retrofit.enabled": "true",
    "cpp_retrofit.nan_check_enabled": "true",
    "cpp_retrofit.flush_to_zero_enabled": "true",
    "cpp_retrofit.double_accumulator_enabled": "true",
    # FR-092 — Twice-Monthly Graph Walk Refresh
    # Changes graph walk generation from nightly to 1st and 15th of each month.
    # Nightly pipeline reuses cached walk results on non-walk days.
    # Does not change walk parameters — only the schedule.
    "graph_walk_refresh.enabled": "true",
    "graph_walk_refresh.schedule_days": "1,15",
    "graph_walk_refresh.skip_nightly_walks": "true",
    # FR-093 — Extended Nightly Data Retention (Tier 1)
    # Adds 6 tables to the existing nightly retention task.
    "retention_tier1.enabled": "true",
    "retention_tier1.celery_results_days": "7",
    "retention_tier1.resolved_alerts_days": "30",
    "retention_tier1.sync_jobs_days": "60",
    "retention_tier1.analytics_sync_runs_days": "90",
    "retention_tier1.telemetry_coverage_days": "90",
    "retention_tier1.reviewer_scorecards_days": "180",
    # FR-094 — Weekly Analytics Pruning (Tier 2)
    # Prunes GSCDailyPerformance, SuggestionTelemetryDaily, GSCKeywordImpact.
    "retention_tier2.enabled": "true",
    "retention_tier2.gsc_daily_performance_days": "90",
    "retention_tier2.suggestion_telemetry_days": "180",
    "retention_tier2.gsc_keyword_impact_days": "180",
    # FR-095 — Quarterly Database Maintenance (Tier 4)
    # VACUUM FULL, REINDEX CONCURRENTLY, full entity re-extraction.
    "quarterly_maintenance.enabled": "true",
    "quarterly_maintenance.vacuum_full_suggestions": "true",
    "quarterly_maintenance.reindex_embeddings": "true",
    "quarterly_maintenance.rebuild_knowledge_graph": "true",
    # FR-096 — Monthly Safe Prune (Tier 5)
    # Prunes BrokenLink (resolved), ImpactReport, and old diagnostics JSON.
    # Does NOT affect GSC, GA4, Matomo, or auto weight tuning.
    "monthly_safe_prune.enabled": "true",
    "monthly_safe_prune.broken_links_days": "60",
    "monthly_safe_prune.impact_reports_days": "365",
    "monthly_safe_prune.diagnostics_json_days": "90",
}


def recommended_bool(key: str) -> bool:
    return RECOMMENDED_PRESET_WEIGHTS[key].strip().lower() == "true"


def recommended_float(key: str) -> float:
    return float(RECOMMENDED_PRESET_WEIGHTS[key])


def recommended_int(key: str) -> int:
    return int(float(RECOMMENDED_PRESET_WEIGHTS[key]))


def recommended_str(key: str) -> str:
    return RECOMMENDED_PRESET_WEIGHTS[key]
