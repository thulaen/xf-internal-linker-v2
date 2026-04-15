"""Forward-declared preset weights for Phase 2 feature requests.

These keys are inert until their corresponding FR/META is implemented and
reads them. They live in a separate file to keep the main recommended_weights.py
and recommended_weights_forward_settings.py under their file-length limits.

``FORWARD_DECLARED_WEIGHTS_PHASE2`` is merged into ``RECOMMENDED_PRESET_WEIGHTS``
at import time by the main module.

All FR-099..FR-224 keys use ``.enabled="true"`` and ``.ranking_weight="0.0"``.
All META-40..META-249 keys use ``.enabled="false"`` (metas stay off until an
operator selects one).

Source specs: docs/specs/fr099-*.md through docs/specs/fr224-*.md
               docs/specs/meta-40-*.md through docs/specs/meta-249-*.md
"""

from __future__ import annotations

FORWARD_DECLARED_WEIGHTS_PHASE2: dict[str, str] = {
    # =====================================================================
    # Block A — Classical IR scoring models (FR-099 .. FR-107)
    # =====================================================================
    # FR-099 — BM25+ Lower-Bound Term-Frequency Normalization
    "bm25_plus.enabled": "true",
    "bm25_plus.ranking_weight": "0.0",
    # FR-100 — BM25L Length-Unbiased Term Weighting
    "bm25l.enabled": "true",
    "bm25l.ranking_weight": "0.0",
    # FR-101 — DFR PL2 (Divergence From Randomness, Poisson + Laplace)
    "dfr_pl2.enabled": "true",
    "dfr_pl2.ranking_weight": "0.0",
    # FR-102 — DFR InL2 (Inverse Document Frequency + Laplace Aftereffect)
    "dfr_inl2.enabled": "true",
    "dfr_inl2.ranking_weight": "0.0",
    # FR-103 — DFR DPH (Parameter-Free Divergence From Randomness)
    "dfr_dph.enabled": "true",
    "dfr_dph.ranking_weight": "0.0",
    # FR-104 — Axiomatic F2-EXP Retrieval Function
    "axiomatic_f2exp.enabled": "true",
    "axiomatic_f2exp.ranking_weight": "0.0",
    # FR-105 — Two-Stage Language Model (Zhai & Lafferty)
    "two_stage_lm.enabled": "true",
    "two_stage_lm.ranking_weight": "0.0",
    # FR-106 — Positional Language Model
    "positional_lm.enabled": "true",
    "positional_lm.ranking_weight": "0.0",
    # FR-107 — Relevance Model RM3 (Pseudo-Relevance Feedback)
    "rm3.enabled": "true",
    "rm3.ranking_weight": "0.0",
    # =====================================================================
    # Block B — Proximity and dependence models (FR-108 .. FR-115)
    # =====================================================================
    # FR-108 — Sequential Dependence Model (SDM, Metzler & Croft)
    "sdm.enabled": "true",
    "sdm.ranking_weight": "0.0",
    # FR-109 — Weighted Sequential Dependence Model (WSDM)
    "wsdm_weighted.enabled": "true",
    "wsdm_weighted.ranking_weight": "0.0",
    # FR-110 — Full Dependence Model (FDM)
    "fdm.enabled": "true",
    "fdm.ranking_weight": "0.0",
    # FR-111 — BM25TP Term-Proximity Extension
    "bm25tp.enabled": "true",
    "bm25tp.ranking_weight": "0.0",
    # FR-112 — Minimum-Span Proximity Score
    "minspan_prox.enabled": "true",
    "minspan_prox.ranking_weight": "0.0",
    # FR-113 — Ordered-Span Proximity Score
    "ordered_span_prox.enabled": "true",
    "ordered_span_prox.ranking_weight": "0.0",
    # FR-114 — BoolProx Boolean-with-Proximity Ranking
    "boolprox.enabled": "true",
    "boolprox.ranking_weight": "0.0",
    # FR-115 — Markov Random Field Per-Field Retrieval
    "mrf_per_field.enabled": "true",
    "mrf_per_field.ranking_weight": "0.0",
    # =====================================================================
    # Block C — Graph authority and centrality (FR-116 .. FR-125)
    # =====================================================================
    # FR-116 — HITS Authority Score
    "hits_authority.enabled": "true",
    "hits_authority.ranking_weight": "0.0",
    # FR-117 — HITS Hub Score
    "hits_hub.enabled": "true",
    "hits_hub.ranking_weight": "0.0",
    # FR-118 — TrustRank Propagation
    "trustrank.enabled": "true",
    "trustrank.ranking_weight": "0.0",
    # FR-119 — Anti-TrustRank (inverse propagation)
    "anti_trustrank.enabled": "true",
    "anti_trustrank.ranking_weight": "0.0",
    # FR-120 — SALSA Stochastic Approach to Link-Structure Analysis
    "salsa.enabled": "true",
    "salsa.ranking_weight": "0.0",
    # FR-121 — SimRank Structural Similarity
    "simrank.enabled": "true",
    "simrank.ranking_weight": "0.0",
    # FR-122 — Katz Centrality
    "katz.enabled": "true",
    "katz.ranking_weight": "0.0",
    # FR-123 — K-Shell Coreness
    "kshell.enabled": "true",
    "kshell.ranking_weight": "0.0",
    # FR-124 — Harmonic Centrality
    "harmonic.enabled": "true",
    "harmonic.ranking_weight": "0.0",
    # FR-125 — LeaderRank
    "leaderrank.enabled": "true",
    "leaderrank.ranking_weight": "0.0",
    # =====================================================================
    # Block D — Result diversification (FR-126 .. FR-133)
    # =====================================================================
    # FR-126 — IA-Select Intent-Aware Diversification
    "ia_select.enabled": "true",
    "ia_select.ranking_weight": "0.0",
    # FR-127 — xQuAD Aspect Diversification
    "xquad.enabled": "true",
    "xquad.ranking_weight": "0.0",
    # FR-128 — PM-2 Proportional Diversification
    "pm2.enabled": "true",
    "pm2.ranking_weight": "0.0",
    # FR-129 — Determinantal Point Process Reranking
    "dpp.enabled": "true",
    "dpp.ranking_weight": "0.0",
    # FR-130 — Submodular Coverage Reranking
    "submod_cov.enabled": "true",
    "submod_cov.ranking_weight": "0.0",
    # FR-131 — Portfolio Theory Reranking
    "portfolio.enabled": "true",
    "portfolio.ranking_weight": "0.0",
    # FR-132 — Latent Diversity Model
    "ldm.enabled": "true",
    "ldm.ranking_weight": "0.0",
    # FR-133 — Quota-Based Diversity
    "quota_div.enabled": "true",
    "quota_div.ranking_weight": "0.0",
    # =====================================================================
    # Block E — Time-series / trend / change detection (FR-134 .. FR-143)
    # =====================================================================
    # FR-134 — Kleinberg Burst Detection
    "kleinberg_burst.enabled": "true",
    "kleinberg_burst.ranking_weight": "0.0",
    # FR-135 — PELT Change-Point Detection
    "pelt_changepoint.enabled": "true",
    "pelt_changepoint.ranking_weight": "0.0",
    # FR-136 — CUSUM Cumulative Anomaly
    "cusum.enabled": "true",
    "cusum.ranking_weight": "0.0",
    # FR-137 — STL Seasonal-Trend Decomposition
    "stl_decomposition.enabled": "true",
    "stl_decomposition.ranking_weight": "0.0",
    # FR-138 — Mann-Kendall Nonparametric Trend Test
    "mann_kendall.enabled": "true",
    "mann_kendall.ranking_weight": "0.0",
    # FR-139 — Theil-Sen Robust Slope Estimator
    "theil_sen.enabled": "true",
    "theil_sen.ranking_weight": "0.0",
    # FR-140 — Fourier Periodicity Strength
    "fourier_periodicity.enabled": "true",
    "fourier_periodicity.ranking_weight": "0.0",
    # FR-141 — Autocorrelation Lag-k Signal
    "autocorrelation.enabled": "true",
    "autocorrelation.ranking_weight": "0.0",
    # FR-142 — Partial Autocorrelation Signal
    "partial_autocorrelation.enabled": "true",
    "partial_autocorrelation.ranking_weight": "0.0",
    # FR-143 — EWMA Smoothed Click Rate
    "ewma_click.enabled": "true",
    "ewma_click.ranking_weight": "0.0",
    # =====================================================================
    # Block F — Streaming sketches and approximate counting (FR-144 .. FR-151)
    # =====================================================================
    # FR-144 — HyperLogLog Unique Visitors
    "hyperloglog.enabled": "true",
    "hyperloglog.ranking_weight": "0.0",
    # FR-145 — HyperLogLog++ Visitor Estimator
    "hyperloglog_plus.enabled": "true",
    "hyperloglog_plus.ranking_weight": "0.0",
    # FR-146 — Count-Min Sketch Anchor Rarity
    "countmin_sketch.enabled": "true",
    "countmin_sketch.ranking_weight": "0.0",
    # FR-147 — Count Sketch Signed Frequency
    "count_sketch.enabled": "true",
    "count_sketch.ranking_weight": "0.0",
    # FR-148 — Space-Saving Top-K Anchors
    "space_saving.enabled": "true",
    "space_saving.ranking_weight": "0.0",
    # FR-149 — t-Digest Quantile Tracker
    "t_digest.enabled": "true",
    "t_digest.ranking_weight": "0.0",
    # FR-150 — Lossy Counting Frequency
    "lossy_counting.enabled": "true",
    "lossy_counting.ranking_weight": "0.0",
    # FR-151 — b-Bit MinHash Similarity
    "b_bit_minhash.enabled": "true",
    "b_bit_minhash.ranking_weight": "0.0",
    # =====================================================================
    # Block G — Linguistic and stylistic quality (FR-152 .. FR-161)
    # =====================================================================
    # FR-152 — Passive Voice Ratio
    "passive_voice.enabled": "true",
    "passive_voice.ranking_weight": "0.0",
    # FR-153 — Nominalization Density
    "nominalization.enabled": "true",
    "nominalization.ranking_weight": "0.0",
    # FR-154 — Hedging Language Density
    "hedging.enabled": "true",
    "hedging.ranking_weight": "0.0",
    # FR-155 — Discourse Connective Density
    "discourse_connective.enabled": "true",
    "discourse_connective.ranking_weight": "0.0",
    # FR-156 — Coh-Metrix Cohesion Score
    "cohesion.enabled": "true",
    "cohesion.ranking_weight": "0.0",
    # FR-157 — Part-of-Speech Diversity
    "pos_diversity.enabled": "true",
    "pos_diversity.ranking_weight": "0.0",
    # FR-158 — Sentence Length Variance
    "sentence_variance.enabled": "true",
    "sentence_variance.ranking_weight": "0.0",
    # FR-159 — Yule-K Lexical Concentration
    "yule_k.enabled": "true",
    "yule_k.ranking_weight": "0.0",
    # FR-160 — MTLD Lexical Diversity
    "mtld.enabled": "true",
    "mtld.ranking_weight": "0.0",
    # FR-161 — Punctuation Entropy
    "punctuation_entropy.enabled": "true",
    "punctuation_entropy.ranking_weight": "0.0",
    # =====================================================================
    # Block H — Click models (FR-162 .. FR-169)
    # =====================================================================
    # FR-162 — Cascade Click Model
    "cascade_click.enabled": "true",
    "cascade_click.ranking_weight": "0.0",
    # FR-163 — Dynamic Bayesian Network Click Model
    "dbn_click.enabled": "true",
    "dbn_click.ranking_weight": "0.0",
    # FR-164 — User Browsing Model
    "user_browsing_model.enabled": "true",
    "user_browsing_model.ranking_weight": "0.0",
    # FR-165 — Position-Bias Click Model
    "position_bias.enabled": "true",
    "position_bias.ranking_weight": "0.0",
    # FR-166 — Dependent Click Model
    "dependent_click.enabled": "true",
    "dependent_click.ranking_weight": "0.0",
    # FR-167 — Click-Chain Click Model
    "click_chain.enabled": "true",
    "click_chain.ranking_weight": "0.0",
    # FR-168 — Click-Graph Random Walk
    "click_graph_walk.enabled": "true",
    "click_graph_walk.ranking_weight": "0.0",
    # FR-169 — Regression Click Propensity
    "regression_click.enabled": "true",
    "regression_click.ranking_weight": "0.0",
    # =====================================================================
    # Block I — Pre-retrieval query performance predictors (FR-170 .. FR-177)
    # =====================================================================
    # FR-170 — Query Clarity Score
    "query_clarity.enabled": "true",
    "query_clarity.ranking_weight": "0.0",
    # FR-171 — Weighted Information Gain
    "weighted_info_gain.enabled": "true",
    "weighted_info_gain.ranking_weight": "0.0",
    # FR-172 — Normalized Query Commitment
    "nqc.enabled": "true",
    "nqc.ranking_weight": "0.0",
    # FR-173 — Simplified Clarity Score
    "simplified_clarity.enabled": "true",
    "simplified_clarity.ranking_weight": "0.0",
    # FR-174 — Query Scope
    "query_scope.enabled": "true",
    "query_scope.ranking_weight": "0.0",
    # FR-175 — Query Feedback Predictor
    "query_feedback.enabled": "true",
    "query_feedback.ranking_weight": "0.0",
    # FR-176 — Average ICTF Pre-Retrieval Predictor
    "avg_ictf.enabled": "true",
    "avg_ictf.ranking_weight": "0.0",
    # FR-177 — SCQ Pre-Retrieval Predictor
    "scq.enabled": "true",
    "scq.ranking_weight": "0.0",
    # =====================================================================
    # Block J — Term associations and divergences (FR-178 .. FR-185)
    # =====================================================================
    # FR-178 — Pointwise Mutual Information
    "pmi.enabled": "true",
    "pmi.ranking_weight": "0.0",
    # FR-179 — Normalized PMI
    "npmi.enabled": "true",
    "npmi.ranking_weight": "0.0",
    # FR-180 — Log-Likelihood Ratio Term Association
    "llr_term.enabled": "true",
    "llr_term.ranking_weight": "0.0",
    # FR-181 — KL Divergence Source-Destination
    "kl_divergence.enabled": "true",
    "kl_divergence.ranking_weight": "0.0",
    # FR-182 — Jensen-Shannon Divergence
    "js_divergence.enabled": "true",
    "js_divergence.ranking_weight": "0.0",
    # FR-183 — Renyi Divergence
    "renyi_divergence.enabled": "true",
    "renyi_divergence.ranking_weight": "0.0",
    # FR-184 — Hellinger Distance
    "hellinger.enabled": "true",
    "hellinger.ranking_weight": "0.0",
    # FR-185 — Word Mover's Distance
    "wmd.enabled": "true",
    "wmd.ranking_weight": "0.0",
    # =====================================================================
    # Block K — Host- and site-level web-spam signals (FR-186 .. FR-203)
    # =====================================================================
    # FR-186 — Site-Level PageRank
    "site_pagerank.enabled": "true",
    "site_pagerank.ranking_weight": "0.0",
    # FR-187 — Host TrustRank
    "host_trustrank.enabled": "true",
    "host_trustrank.ranking_weight": "0.0",
    # FR-188 — SpamRank Propagation
    "spamrank.enabled": "true",
    "spamrank.ranking_weight": "0.0",
    # FR-189 — BadRank Inverse PageRank
    "badrank.enabled": "true",
    "badrank.ranking_weight": "0.0",
    # FR-190 — Host Age Boost
    "host_age.enabled": "true",
    "host_age.ranking_weight": "0.0",
    # FR-191 — Subdomain Diversity Penalty
    "subdomain_diversity.enabled": "true",
    "subdomain_diversity.ranking_weight": "0.0",
    # FR-192 — Doorway Page Detector
    "doorway_page.enabled": "true",
    "doorway_page.ranking_weight": "0.0",
    # FR-193 — Block-Level PageRank
    "block_pagerank.enabled": "true",
    "block_pagerank.ranking_weight": "0.0",
    # FR-194 — Host-Cluster Cohesion
    "host_cluster_cohesion.enabled": "true",
    "host_cluster_cohesion.ranking_weight": "0.0",
    # FR-195 — Link-Pattern Naturalness
    "link_naturalness.enabled": "true",
    "link_naturalness.ranking_weight": "0.0",
    # FR-196 — Cloaking Detector
    "cloaking.enabled": "true",
    "cloaking.ranking_weight": "0.0",
    # FR-197 — Link-Farm Ring Detector
    "link_farm_ring.enabled": "true",
    "link_farm_ring.ranking_weight": "0.0",
    # FR-198 — Keyword Stuffing Detector
    "keyword_stuffing.enabled": "true",
    "keyword_stuffing.ranking_weight": "0.0",
    # FR-199 — Content Spin Detector
    "content_spin.enabled": "true",
    "content_spin.ranking_weight": "0.0",
    # FR-200 — Sybil Attack Detector
    "sybil_attack.enabled": "true",
    "sybil_attack.ranking_weight": "0.0",
    # FR-201 — Astroturf Pattern Detector
    "astroturf.enabled": "true",
    "astroturf.ranking_weight": "0.0",
    # FR-202 — Clickbait Classifier
    "clickbait.enabled": "true",
    "clickbait.ranking_weight": "0.0",
    # FR-203 — Content-Farm Detector
    "content_farm.enabled": "true",
    "content_farm.ranking_weight": "0.0",
    # =====================================================================
    # Block L — Author and community authority (FR-204 .. FR-212)
    # =====================================================================
    # FR-204 — Author H-Index Within Forum
    "author_h_index.enabled": "true",
    "author_h_index.ranking_weight": "0.0",
    # FR-205 — Co-Authorship Graph PageRank
    "coauthor_pagerank.enabled": "true",
    "coauthor_pagerank.ranking_weight": "0.0",
    # FR-206 — Account Age Gravity
    "account_age.enabled": "true",
    "account_age.ranking_weight": "0.0",
    # FR-207 — Edit History Density
    "edit_history.enabled": "true",
    "edit_history.ranking_weight": "0.0",
    # FR-208 — Moderator Endorsement Signal
    "moderator_endorsement.enabled": "true",
    "moderator_endorsement.ranking_weight": "0.0",
    # FR-209 — Reply Quality-to-Post Ratio
    "reply_quality.enabled": "true",
    "reply_quality.ranking_weight": "0.0",
    # FR-210 — Cross-Thread Topic Consistency
    "cross_thread_consistency.enabled": "true",
    "cross_thread_consistency.ranking_weight": "0.0",
    # FR-211 — Trust Propagation User Graph
    "user_trust_propagation.enabled": "true",
    "user_trust_propagation.ranking_weight": "0.0",
    # FR-212 — User EigenTrust
    "user_eigentrust.enabled": "true",
    "user_eigentrust.ranking_weight": "0.0",
    # =====================================================================
    # Block M — Technical page quality and SEO structure (FR-213 .. FR-220)
    # =====================================================================
    # FR-213 — Heading Hierarchy Correctness
    "heading_hierarchy.enabled": "true",
    "heading_hierarchy.ranking_weight": "0.0",
    # FR-214 — Alt-Text Coverage Ratio
    "alt_text_coverage.enabled": "true",
    "alt_text_coverage.ranking_weight": "0.0",
    # FR-215 — Schema.org Completeness
    "schema_completeness.enabled": "true",
    "schema_completeness.ranking_weight": "0.0",
    # FR-216 — Open Graph Completeness
    "open_graph.enabled": "true",
    "open_graph.ranking_weight": "0.0",
    # FR-217 — Mobile-Friendly Score
    "mobile_friendly.enabled": "true",
    "mobile_friendly.ranking_weight": "0.0",
    # FR-218 — Core Web Vital LCP
    "cwv_lcp.enabled": "true",
    "cwv_lcp.ranking_weight": "0.0",
    # FR-219 — Core Web Vital CLS
    "cwv_cls.enabled": "true",
    "cwv_cls.ranking_weight": "0.0",
    # FR-220 — Core Web Vital INP
    "cwv_inp.enabled": "true",
    "cwv_inp.ranking_weight": "0.0",
    # =====================================================================
    # Block N — Passage segmentation algorithms (FR-221 .. FR-224)
    # =====================================================================
    # FR-221 — Passage TextTiling Boundary Strength
    "texttiling.enabled": "true",
    "texttiling.ranking_weight": "0.0",
    # FR-222 — C99 Passage Segmentation
    "c99_segmentation.enabled": "true",
    "c99_segmentation.ranking_weight": "0.0",
    # FR-223 — DotPlotting Topic Boundary
    "dotplotting.enabled": "true",
    "dotplotting.ranking_weight": "0.0",
    # FR-224 — BayesSeg Bayesian Segmentation
    "bayesseg.enabled": "true",
    "bayesseg.ranking_weight": "0.0",
    # =====================================================================
    # Block P1 — Second-order and trust-region optimisers (META-40 .. META-50)
    # =====================================================================
    # META-40 — Newton's Method
    "newton.enabled": "false",
    # META-41 — Gauss-Newton
    "gauss_newton.enabled": "false",
    # META-42 — Levenberg-Marquardt
    "levenberg_marquardt.enabled": "false",
    # META-43 — L-BFGS-B Bounded Quasi-Newton
    "lbfgs_b.enabled": "false",
    # META-44 — BFGS Full Quasi-Newton
    "bfgs.enabled": "false",
    # META-45 — Fletcher-Reeves Conjugate Gradient
    "fletcher_reeves.enabled": "false",
    # META-46 — AdaGrad
    "adagrad.enabled": "false",
    # META-47 — AdaDelta
    "adadelta.enabled": "false",
    # META-48 — Nadam
    "nadam.enabled": "false",
    # META-49 — AMSGrad
    "amsgrad.enabled": "false",
    # META-50 — Lookahead Optimizer
    "lookahead.enabled": "false",
    # =====================================================================
    # Block P2 — Adaptive deep-learning optimisers (META-51 .. META-53)
    # =====================================================================
    # META-51 — RAdam (Rectified Adam)
    "radam.enabled": "false",
    # META-52 — Lion Optimizer
    "lion.enabled": "false",
    # META-53 — Yogi Optimizer
    "yogi.enabled": "false",
    # =====================================================================
    # Block P3 — Bayesian and surrogate hyperparameter optimisation (META-54 .. META-59)
    # =====================================================================
    # META-54 — GP-EI Bayesian Optimization
    "gp_ei.enabled": "false",
    # META-55 — TPE Tree-Parzen Estimator
    "tpe.enabled": "false",
    # META-56 — SMAC Sequential Model-based Algorithm Configuration
    "smac.enabled": "false",
    # META-57 — BOHB Bayesian Hyperband
    "bohb.enabled": "false",
    # META-58 — Hyperband
    "hyperband.enabled": "false",
    # META-59 — GP-UCB Acquisition
    "gp_ucb.enabled": "false",
    # =====================================================================
    # Block P4 — Multi-objective optimisation (META-60 .. META-64)
    # =====================================================================
    # META-60 — NSGA-II
    "nsga_ii.enabled": "false",
    # META-61 — NSGA-III
    "nsga_iii.enabled": "false",
    # META-62 — MOEA/D
    "moea_d.enabled": "false",
    # META-63 — Epsilon-Constraint Method
    "epsilon_constraint.enabled": "false",
    # META-64 — Tchebycheff Scalarization
    "tchebycheff.enabled": "false",
    # =====================================================================
    # Block P5 — Swarm and nature-inspired metaheuristics (META-65 .. META-69)
    # =====================================================================
    # META-65 — Particle Swarm Optimization
    "pso.enabled": "false",
    # META-66 — Ant Colony Optimization
    "aco.enabled": "false",
    # META-67 — Cuckoo Search
    "cuckoo_search.enabled": "false",
    # META-68 — Firefly Algorithm
    "firefly.enabled": "false",
    # META-69 — Bat Algorithm
    "bat_algorithm.enabled": "false",
    # =====================================================================
    # Block P6 — Online learning and streaming optimisation (META-70 .. META-75)
    # =====================================================================
    # META-70 — FTRL-Proximal
    "ftrl.enabled": "false",
    # META-71 — Online Newton Step
    "online_newton.enabled": "false",
    # META-72 — Online Mirror Descent
    "online_mirror_descent.enabled": "false",
    # META-73 — Online AdaBoost.OC
    "online_adaboost.enabled": "false",
    # META-74 — Projected Online Gradient
    "projected_online_gradient.enabled": "false",
    # META-75 — ADMM Streaming
    "admm_streaming.enabled": "false",
    # =====================================================================
    # Block P7 — Listwise and smooth-rank loss surrogates (META-76 .. META-81)
    # =====================================================================
    # META-76 — ApproxNDCG
    "approxndcg.enabled": "false",
    # META-77 — Lambda Loss
    "lambda_loss.enabled": "false",
    # META-78 — Neural NDCG
    "neural_ndcg.enabled": "false",
    # META-79 — SoftRank
    "softrank.enabled": "false",
    # META-80 — Smooth-AP
    "smooth_ap.enabled": "false",
    # META-81 — Listwise Cross-Entropy
    "listwise_ce.enabled": "false",
    # =====================================================================
    # Block P8 — Proximal, structured-sparsity regularisers (META-82 .. META-86)
    # =====================================================================
    # META-82 — FISTA Proximal Gradient
    "fista.enabled": "false",
    # META-83 — Nuclear-Norm Regularization
    "nuclear_norm.enabled": "false",
    # META-84 — Group Lasso
    "group_lasso.enabled": "false",
    # META-85 — Fused Lasso
    "fused_lasso.enabled": "false",
    # META-86 — SCAD Penalty
    "scad.enabled": "false",
    # =====================================================================
    # Block P9 — Calibration (META-87 .. META-90)
    # =====================================================================
    # META-87 — Platt Sigmoid Scaling
    "platt_scaling.enabled": "false",
    # META-88 — Beta Calibration
    "beta_calibration.enabled": "false",
    # META-89 — Dirichlet Calibration
    "dirichlet_calibration.enabled": "false",
    # META-90 — Histogram Binning Calibration
    "histogram_binning.enabled": "false",
    # =====================================================================
    # Block P10 — Learning-rate schedules (META-91 .. META-95)
    # =====================================================================
    # META-91 — Cosine Annealing with Warm Restarts
    "cosine_warm_restart.enabled": "false",
    # META-92 — One-Cycle LR
    "one_cycle_lr.enabled": "false",
    # META-93 — Transformer Warmup + Linear Decay
    "transformer_warmup.enabled": "false",
    # META-94 — Polynomial Decay LR
    "poly_decay_lr.enabled": "false",
    # META-95 — Step Decay on Plateau
    "step_decay_plateau.enabled": "false",
    # =====================================================================
    # Block P11 — Ensembling and weight averaging (META-96 .. META-99)
    # =====================================================================
    # META-96 — Stochastic Weight Averaging
    "swa.enabled": "false",
    # META-97 — Polyak-Ruppert Averaging
    "polyak_ruppert.enabled": "false",
    # META-98 — Snapshot Ensemble
    "snapshot_ensemble.enabled": "false",
    # META-99 — Deep Ensembles
    "deep_ensembles.enabled": "false",
    # =====================================================================
    # Block P12 — Distributionally robust optimisation (META-100 .. META-101)
    # =====================================================================
    # META-100 — Distributionally Robust Optimization
    "dro.enabled": "false",
    # META-101 — Wasserstein DRO
    "wasserstein_dro.enabled": "false",
    # =====================================================================
    # Block Q1 — Mini-batch and sampling strategies (META-102 .. META-105)
    # =====================================================================
    # META-102 — Hard Negative Mining (OHEM)
    "ohem.enabled": "false",
    # META-103 — Reservoir Sampling
    "reservoir_sampling.enabled": "false",
    # META-104 — Importance-Weighted Minibatch
    "importance_minibatch.enabled": "false",
    # META-105 — Stratified K-Fold Minibatch
    "stratified_kfold_minibatch.enabled": "false",
    # =====================================================================
    # Block Q2 — Markov Chain Monte Carlo (META-106 .. META-113)
    # =====================================================================
    # META-106 — Metropolis-Hastings
    "metropolis_hastings.enabled": "false",
    # META-107 — Gibbs Sampling
    "gibbs.enabled": "false",
    # META-108 — Slice Sampling
    "slice_sampling.enabled": "false",
    # META-109 — Hamiltonian Monte Carlo
    "hmc.enabled": "false",
    # META-110 — NUTS No-U-Turn Sampler
    "nuts.enabled": "false",
    # META-111 — Stochastic Gradient Langevin Dynamics
    "sgld.enabled": "false",
    # META-112 — Elliptical Slice Sampling
    "elliptical_slice.enabled": "false",
    # META-113 — Sequential Monte Carlo
    "smc.enabled": "false",
    # =====================================================================
    # Block Q3 — Variational inference (META-114 .. META-119)
    # =====================================================================
    # META-114 — Mean-Field Variational Inference
    "mean_field_vi.enabled": "false",
    # META-115 — Expectation Propagation
    "ep.enabled": "false",
    # META-116 — Stein Variational Gradient Descent
    "svgd.enabled": "false",
    # META-117 — Black-Box Variational Inference
    "bbvi.enabled": "false",
    # META-118 — Reparameterization-Trick Variational Inference
    "reparam_vi.enabled": "false",
    # META-119 — Amortised Variational Inference
    "amortised_vi.enabled": "false",
    # =====================================================================
    # Block Q4 — Evolutionary and population-based search (META-120 .. META-127)
    # =====================================================================
    # META-120 — Genetic Algorithm
    "genetic_algorithm.enabled": "false",
    # META-121 — Evolution Strategies
    "evolution_strategies.enabled": "false",
    # META-122 — Natural Evolution Strategies
    "nes.enabled": "false",
    # META-123 — Tabu Search
    "tabu_search.enabled": "false",
    # META-124 — GRASP
    "grasp.enabled": "false",
    # META-125 — Variable Neighborhood Search
    "vns.enabled": "false",
    # META-126 — ALNS Adaptive Large Neighbourhood Search
    "alns.enabled": "false",
    # META-127 — Harmony Search
    "harmony_search.enabled": "false",
    # =====================================================================
    # Block Q5 — Accelerated gradient methods (META-128 .. META-135)
    # =====================================================================
    # META-128 — Natural Gradient
    "natural_gradient.enabled": "false",
    # META-129 — AdaBelief
    "adabelief.enabled": "false",
    # META-130 — Nesterov Accelerated Gradient
    "nag.enabled": "false",
    # META-131 — Mirror Descent (Offline)
    "mirror_descent.enabled": "false",
    # META-132 — Proximal Gradient (ISTA)
    "ista.enabled": "false",
    # META-133 — Apollo Optimiser
    "apollo.enabled": "false",
    # META-134 — LAMB
    "lamb.enabled": "false",
    # META-135 — LARS
    "lars.enabled": "false",
    # =====================================================================
    # Block Q6 — Regularisation via data augmentation and noise (META-136 .. META-142)
    # =====================================================================
    # META-136 — Label Smoothing
    "label_smoothing.enabled": "false",
    # META-137 — Mixup
    "mixup.enabled": "false",
    # META-138 — CutMix
    "cutmix.enabled": "false",
    # META-139 — Cutout
    "cutout.enabled": "false",
    # META-140 — DropConnect
    "dropconnect.enabled": "false",
    # META-141 — Stochastic Depth
    "stochastic_depth.enabled": "false",
    # META-142 — Gradient Noise Injection
    "gradient_noise.enabled": "false",
    # =====================================================================
    # Block Q7 — Basis-function feature expansions (META-143 .. META-146)
    # =====================================================================
    # META-143 — Polynomial Feature Expansion
    "poly_features.enabled": "false",
    # META-144 — B-Spline Basis Features
    "bspline_basis.enabled": "false",
    # META-145 — Natural Cubic Spline Basis
    "cubic_spline_basis.enabled": "false",
    # META-146 — Fourier Random Features
    "fourier_features.enabled": "false",
    # =====================================================================
    # Block Q8 — Categorical and high-cardinality encodings (META-147 .. META-150)
    # =====================================================================
    # META-147 — Hashing Trick
    "hashing_trick.enabled": "false",
    # META-148 — Target Encoding
    "target_encoding.enabled": "false",
    # META-149 — Count Encoding
    "count_encoding.enabled": "false",
    # META-150 — Leave-One-Out Target Encoding
    "loo_target_encoding.enabled": "false",
    # =====================================================================
    # Block Q9 — Dimensionality reduction (META-151 .. META-157)
    # =====================================================================
    # META-151 — PCA
    "pca.enabled": "false",
    # META-152 — Kernel PCA
    "kernel_pca.enabled": "false",
    # META-153 — ICA
    "ica.enabled": "false",
    # META-154 — Sparse PCA
    "sparse_pca.enabled": "false",
    # META-155 — LDA Linear Discriminant Analysis
    "lda.enabled": "false",
    # META-156 — CCA Canonical Correlation Analysis
    "cca.enabled": "false",
    # META-157 — Random Projection (Johnson-Lindenstrauss)
    "random_projection.enabled": "false",
    # =====================================================================
    # Block Q10 — Kernel-based and Gaussian-process regressors (META-158 .. META-162)
    # =====================================================================
    # META-158 — Kernel Ridge Regression
    "kernel_ridge.enabled": "false",
    # META-159 — Support Vector Regression
    "svr.enabled": "false",
    # META-160 — Nystrom Approximation
    "nystrom.enabled": "false",
    # META-161 — Random Fourier Features
    "rff.enabled": "false",
    # META-162 — Gaussian Process Regression
    "gpr.enabled": "false",
    # =====================================================================
    # Block Q11 — Information-theoretic model selection (META-163 .. META-167)
    # =====================================================================
    # META-163 — Kraskov Mutual Information
    "kraskov_mi.enabled": "false",
    # META-164 — Information Bottleneck
    "info_bottleneck.enabled": "false",
    # META-165 — Minimum Description Length
    "mdl.enabled": "false",
    # META-166 — Akaike Information Criterion
    "aic.enabled": "false",
    # META-167 — Bayesian Information Criterion
    "bic.enabled": "false",
    # =====================================================================
    # Block Q12 — Clustering algorithms (META-168 .. META-175)
    # =====================================================================
    # META-168 — K-Means
    "kmeans.enabled": "false",
    # META-169 — K-Medoids (PAM)
    "kmedoids.enabled": "false",
    # META-170 — DBSCAN
    "dbscan.enabled": "false",
    # META-171 — HDBSCAN
    "hdbscan.enabled": "false",
    # META-172 — OPTICS
    "optics.enabled": "false",
    # META-173 — Mean Shift
    "mean_shift.enabled": "false",
    # META-174 — Affinity Propagation
    "affinity_propagation.enabled": "false",
    # META-175 — BIRCH
    "birch.enabled": "false",
    # =====================================================================
    # Block Q13 — Feature importance and model explanation (META-176 .. META-180)
    # =====================================================================
    # META-176 — Permutation Importance
    "permutation_importance.enabled": "false",
    # META-177 — SHAP Values
    "shap.enabled": "false",
    # META-178 — LIME
    "lime.enabled": "false",
    # META-179 — Integrated Gradients
    "integrated_gradients.enabled": "false",
    # META-180 — Mean Decrease Impurity
    "mdi.enabled": "false",
    # =====================================================================
    # Block Q14 — Active and semi-supervised learning (META-181 .. META-190)
    # =====================================================================
    # META-181 — Uncertainty Sampling
    "uncertainty_sampling.enabled": "false",
    # META-182 — Query-by-Committee
    "qbc.enabled": "false",
    # META-183 — Expected Model Change
    "expected_model_change.enabled": "false",
    # META-184 — Density-Weighted Sampling
    "density_weighted.enabled": "false",
    # META-185 — Batch-Mode Active Learning
    "batch_active_learning.enabled": "false",
    # META-186 — Self-Training
    "self_training.enabled": "false",
    # META-187 — Co-Training
    "co_training.enabled": "false",
    # META-188 — Label Propagation (Graph)
    "label_propagation.enabled": "false",
    # META-189 — MixMatch
    "mixmatch.enabled": "false",
    # META-190 — FixMatch
    "fixmatch.enabled": "false",
    # =====================================================================
    # Block Q15 — Causal inference estimators (META-191 .. META-195)
    # =====================================================================
    # META-191 — Inverse Propensity Weighting
    "ipw.enabled": "false",
    # META-192 — Double Machine Learning
    "double_ml.enabled": "false",
    # META-193 — Doubly-Robust Estimator
    "doubly_robust.enabled": "false",
    # META-194 — Causal Forest
    "causal_forest.enabled": "false",
    # META-195 — T/S/X-Learner Family
    "tsx_learner.enabled": "false",
    # =====================================================================
    # Block Q16 — Reinforcement-learning policy optimisers (META-196 .. META-201)
    # =====================================================================
    # META-196 — Q-Learning
    "q_learning.enabled": "false",
    # META-197 — SARSA
    "sarsa.enabled": "false",
    # META-198 — REINFORCE Policy Gradient
    "reinforce.enabled": "false",
    # META-199 — Actor-Critic
    "actor_critic.enabled": "false",
    # META-200 — Proximal Policy Optimization
    "ppo.enabled": "false",
    # META-201 — DDPG
    "ddpg.enabled": "false",
    # =====================================================================
    # Block Q17 — Contextual bandits (META-202 .. META-205)
    # =====================================================================
    # META-202 — Epsilon-Greedy
    "epsilon_greedy.enabled": "false",
    # META-203 — LinUCB
    "linucb.enabled": "false",
    # META-204 — LinTS Linear Thompson Sampling
    "lints.enabled": "false",
    # META-205 — Cascading Bandits
    "cascading_bandits.enabled": "false",
    # =====================================================================
    # Block Q18 — Matrix factorisation (META-206 .. META-210)
    # =====================================================================
    # META-206 — SVD
    "svd.enabled": "false",
    # META-207 — NMF Non-Negative Matrix Factorization
    "nmf.enabled": "false",
    # META-208 — Probabilistic Matrix Factorization
    "pmf.enabled": "false",
    # META-209 — Bayesian PMF
    "bpmf.enabled": "false",
    # META-210 — Weighted ALS (Implicit Feedback)
    "wals.enabled": "false",
    # =====================================================================
    # Block Q19 — Weight initialisation and normalisation (META-211 .. META-218)
    # =====================================================================
    # META-211 — Xavier/Glorot Init
    "xavier_init.enabled": "false",
    # META-212 — He Init
    "he_init.enabled": "false",
    # META-213 — Orthogonal Init
    "orthogonal_init.enabled": "false",
    # META-214 — Layer Normalization
    "layer_norm.enabled": "false",
    # META-215 — Batch Normalization
    "batch_norm.enabled": "false",
    # META-216 — Group Normalization
    "group_norm.enabled": "false",
    # META-217 — Weight Normalization
    "weight_norm.enabled": "false",
    # META-218 — Spectral Normalization
    "spectral_norm.enabled": "false",
    # =====================================================================
    # Block Q20 — Probabilistic calibration (META-219 .. META-223)
    # =====================================================================
    # META-219 — BBQ Bayesian Binning into Quantiles
    "bbq.enabled": "false",
    # META-220 — Spline Calibration
    "spline_calibration.enabled": "false",
    # META-221 — Venn-Abers Predictors
    "venn_abers.enabled": "false",
    # META-222 — Focal Loss Calibration
    "focal_calibration.enabled": "false",
    # META-223 — Cumulative Histogram Calibration
    "cumulative_histogram_calibration.enabled": "false",
    # =====================================================================
    # Block Q21 — Feature selection methods (META-224 .. META-231)
    # =====================================================================
    # META-224 — Recursive Feature Elimination
    "rfe.enabled": "false",
    # META-225 — Stability Selection
    "stability_selection.enabled": "false",
    # META-226 — mRMR
    "mrmr.enabled": "false",
    # META-227 — Mutual Information Feature Ranking
    "mi_feature_ranking.enabled": "false",
    # META-228 — Chi-Squared Feature Test
    "chi_squared.enabled": "false",
    # META-229 — ANOVA F-Statistic
    "anova_f.enabled": "false",
    # META-230 — Forward Selection
    "forward_selection.enabled": "false",
    # META-231 — Boruta Wrapper
    "boruta.enabled": "false",
    # =====================================================================
    # Block Q22 — Metric learning (META-232 .. META-236)
    # =====================================================================
    # META-232 — Mahalanobis Metric
    "mahalanobis.enabled": "false",
    # META-233 — LMNN Large Margin Nearest Neighbour
    "lmnn.enabled": "false",
    # META-234 — NCA Neighbourhood Components Analysis
    "nca.enabled": "false",
    # META-235 — ITML Information-Theoretic Metric Learning
    "itml.enabled": "false",
    # META-236 — LogDet Metric Learning
    "logdet_metric.enabled": "false",
    # =====================================================================
    # Block Q23 — Outlier and anomaly detection (META-237 .. META-242)
    # =====================================================================
    # META-237 — LOF Local Outlier Factor
    "lof.enabled": "false",
    # META-238 — One-Class SVM
    "one_class_svm.enabled": "false",
    # META-239 — Elliptic Envelope
    "elliptic_envelope.enabled": "false",
    # META-240 — Autoencoder Reconstruction Error
    "autoencoder_recon.enabled": "false",
    # META-241 — Minimum Covariance Determinant
    "mcd.enabled": "false",
    # META-242 — GL Early Stopping
    "gl_early_stopping.enabled": "false",
    # =====================================================================
    # Block Q24 — AutoML, online trees and streaming variants (META-243 .. META-249)
    # =====================================================================
    # META-243 — Population-Based Training
    "pbt.enabled": "false",
    # META-244 — Multi-Armed Bandit Hyperparameter Optimization
    "mab_hpo.enabled": "false",
    # META-245 — Adaptive Random Forest
    "adaptive_rf.enabled": "false",
    # META-246 — Mondrian Forest
    "mondrian_forest.enabled": "false",
    # META-247 — Mini-Batch K-Means
    "minibatch_kmeans.enabled": "false",
    # META-248 — Incremental PCA
    "incremental_pca.enabled": "false",
    # META-249 — Online SVD (Brand's algorithm)
    "online_svd.enabled": "false",
}
