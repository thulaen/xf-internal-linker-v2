"""Forward-declared preset weights for future feature requests.

These keys are inert until their corresponding FR is implemented and reads
them.  They live in a separate file to keep the main recommended_weights.py
under the file-length limit.

``FORWARD_DECLARED_WEIGHTS`` is merged into ``RECOMMENDED_PRESET_WEIGHTS``
at import time by the main module.
"""

from __future__ import annotations

FORWARD_DECLARED_WEIGHTS: dict[str, str] = {
    # FR-038 — Information Gain Scoring
    # Forward-declared: these keys are inert until FR-038 is implemented and reads them.
    # A new migration (or manual DB update) is needed to push these into the seeded preset.
    # Research basis: US11354342B2. Starting weight is conservative (0.03) because this
    # signal is unvalidated on real content. Run diagnostics first, then raise to 0.05
    # once sample_novel_tokens look sensible across a live pipeline run.
    # C++ extension: refcontext.cpp.
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
    "anchor_diversity.ranking_weight": "0.03",
    "anchor_diversity.min_history_count": "3",
    "anchor_diversity.max_exact_match_share": "0.40",
    "anchor_diversity.max_exact_match_count": "3",
    "anchor_diversity.hard_cap_enabled": "false",
    # FR-046 — Multi-Query Fan-Out for Stage 1 Candidate Retrieval
    "fan_out.enabled": "true",
    "fan_out.max_sub_queries": "3",
    "fan_out.min_segment_words": "50",
    "fan_out.rrf_k": "60",
    # FR-047 — Navigation Path Prediction
    "navigation_path.enabled": "true",
    "navigation_path.ranking_weight": "0.04",
    "navigation_path.lookback_days": "90",
    "navigation_path.min_sessions": "50",
    "navigation_path.min_transition_count": "5",
    "navigation_path.w_direct": "0.6",
    "navigation_path.w_shortcut": "0.4",
    # FR-048 — Topical Authority Cluster Density
    "topical_cluster.enabled": "true",
    "topical_cluster.ranking_weight": "0.04",
    "topical_cluster.min_cluster_size": "5",
    "topical_cluster.min_site_pages": "20",
    "topical_cluster.max_staleness_days": "14",
    "topical_cluster.fallback_value": "0.5",
    # FR-049 — Query Intent Funnel Alignment
    "intent_funnel.enabled": "true",
    "intent_funnel.ranking_weight": "0.03",
    "intent_funnel.optimal_offset": "1",
    "intent_funnel.sigma": "1.2",
    "intent_funnel.min_confidence": "0.25",
    "intent_funnel.navigational_confidence_threshold": "0.6",
    # FR-050 — Seasonality & Temporal Demand Matching
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
    "value_model.co_occurrence.llr_sigmoid_alpha": "0.1",
    "value_model.co_occurrence.llr_sigmoid_beta": "10.0",
    # =====================================================================
    # PATENT-BACKED RANKING SIGNALS (FR-051 to FR-059)
    # =====================================================================
    # FR-051 — Reference Context Scoring
    "reference_context.enabled": "true",
    "reference_context.ranking_weight": "0.03",
    "reference_context.window_tokens": "5",
    "reference_context.idf_smoothing": "1",
    # FR-052 — Readability Level Matching
    "readability_match.enabled": "true",
    "readability_match.ranking_weight": "0.02",
    "readability_match.max_grade_gap": "3",
    "readability_match.penalty_per_grade": "0.10",
    # FR-053 — Passage-Level Relevance Scoring
    "passage_relevance.enabled": "true",
    "passage_relevance.ranking_weight": "0.05",
    "passage_relevance.passages_per_page": "5",
    "passage_relevance.passage_words": "200",
    "passage_relevance.index_quantised": "true",
    # FR-054 — Boilerplate-to-Content Ratio
    "boilerplate_ratio.enabled": "true",
    "boilerplate_ratio.ranking_weight": "0.02",
    "boilerplate_ratio.boilerplate_threshold": "0.80",
    "boilerplate_ratio.min_content_chars": "200",
    # FR-055 — Reasonable Surfer Click Probability
    "reasonable_surfer.enabled": "true",
    "reasonable_surfer.ranking_weight": "0.03",
    "reasonable_surfer.zone_weight_body": "1.0",
    "reasonable_surfer.zone_weight_sidebar": "0.5",
    "reasonable_surfer.zone_weight_header": "0.3",
    "reasonable_surfer.zone_weight_footer": "0.2",
    "reasonable_surfer.emphasis_boost": "1.2",
    # FR-056 — Long-Click Satisfaction Ratio
    "long_click_ratio.enabled": "true",
    "long_click_ratio.ranking_weight": "0.04",
    "long_click_ratio.long_session_seconds": "30",
    "long_click_ratio.short_session_seconds": "10",
    "long_click_ratio.laplace_alpha": "5",
    # FR-057 — Content-Update Magnitude
    "content_update.enabled": "true",
    "content_update.ranking_weight": "0.02",
    "content_update.max_staleness_days": "180",
    # FR-058 — N-gram Writing Quality Prediction
    "ngram_quality.enabled": "true",
    "ngram_quality.ranking_weight": "0.03",
    "ngram_quality.max_n": "5",
    "ngram_quality.kn_discount": "0.75",
    "ngram_quality.baseline_perplexity": "200.0",
    # FR-059 — Topic Purity Score
    "topic_purity.enabled": "true",
    "topic_purity.ranking_weight": "0.04",
    "topic_purity.on_topic_threshold": "0.50",
    "topic_purity.min_sentences": "5",
    # =====================================================================
    # STATISTICAL MODELS & LEARNING-TO-RANK (FR-060 to FR-065)
    # =====================================================================
    # FR-060 — ListNet Listwise Ranking
    "listnet.enabled": "false",
    "listnet.n_estimators": "200",
    "listnet.num_leaves": "31",
    "listnet.learning_rate": "0.05",
    "listnet.min_training_samples": "500",
    "listnet.model_refresh_days": "30",
    # FR-061 — RankBoost Weight Optimisation (Weights-Only Mode)
    "rankboost.enabled": "false",
    "rankboost.n_rounds": "100",
    "rankboost.learning_rate": "1.0",
    "rankboost.min_weight_floor": "0.01",
    "rankboost.data_sources": "gsc,matomo,ga4",
    "rankboost.retrain_days": "14",
    # FR-062 — Particle Thompson Sampling + Matrix Factorisation (PTS-MF)
    "pts_mf.enabled": "false",
    "pts_mf.latent_dim": "20",
    "pts_mf.n_particles": "30",
    "pts_mf.prior_variance": "0.1",
    "pts_mf.resample_ess_threshold": "0.5",
    "pts_mf.model_refresh_days": "7",
    # FR-063 — Multi-Hyperplane Ranker Ensemble (MHR)
    "mhr.enabled": "false",
    "mhr.n_grades": "4",
    "mhr.svm_c": "1.0",
    "mhr.svm_max_iter": "2000",
    "mhr.retrain_days": "30",
    # FR-064 — Spectral Relational Clustering (SRC)
    "spectral_rc.enabled": "false",
    "spectral_rc.n_clusters": "32",
    "spectral_rc.eigen_dim": "16",
    "spectral_rc.relation_weight_anchor": "0.5",
    "spectral_rc.relation_weight_query": "0.5",
    "spectral_rc.rebuild_days": "14",
    # FR-065 — Isotonic Regression Score Calibration
    "isotonic_calibration.enabled": "false",
    "isotonic_calibration.min_training_samples": "200",
    "isotonic_calibration.retrain_days": "7",
    # =====================================================================
    # C++ META-ALGORITHMS (FR-066 to FR-068)
    # =====================================================================
    # FR-066 — SmoothRank: Direct Metric Optimisation (META-01)
    "smoothrank.enabled": "false",
    "smoothrank.sigma_init": "1.0",
    "smoothrank.sigma_min": "0.05",
    "smoothrank.sigma_anneal": "0.95",
    "smoothrank.learning_rate": "0.01",
    "smoothrank.n_epochs": "100",
    "smoothrank.retrain_days": "14",
    # FR-067 — Supervised Rank Aggregation via Markov Chains (META-02)
    "rank_aggregation.enabled": "false",
    "rank_aggregation.sdp_max_iter": "1000",
    "rank_aggregation.sdp_tol": "1e-6",
    "rank_aggregation.power_iter_max": "500",
    "rank_aggregation.power_iter_tol": "1e-6",
    "rank_aggregation.retrain_days": "14",
    # FR-068 — Cascade Telescoping Re-Ranking (META-03)
    "cascade_rerank.enabled": "false",
    "cascade_rerank.stage1_top_n": "200",
    "cascade_rerank.stage2_top_n": "50",
    "cascade_rerank.stage3_top_n": "10",
    "cascade_rerank.net_hidden_size": "32",
    "cascade_rerank.adam_lr": "0.001",
    "cascade_rerank.retrain_days": "14",
    # =====================================================================
    # SOCIAL MEDIA & TECH COMPANY PATENT SIGNALS (FR-069 to FR-090)
    # =====================================================================
    # FR-069 — Viral Propagation Depth
    "viral_depth.enabled": "true",
    "viral_depth.ranking_weight": "0.02",
    "viral_depth.engagement_floor": "0.10",
    "viral_depth.lookback_days": "90",
    # FR-070 — Viral Content Recipient Ranking
    "viral_recipient.enabled": "true",
    "viral_recipient.ranking_weight": "0.02",
    "viral_recipient.lookback_days": "90",
    # FR-071 — Large-Scale Sentiment Score
    "sentiment_score.enabled": "true",
    "sentiment_score.ranking_weight": "0.02",
    "sentiment_score.controversy_threshold": "0.60",
    # FR-072 — Trending Content Velocity
    "trending_velocity.enabled": "true",
    "trending_velocity.ranking_weight": "0.02",
    "trending_velocity.window_hours": "6",
    "trending_velocity.refresh_hours": "6",
    # FR-073 — Professional Graph Proximity
    "professional_proximity.enabled": "true",
    "professional_proximity.ranking_weight": "0.02",
    "professional_proximity.min_shared_users": "5",
    # FR-074 — Influence Score
    "influence_score.enabled": "true",
    "influence_score.ranking_weight": "0.02",
    "influence_score.damping": "0.15",
    "influence_score.lookback_days": "90",
    # FR-075 — Watch-Time Completion Rate
    "watch_completion.enabled": "true",
    "watch_completion.ranking_weight": "0.02",
    "watch_completion.completion_threshold": "0.85",
    "watch_completion.laplace_alpha": "1",
    "watch_completion.no_video_default": "0.5",
    # FR-076 — Dwell-Time Interest Profile Match
    "dwell_profile_match.enabled": "true",
    "dwell_profile_match.ranking_weight": "0.02",
    "dwell_profile_match.decay_seconds": "60",
    # FR-077 — Geographic Engagement Concentration
    "geo_concentration.enabled": "true",
    "geo_concentration.ranking_weight": "0.02",
    "geo_concentration.lookback_days": "90",
    # FR-078 — Community Upvote Velocity
    "upvote_velocity.enabled": "true",
    "upvote_velocity.ranking_weight": "0.02",
    "upvote_velocity.first_hour_window": "1",
    "upvote_velocity.velocity_cap": "5.0",
    # FR-079 — Spam Account Interaction Filter
    "spam_filter.enabled": "true",
    "spam_filter.ranking_weight": "0.02",
    "spam_filter.min_interactions": "10",
    # FR-080 — Content Freshness Decay Rate
    "freshness_decay_rate.enabled": "true",
    "freshness_decay_rate.ranking_weight": "0.02",
    "freshness_decay_rate.history_weeks": "26",
    # FR-081 — Contextual Sentiment Alignment
    "sentiment_alignment.enabled": "true",
    "sentiment_alignment.ranking_weight": "0.02",
    # FR-082 — Structural Duplicate Detection Score
    "structural_dup.enabled": "true",
    "structural_dup.ranking_weight": "0.02",
    "structural_dup.simhash_bits": "64",
    "structural_dup.similarity_threshold": "0.90",
    # FR-083 — Anomalous Interaction Pattern Filter
    "anomaly_filter.enabled": "true",
    "anomaly_filter.ranking_weight": "0.02",
    "anomaly_filter.burst_z_threshold": "3.0",
    # FR-084 — Hashtag Co-occurrence Strength
    "hashtag_cooccurrence.enabled": "true",
    "hashtag_cooccurrence.ranking_weight": "0.02",
    "hashtag_cooccurrence.pmi_smoothing": "0.5",
    # FR-085 — Content Format Preference Signal
    "format_preference.enabled": "true",
    "format_preference.ranking_weight": "0.02",
    "format_preference.mismatch_penalty": "0.50",
    # FR-086 — Retweet Graph Authority
    "retweet_authority.enabled": "true",
    "retweet_authority.ranking_weight": "0.02",
    "retweet_authority.damping": "0.15",
    "retweet_authority.lookback_days": "90",
    # FR-087 — Reply Thread Depth Signal
    "reply_depth.enabled": "true",
    "reply_depth.ranking_weight": "0.02",
    "reply_depth.depth_cap": "5",
    # FR-088 — Save/Bookmark Rate
    "bookmark_rate.enabled": "true",
    "bookmark_rate.ranking_weight": "0.02",
    "bookmark_rate.laplace_denominator": "10",
    # FR-089 — Visual-Topic Consistency Score
    "visual_consistency.enabled": "true",
    "visual_consistency.ranking_weight": "0.02",
    "visual_consistency.no_image_default": "0.5",
    # FR-090 — Cross-Platform Engagement Correlation
    "cross_platform_engagement.enabled": "true",
    "cross_platform_engagement.ranking_weight": "0.02",
    "cross_platform_engagement.spike_z_threshold": "2.0",
    "cross_platform_engagement.lookback_days": "30",
    # =====================================================================
    # OPERATIONAL FEATURES (FR-091 to FR-096)
    # =====================================================================
    # FR-091 — C++ Extension Retrofit
    "cpp_retrofit.enabled": "true",
    "cpp_retrofit.nan_check_enabled": "true",
    "cpp_retrofit.flush_to_zero_enabled": "true",
    "cpp_retrofit.double_accumulator_enabled": "true",
    # FR-092 — Twice-Monthly Graph Walk Refresh
    "graph_walk_refresh.enabled": "true",
    "graph_walk_refresh.schedule_days": "1,15",
    "graph_walk_refresh.skip_nightly_walks": "true",
    # FR-093 — Extended Nightly Data Retention (Tier 1)
    "retention_tier1.enabled": "true",
    "retention_tier1.celery_results_days": "7",
    "retention_tier1.resolved_alerts_days": "30",
    "retention_tier1.sync_jobs_days": "60",
    "retention_tier1.analytics_sync_runs_days": "90",
    "retention_tier1.telemetry_coverage_days": "90",
    "retention_tier1.reviewer_scorecards_days": "180",
    # FR-094 — Weekly Analytics Pruning (Tier 2)
    "retention_tier2.enabled": "true",
    "retention_tier2.gsc_daily_performance_days": "90",
    "retention_tier2.suggestion_telemetry_days": "180",
    "retention_tier2.gsc_keyword_impact_days": "180",
    # FR-095 — Quarterly Database Maintenance (Tier 4)
    "quarterly_maintenance.enabled": "true",
    "quarterly_maintenance.vacuum_full_suggestions": "true",
    "quarterly_maintenance.reindex_embeddings": "true",
    "quarterly_maintenance.rebuild_knowledge_graph": "true",
    # FR-096 — Monthly Safe Prune (Tier 5)
    "monthly_safe_prune.enabled": "true",
    "monthly_safe_prune.broken_links_days": "60",
    "monthly_safe_prune.impact_reports_days": "365",
    "monthly_safe_prune.diagnostics_json_days": "90",
}
