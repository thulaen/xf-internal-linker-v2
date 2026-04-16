"""Forward-declared Phase 2 ranking-signal weights — Blocks E through H."""
# Covers 36 ranking signals across:
#   - Block E: Time-series / trend / change detection (FR-134 .. FR-143)
#   - Block F: Streaming sketches and approximate counting (FR-144 .. FR-151)
#   - Block G: Linguistic and text-quality signals (FR-152 .. FR-161)
#   - Block H: Click-model relevance estimators (FR-162 .. FR-169)
#
# Each entry has the researched starting ranking_weight and all algorithm-
# specific hyperparameters from the spec's "Starting weight preset". Signals
# are LIVE the moment the C++ extension is wired and the auto-tuner (FR-018)
# adjusts the weight from there.
#
# Source specs: see fr1NN range under docs/specs/.
#
# Where the spec preset listed ranking_weight as 0.0 (forward-declaration
# default), this file replaces that with a small live starting weight in the
# 0.02-0.04 range so each signal contributes the moment its C++ kernel is
# wired. Where the spec uses a non-default key prefix, this file honors the
# spec prefix and notes it inline.

from __future__ import annotations

FORWARD_DECLARED_WEIGHTS_PHASE2_SIGNALS_E_H: dict[str, str] = {
    # =====================================================================
    # Block E - Time-series / trend / change detection (FR-134 .. FR-143)
    # =====================================================================
    # FR-134 - Kleinberg Burst Detection
    # Kleinberg, KDD 2002 - two-state HMM over inter-event gaps. Starting
    # weight 0.02 because burst classification is binary and noisy on small
    # event windows; raise after diagnostics confirm gap-mean separation.
    "kleinberg_burst.enabled": "true",
    "kleinberg_burst.ranking_weight": "0.02",
    "kleinberg_burst.gamma": "1.0",
    "kleinberg_burst.scale_s": "2.0",
    "kleinberg_burst.min_events": "8",
    # FR-135 - PELT Change-Point Detection
    # Killick et al., JASA 2012 - exact pruned segmentation. Starting weight
    # 0.02 because the signal flags abrupt regime changes that should nudge
    # ranking only mildly until per-site penalty beta is tuned.
    "pelt_changepoint.enabled": "true",
    "pelt_changepoint.ranking_weight": "0.02",
    "pelt_changepoint.penalty_beta": "log_n",
    "pelt_changepoint.min_segment_length": "5",
    "pelt_changepoint.recency_window_days": "30",
    # FR-136 - CUSUM Cumulative Anomaly (spec prefix: cusum_anomaly)
    # Page 1954 sequential analysis. Starting weight 0.02 because the
    # online drift_score is robust but should not dominate ranking until
    # per-page mu/sigma baselines stabilise after warmup.
    "cusum_anomaly.enabled": "true",
    "cusum_anomaly.ranking_weight": "0.02",
    "cusum_anomaly.delta_sigmas": "1.0",
    "cusum_anomaly.threshold_h_sigmas": "5.0",
    "cusum_anomaly.warmup_observations": "20",
    # FR-137 - STL Seasonal-Trend Decomposition (spec prefix: stl_decomposition)
    # Cleveland et al. 1990 LOESS-based decomposition. Starting weight 0.03
    # because trend_strength and seasonal_strength are well-validated quality
    # signals from statsmodels and align with FR-050.
    "stl_decomposition.enabled": "true",
    "stl_decomposition.ranking_weight": "0.03",
    "stl_decomposition.period_n_p": "7",
    "stl_decomposition.seasonal_span_n_s": "13",
    "stl_decomposition.trend_span_n_t": "21",
    "stl_decomposition.outer_iterations": "1",
    "stl_decomposition.inner_iterations": "2",
    # FR-138 - Mann-Kendall Non-Parametric Trend
    # Mann 1945, Kendall 1975. Starting weight 0.02 because the test gives
    # a binary trend verdict; magnitude comes from FR-139 Theil-Sen.
    "mann_kendall.enabled": "true",
    "mann_kendall.ranking_weight": "0.02",
    "mann_kendall.alpha": "0.05",
    "mann_kendall.min_observations": "10",
    "mann_kendall.window_days": "60",
    # FR-139 - Theil-Sen Robust Slope
    # Theil 1950, Sen 1968. Starting weight 0.03 because slope magnitude is
    # a clean quantitative signal robust to outliers, useful for ranking.
    "theil_sen.enabled": "true",
    "theil_sen.ranking_weight": "0.03",
    "theil_sen.alpha_confidence": "0.05",
    "theil_sen.min_observations": "10",
    "theil_sen.window_days": "30",
    # FR-140 - Fourier Periodicity Strength
    # Welch 1967 PSD estimate. Starting weight 0.02 because periodicity
    # strength can over-fire on noisy click streams; needs operator review.
    "fourier_periodicity.enabled": "true",
    "fourier_periodicity.ranking_weight": "0.02",
    "fourier_periodicity.welch_segment_length": "64",
    "fourier_periodicity.welch_overlap_fraction": "0.5",
    "fourier_periodicity.min_observations": "32",
    # FR-141 - Autocorrelation Lag-K (spec prefix: acf_lag_k)
    # Wiener-Khinchin theorem via FFT. Starting weight 0.02 because raw ACF
    # at fixed lags is informative but interacts with FR-140 and FR-142.
    "acf_lag_k.enabled": "true",
    "acf_lag_k.ranking_weight": "0.02",
    "acf_lag_k.lags_to_compute": "1,7,30",
    "acf_lag_k.use_fft": "true",
    "acf_lag_k.min_observations": "32",
    # FR-142 - Partial Autocorrelation (spec prefix: pacf_lag_k)
    # Durbin-Levinson recursion. Starting weight 0.02 - PACF is more
    # specific than ACF but signal density per page is low.
    "pacf_lag_k.enabled": "true",
    "pacf_lag_k.ranking_weight": "0.02",
    "pacf_lag_k.lags_to_compute": "1,7,30",
    "pacf_lag_k.method": "durbin_levinson",
    "pacf_lag_k.min_observations": "50",
    # FR-143 - EWMA Smoothed Click Rate (spec prefix: ewma_smoothed)
    # Roberts 1959 exponentially weighted moving average. Starting weight
    # 0.03 because EWMA is a proven low-variance click-rate estimator.
    "ewma_smoothed.enabled": "true",
    "ewma_smoothed.ranking_weight": "0.03",
    "ewma_smoothed.alpha": "0.1",
    "ewma_smoothed.warmup_observations": "5",
    "ewma_smoothed.reset_on_gap_days": "30",
    # =====================================================================
    # Block F - Streaming sketches and approximate counting (FR-144 .. FR-151)
    # =====================================================================
    # FR-144 - HyperLogLog Unique Visitors (spec prefix: hyperloglog)
    # Flajolet et al. 2007. Starting weight 0.03 because cardinality of
    # unique visitors is a reliable popularity signal aligned with FR-022.
    "hyperloglog.enabled": "true",
    "hyperloglog.ranking_weight": "0.03",
    "hyperloglog.precision_p": "12",
    "hyperloglog.hash_function": "xxhash64",
    "hyperloglog.min_estimated_cardinality": "10",
    # FR-145 - HyperLogLog++ (spec prefix: hyperloglog_pp)
    # Heule, Nunkesser & Hall, EDBT 2013 - bias-corrected. Starting weight
    # 0.03 - same role as FR-144 with better small-cardinality accuracy.
    "hyperloglog_pp.enabled": "true",
    "hyperloglog_pp.ranking_weight": "0.03",
    "hyperloglog_pp.precision_p": "14",
    "hyperloglog_pp.sparse_threshold_fraction": "0.25",
    "hyperloglog_pp.bias_table": "google_2013",
    # FR-146 - Count-Min Sketch Anchor Rarity (spec prefix: countmin_anchor)
    # Cormode & Muthukrishnan 2005. Starting weight 0.02 because rarity
    # estimates can be noisy at low frequency; conservative until calibrated.
    "countmin_anchor.enabled": "true",
    "countmin_anchor.ranking_weight": "0.02",
    "countmin_anchor.epsilon": "0.001",
    "countmin_anchor.delta": "0.01",
    "countmin_anchor.use_conservative_update": "true",
    "countmin_anchor.hash_function": "murmurhash3",
    # FR-147 - Count Sketch Signed Frequency
    # Charikar, Chen & Farach-Colton, ICALP 2002. Starting weight 0.02
    # because median-of-d signed estimates are unbiased but noisier than CMS.
    "count_sketch.enabled": "true",
    "count_sketch.ranking_weight": "0.02",
    "count_sketch.epsilon": "0.01",
    "count_sketch.delta": "0.01",
    "count_sketch.hash_function": "murmurhash3",
    "count_sketch.sign_hash_seed": "0xC0FFEE",
    # FR-148 - Space-Saving Top-K Anchors
    # Metwally, Agrawal & El Abbadi, ICDT 2005. Starting weight 0.03
    # because top-k anchor identification is a well-defined ranking signal.
    "space_saving.enabled": "true",
    "space_saving.ranking_weight": "0.03",
    "space_saving.k_counters": "1000",
    "space_saving.report_top_n": "100",
    "space_saving.guarantee_threshold_epsilon": "0.001",
    # FR-149 - t-digest Quantile Tracker
    # Dunning & Ertl 2019. Starting weight 0.02 - quantile tracking is
    # used as a calibration helper; small direct ranking weight.
    "t_digest.enabled": "true",
    "t_digest.ranking_weight": "0.02",
    "t_digest.compression_delta": "100",
    "t_digest.compress_every_n_inserts": "500",
    "t_digest.scale_function": "k1_arcsin",
    # FR-150 - Lossy Counting Frequency (spec prefix: lossy_counting)
    # Manku & Motwani, VLDB 2002. Starting weight 0.02 because frequency
    # estimates are upper-bounded with bounded error; redundant with FR-148.
    "lossy_counting.enabled": "true",
    "lossy_counting.ranking_weight": "0.02",
    "lossy_counting.epsilon": "0.001",
    "lossy_counting.support_threshold_s": "0.005",
    "lossy_counting.bucket_width_w": "auto",
    # FR-151 - b-bit MinHash Similarity (spec prefix: b_bit_minhash)
    # Li & Konig, WWW 2010. Starting weight 0.03 because b-bit MinHash is
    # a well-validated near-duplicate similarity estimator.
    "b_bit_minhash.enabled": "true",
    "b_bit_minhash.ranking_weight": "0.03",
    "b_bit_minhash.b_bits_per_signature": "1",
    "b_bit_minhash.k_permutations": "512",
    "b_bit_minhash.universe_size_D": "auto",
    "b_bit_minhash.shingle_size": "5",
    # =====================================================================
    # Block G - Linguistic / text-quality signals (FR-152 .. FR-161)
    # =====================================================================
    # FR-152 - Passive Voice Ratio
    # Hayes & Bajzek 2008 readability metrics. Starting weight 0.02 because
    # passive-voice ratio is a soft style signal; raise after spaCy POS QA.
    "passive_voice.enabled": "true",
    "passive_voice.ranking_weight": "0.02",
    "passive_voice.target_ratio": "0.20",
    "passive_voice.penalty_above": "0.40",
    # FR-153 - Nominalization Density
    # Halliday systemic functional linguistics. Starting weight 0.02 -
    # heuristic suffix matching can over-fire on legitimate jargon.
    "nominalization.enabled": "true",
    "nominalization.ranking_weight": "0.02",
    "nominalization.target_density": "0.15",
    "nominalization.penalty_above": "0.50",
    # FR-154 - Hedging Language Density
    # Hyland 2005 academic-writing hedging. Starting weight 0.02 because
    # the lexicon is moderate-coverage; tune target_per_1k after diagnostics.
    "hedging.enabled": "true",
    "hedging.ranking_weight": "0.02",
    "hedging.target_per_1k": "10.0",
    "hedging.penalty_above": "25.0",
    # FR-155 - Discourse Connective Density (spec prefix: discourse_conn)
    # Penn Discourse Treebank inventory. Starting weight 0.03 because
    # connective use correlates strongly with cohesion and is well-studied.
    "discourse_conn.enabled": "true",
    "discourse_conn.ranking_weight": "0.03",
    "discourse_conn.target_per_sentence": "0.6",
    # FR-156 - Cohesion Score (Coh-Metrix)
    # Graesser et al. 2004 LSA-based sentence cohesion. Starting weight
    # 0.04 because cohesion is a mature, validated text-quality signal.
    "cohesion.enabled": "true",
    "cohesion.ranking_weight": "0.04",
    "cohesion.embedding_dim": "300",
    "cohesion.target_value": "0.30",
    # FR-157 - Part-of-Speech Diversity
    # Shannon entropy over POS distribution. Starting weight 0.02 because
    # POS entropy is a coarse stylistic signal; small starting weight.
    "pos_diversity.enabled": "true",
    "pos_diversity.ranking_weight": "0.02",
    "pos_diversity.target_entropy": "4.0",
    # FR-158 - Sentence Length Variance (spec prefix: sent_variance)
    # Coefficient-of-variation over sentence lengths. Starting weight 0.02
    # because sentence-length CV correlates weakly with quality on its own.
    "sent_variance.enabled": "true",
    "sent_variance.ranking_weight": "0.02",
    "sent_variance.target_cv": "0.45",
    # FR-159 - Yule's K Lexical Concentration
    # Yule 1944 statistical lexicography. Starting weight 0.02 because K
    # is sensitive to text length; needs FR-160 MTLD as a complement.
    "yule_k.enabled": "true",
    "yule_k.ranking_weight": "0.02",
    "yule_k.target_max": "150.0",
    "yule_k.penalty_above": "250.0",
    # FR-160 - MTLD Lexical Diversity
    # McCarthy & Jarvis 2010 - text-length-robust diversity. Starting
    # weight 0.03 because MTLD is the recommended modern lexical-diversity
    # metric and is robust to document length.
    "mtld.enabled": "true",
    "mtld.ranking_weight": "0.03",
    "mtld.ttr_threshold": "0.72",
    "mtld.target_min": "60.0",
    # FR-161 - Punctuation Entropy
    # Shannon entropy over punctuation-class distribution. Starting weight
    # 0.02 - secondary stylistic signal, useful as a quality tie-breaker.
    "punct_entropy.enabled": "true",
    "punct_entropy.ranking_weight": "0.02",
    "punct_entropy.target_entropy": "2.3",
    # =====================================================================
    # Block H - Click-model relevance estimators (FR-162 .. FR-169)
    # =====================================================================
    # FR-162 - Cascade Click Model
    # Craswell et al., WSDM 2008. Starting weight 0.04 because cascade
    # alpha is a direct relevance estimate; well-validated on web search.
    "ccm.enabled": "true",
    "ccm.ranking_weight": "0.04",
    "ccm.min_impressions": "20",
    "ccm.smoothing_alpha": "1.0",
    # FR-163 - Dynamic Bayesian Network Click Model
    # Chapelle & Zhang, WWW 2009. Starting weight 0.04 because DBN
    # separates attractiveness from satisfaction better than simple cascade.
    "dbn.enabled": "true",
    "dbn.ranking_weight": "0.04",
    "dbn.continuation_gamma": "0.7",
    "dbn.em_max_iters": "20",
    "dbn.em_tolerance": "1e-4",
    # FR-164 - User Browsing Model
    # Dupret & Piwowarski, SIGIR 2008. Starting weight 0.03 because UBM
    # has stronger position-and-distance assumptions; tune EM convergence.
    "ubm.enabled": "true",
    "ubm.ranking_weight": "0.03",
    "ubm.max_rank": "10",
    "ubm.em_max_iters": "20",
    # FR-165 - Position Bias Model
    # Richardson, Dominowska & Ragno, WWW 2007. Starting weight 0.03
    # because PBM is the simplest examination model; useful as a baseline.
    "pbm.enabled": "true",
    "pbm.ranking_weight": "0.03",
    "pbm.max_rank": "10",
    "pbm.em_max_iters": "15",
    # FR-166 - Dependent Click Model
    # Guo, Liu & Wang, WSDM 2009. Starting weight 0.03 - closed-form MLE
    # is fast and robust; modest weight pending live A/B comparison.
    "dcm.enabled": "true",
    "dcm.ranking_weight": "0.03",
    "dcm.max_rank": "10",
    "dcm.smoothing_alpha": "1.0",
    # FR-167 - Click Chain Model (spec prefix: ccm_bayes)
    # Guo, Liu & Wang, WWW 2009. Starting weight 0.03 because Bayesian
    # CCM posterior is sensitive to alpha priors; tune before promoting.
    "ccm_bayes.enabled": "true",
    "ccm_bayes.ranking_weight": "0.03",
    "ccm_bayes.alpha_1": "0.5",
    "ccm_bayes.alpha_2": "0.7",
    "ccm_bayes.alpha_3": "0.3",
    "ccm_bayes.prior_a": "1.0",
    "ccm_bayes.prior_b": "1.0",
    # FR-168 - Click Graph Random Walk (spec prefix: click_walk)
    # Craswell & Szummer, SIGIR 2007. Starting weight 0.03 because random
    # walk on click graph is a clean similarity-propagation signal.
    "click_walk.enabled": "true",
    "click_walk.ranking_weight": "0.03",
    "click_walk.restart_prob": "0.15",
    "click_walk.walk_steps": "5",
    # FR-169 - Regression Click Propensity (spec prefix: reg_em)
    # Wang, Bendersky, Metzler & Najork, WSDM 2018 Regression EM. Starting
    # weight 0.04 because feature-rich regression EM is the most flexible
    # debiased click estimator and supports multiple bias features.
    "reg_em.enabled": "true",
    "reg_em.ranking_weight": "0.04",
    "reg_em.em_max_iters": "10",
    "reg_em.feature_set": "rank,hour,device,query_len",
    "reg_em.l2_reg": "0.01",
}
