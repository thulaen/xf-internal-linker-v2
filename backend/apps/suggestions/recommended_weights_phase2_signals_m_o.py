"""Forward-declared Phase 2 ranking-signal weights — Blocks M through O."""
# Covers 21 ranking signals across:
#   - Block M: Author / poster reputation (FR-204..FR-212, 9 FRs)
#   - Block N: Structural HTML / page-quality / Core Web Vitals (FR-213..FR-220, 8 FRs)
#   - Block O: Passage segmentation (FR-221..FR-224, 4 FRs)
#
# Each entry has a researched starting ranking_weight plus all algorithm-
# specific hyperparameters lifted verbatim from each spec's "Starting weight
# preset" section. Specs themselves declare ranking_weight as 0.0 (inert
# placeholder); per project rules every signal must ship with a real
# starting weight (0.02-0.05 band), so this module overrides the spec 0.0
# with a conservative live value. Auto-tuner adjusts once C++ is wired
# and live diagnostics are observed.
#
# Key prefixes match each spec's canonical preset (e.g. eigentrust, rqr,
# alt_text_coverage), not the working slug used in the FR docket.

from __future__ import annotations

FORWARD_DECLARED_WEIGHTS_PHASE2_SIGNALS_M_O: dict[str, str] = {
    # =====================================================================
    # BLOCK M — Author / poster reputation (FR-204..FR-212)
    # =====================================================================
    # FR-204 — Author H-Index Within Forum
    # Spec prefix: author_h_index. Spec ranking_weight 0.0 overridden to
    # 0.03 (mid-band) — h-index is a well-established bibliometric signal,
    # but on a forum it relies on stable upvote semantics; conservative
    # until live distribution is profiled.
    "author_h_index.enabled": "true",
    "author_h_index.ranking_weight": "0.03",
    "author_h_index.use_time_decay": "true",
    "author_h_index.alpha_decay": "0.005",
    "author_h_index.h_norm": "50",
    "author_h_index.metric": "upvotes",
    # FR-205 — Co-Authorship Graph PageRank
    # Spec prefix: co_authorship_pr. Spec ranking_weight 0.0 overridden to
    # 0.03 — graph-walk authority is sensitive to community structure,
    # mid-band start lets reranker calibrate against direct h-index.
    "co_authorship_pr.enabled": "true",
    "co_authorship_pr.ranking_weight": "0.03",
    "co_authorship_pr.damping": "0.85",
    "co_authorship_pr.tolerance": "1e-6",
    "co_authorship_pr.max_iters": "100",
    "co_authorship_pr.min_post_depth": "1",
    "co_authorship_pr.rebuild_cadence_hours": "24",
    # FR-206 — Account Age Gravity
    # Spec prefix: account_age_gravity. Spec ranking_weight 0.0 overridden
    # to 0.02 — age gravity is a soft prior; small weight prevents over-
    # rewarding tenure relative to actual content quality.
    "account_age_gravity.enabled": "true",
    "account_age_gravity.ranking_weight": "0.02",
    "account_age_gravity.tau_days": "90.0",
    "account_age_gravity.first_post_gate_days": "7",
    "account_age_gravity.use_first_post_gate": "true",
    # FR-207 — Edit History Density
    # Spec prefix: edit_history_density. Spec ranking_weight 0.0 overridden
    # to 0.03 — edit cadence with revert penalty is a meaningful quality
    # proxy; survival weighting needs live tuning so start mid-band.
    "edit_history_density.enabled": "true",
    "edit_history_density.ranking_weight": "0.03",
    "edit_history_density.epsilon": "1.0",
    "edit_history_density.gamma_revert": "0.50",
    "edit_history_density.use_survival_weighting": "true",
    "edit_history_density.lambda_sigmoid": "1.5",
    "edit_history_density.mu_decision": "0.30",
    "edit_history_density.survival_followup_T": "10",
    "edit_history_density.survival_window_days": "30",
    # FR-208 — Moderator Endorsement Signal
    # Spec prefix: mod_endorsement. Spec ranking_weight 0.0 overridden to
    # 0.04 — explicit human moderator endorsement is the most trustworthy
    # signal in this block; small extra weight reflects that.
    "mod_endorsement.enabled": "true",
    "mod_endorsement.ranking_weight": "0.04",
    "mod_endorsement.weight_pin": "1.0",
    "mod_endorsement.weight_best_answer": "0.8",
    "mod_endorsement.weight_mod_quote": "0.5",
    "mod_endorsement.weight_mod_react": "0.3",
    "mod_endorsement.beta_decay": "0.005",
    "mod_endorsement.endorse_norm": "10.0",
    "mod_endorsement.use_time_decay": "true",
    # FR-209 — Reply Quality to Post Ratio
    # Spec prefix: rqr. Spec ranking_weight 0.0 overridden to 0.03 —
    # Wilson-bounded ratios are statistically reliable; mid-band is safe.
    "rqr.enabled": "true",
    "rqr.ranking_weight": "0.03",
    "rqr.use_wilson_bound": "true",
    "rqr.wilson_z": "1.96",
    "rqr.positive_threshold_likes": "1",
    "rqr.positive_threshold_thanks": "1",
    # FR-210 — Cross-Thread Topic Consistency
    # Spec prefix: topic_consistency. Spec ranking_weight 0.0 overridden
    # to 0.03 — LDA expertise gating is sensitive to topic count and
    # corpus drift, so a moderate weight pending live tuning.
    "topic_consistency.enabled": "true",
    "topic_consistency.ranking_weight": "0.03",
    "topic_consistency.lda_topic_count": "100",
    "topic_consistency.tau_expertise": "0.10",
    "topic_consistency.dirichlet_alpha": "0.10",
    "topic_consistency.lda_passes": "20",
    "topic_consistency.smoothing_eps": "1e-9",
    # FR-211 — Trust Propagation User Graph
    # Spec prefix: trust_propagation. Spec ranking_weight 0.0 overridden
    # to 0.03 — propagated trust complements direct mod endorsement; mid-
    # band keeps the two reputation streams balanced.
    "trust_propagation.enabled": "true",
    "trust_propagation.ranking_weight": "0.03",
    "trust_propagation.alpha_direct": "0.40",
    "trust_propagation.alpha_cocitation": "0.40",
    "trust_propagation.alpha_transpose": "0.10",
    "trust_propagation.alpha_coupling": "0.10",
    "trust_propagation.k_steps": "4",
    "trust_propagation.gamma_distrust": "0.50",
    "trust_propagation.seed_size": "32",
    # FR-212 — User EigenTrust
    # Spec prefix: eigentrust. Spec ranking_weight 0.0 overridden to 0.03
    # — Kamvar EigenTrust is mathematically sound but seed-set sensitive;
    # mid-band start, raise after seed-set audit.
    "eigentrust.enabled": "true",
    "eigentrust.ranking_weight": "0.03",
    "eigentrust.anchor_a": "0.10",
    "eigentrust.tolerance": "1e-6",
    "eigentrust.max_iters": "100",
    "eigentrust.pretrusted_top_n_h_authors": "20",
    "eigentrust.pretrusted_include_all_mods": "true",
    "eigentrust.rebuild_cadence_hours": "24",
    # =====================================================================
    # BLOCK N — Structural HTML / page-quality / Core Web Vitals
    # (FR-213..FR-220)
    # =====================================================================
    # FR-213 — Heading Hierarchy Correctness
    # Spec prefix: heading_hierarchy. Spec ranking_weight 0.0 overridden
    # to 0.02 — outline correctness is a small accessibility/SEO prior;
    # low weight is appropriate.
    "heading_hierarchy.enabled": "true",
    "heading_hierarchy.ranking_weight": "0.02",
    "heading_hierarchy.exclude_zones": "header,footer,nav,aside",
    "heading_hierarchy.min_headings": "3",
    # FR-214 — Alt-Text Coverage Ratio
    # Spec prefix: alt_text_coverage. Spec ranking_weight 0.0 overridden
    # to 0.02 — page-quality prior similar to heading hierarchy.
    "alt_text_coverage.enabled": "true",
    "alt_text_coverage.ranking_weight": "0.02",
    "alt_text_coverage.min_images": "2",
    "alt_text_coverage.exclude_decorative": "true",
    "alt_text_coverage.min_alt_chars": "2",
    # FR-215 — Schema.org Completeness
    # Spec prefix: schema_completeness. Spec ranking_weight 0.0 overridden
    # to 0.02 — structured-data signal is meaningful for rich-result
    # candidates; small weight to start.
    "schema_completeness.enabled": "true",
    "schema_completeness.ranking_weight": "0.02",
    "schema_completeness.min_items": "1",
    "schema_completeness.recurse_nested": "true",
    "schema_completeness.spec_version": "28.0",
    # FR-216 — Open Graph Completeness
    # Spec prefix: open_graph_completeness. Spec ranking_weight 0.0
    # overridden to 0.02 — OG completeness mostly affects social
    # shareability; small weight is sufficient.
    "open_graph_completeness.enabled": "true",
    "open_graph_completeness.ranking_weight": "0.02",
    "open_graph_completeness.required_weight": "0.85",
    "open_graph_completeness.supplementary_weight": "0.15",
    # validate_image_fetch keeps optional network call disabled by default
    "open_graph_completeness.validate_image_fetch": "false",
    # FR-217 — Mobile-Friendly Score
    # Spec prefix: mobile_friendly. Spec ranking_weight 0.0 overridden to
    # 0.03 — mobile-friendliness is a Google ranking factor; mid-band.
    "mobile_friendly.enabled": "true",
    "mobile_friendly.ranking_weight": "0.03",
    "mobile_friendly.weight_viewport": "0.30",
    "mobile_friendly.weight_font": "0.20",
    "mobile_friendly.weight_no_hscroll": "0.20",
    "mobile_friendly.weight_touch": "0.20",
    "mobile_friendly.weight_no_plugin": "0.10",
    "mobile_friendly.min_touch_target_px": "48",
    "mobile_friendly.min_font_px": "16",
    "mobile_friendly.touch_pass_ratio": "0.90",
    # FR-218 — Core Web Vital LCP
    # Spec prefix: cwv_lcp. Spec ranking_weight 0.0 overridden to 0.03 —
    # CWV is an established Google ranking factor; mid-band per signal.
    "cwv_lcp.enabled": "true",
    "cwv_lcp.ranking_weight": "0.03",
    "cwv_lcp.good_ms": "2500",
    "cwv_lcp.poor_ms": "4000",
    # aggregate is one of mean | p75 | p95
    "cwv_lcp.aggregate": "p75",
    "cwv_lcp.min_samples": "5",
    # FR-219 — Core Web Vital CLS
    # Spec prefix: cwv_cls. Spec ranking_weight 0.0 overridden to 0.03 —
    # parallels FR-218 weighting.
    "cwv_cls.enabled": "true",
    "cwv_cls.ranking_weight": "0.03",
    "cwv_cls.good": "0.10",
    "cwv_cls.poor": "0.25",
    "cwv_cls.session_window_ms": "5000",
    "cwv_cls.session_gap_ms": "1000",
    "cwv_cls.aggregate": "p75",
    "cwv_cls.min_samples": "5",
    # FR-220 — Core Web Vital INP
    # Spec prefix: cwv_inp. Spec ranking_weight 0.0 overridden to 0.03 —
    # parallels FR-218 / FR-219 weighting.
    "cwv_inp.enabled": "true",
    "cwv_inp.ranking_weight": "0.03",
    "cwv_inp.good_ms": "200",
    "cwv_inp.poor_ms": "500",
    "cwv_inp.percentile": "0.98",
    "cwv_inp.high_interaction_threshold": "50",
    "cwv_inp.min_interactions": "1",
    # =====================================================================
    # BLOCK O — Passage segmentation (FR-221..FR-224)
    # =====================================================================
    # FR-221 — Passage TextTiling Boundary Strength
    # Spec prefix: texttiling. Spec ranking_weight 0.0 overridden to 0.04
    # — Hearst TextTiling is well-validated; passage signals materially
    # improve insertion-point relevance, slightly higher band than block-N.
    "texttiling.enabled": "true",
    "texttiling.ranking_weight": "0.04",
    "texttiling.block_size_tokens": "20",
    "texttiling.smoothing_window": "2",
    "texttiling.threshold_c": "0.5",
    "texttiling.min_blocks": "6",
    # FR-222 — C99 Passage Segmentation
    # Spec prefix: c99_segmentation. Spec ranking_weight 0.0 overridden
    # to 0.04 — C99 (Choi 2000) complements TextTiling, similar weight.
    "c99_segmentation.enabled": "true",
    "c99_segmentation.ranking_weight": "0.04",
    "c99_segmentation.rank_neighbourhood": "11",
    "c99_segmentation.stop_threshold_c": "1.2",
    "c99_segmentation.min_sentences": "8",
    # FR-223 — Dotplotting Topic Boundary
    # Spec prefix: dotplot_segmentation. Spec ranking_weight 0.0
    # overridden to 0.04 — Reynar dotplotting fills out the segmentation
    # ensemble; same band as siblings.
    "dotplot_segmentation.enabled": "true",
    "dotplot_segmentation.ranking_weight": "0.04",
    # binarize_threshold uses mean(M) when "auto"
    "dotplot_segmentation.binarize_threshold": "auto",
    "dotplot_segmentation.window_w": "5",
    "dotplot_segmentation.boundary_c": "0.5",
    "dotplot_segmentation.min_sentences": "10",
    # FR-224 — BayesSeg Bayesian Segmentation
    # Spec prefix: bayesseg. Spec ranking_weight 0.0 overridden to 0.04 —
    # BayesSeg (Eisenstein & Barzilay 2008) is the most principled of the
    # four segmenters; same band, ensemble effects expected.
    "bayesseg.enabled": "true",
    "bayesseg.ranking_weight": "0.04",
    "bayesseg.dirichlet_alpha": "0.5",
    # mdl_lambda auto-resolves to log(n_tokens) when "log_n"
    "bayesseg.mdl_lambda": "log_n",
    "bayesseg.min_tokens": "200",
    "bayesseg.max_segments": "50",
    "bayesseg.zscore_shape": "0.25",
}
