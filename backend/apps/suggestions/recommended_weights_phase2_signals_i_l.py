"""Forward-declared Phase 2 ranking-signal weights — Blocks I through L."""
# Covers 34 ranking signals across:
#   - Block I: Query-performance prediction (FR-170 .. FR-177, 8 FRs)
#   - Block J: Information-theoretic divergences (FR-178 .. FR-185, 8 FRs)
#   - Block K: Site / host-level authority (FR-186 .. FR-194, 9 FRs)
#   - Block L: Anti-spam / adversarial detectors (FR-195 .. FR-203, 9 FRs)
#
# Each entry has researched starting ranking_weight + all algorithm-specific
# hyperparameters from the spec. Signals go live the moment the C++ extension
# is wired. Starting weights deliberately conservative (0.02 .. 0.05) so a
# new signal cannot dominate ranking before live diagnostics validate it.
#
# Source specs: docs/specs/fr170-*.md .. docs/specs/fr203-*.md
# Each FR's "Starting weight preset" was the input. The ranking_weight value
# was raised from the spec's inert "0.0" to a small live value per task brief.
#
# These keys are merged into RECOMMENDED_PRESET_WEIGHTS at import time by the
# main recommended_weights.py module.

from __future__ import annotations

FORWARD_DECLARED_WEIGHTS_PHASE2_SIGNALS_I_L: dict[str, str] = {
    # =====================================================================
    # Block I — Query-performance prediction (FR-170 .. FR-177)
    # Pre-retrieval and post-retrieval predictors that estimate how well a
    # ranker will perform on a given query. Used as confidence signals.
    # =====================================================================
    # FR-170 — Query Clarity Score
    # Research basis: Cronen-Townsend & Croft (SIGIR 2002). KL divergence
    # between query LM and collection LM. Starting weight 0.02 — predictor
    # is noisy on short queries; raise after diagnostics validate.
    "query_clarity.enabled": "true",
    "query_clarity.ranking_weight": "0.02",
    "query_clarity.top_k_for_qlm": "50",
    "query_clarity.smoothing_lambda": "0.6",
    "query_clarity.vocab_truncation_top_n": "500",
    # FR-171 — Weighted Information Gain (WIG)
    # Research basis: Zhou & Croft (CIKM 2007). Mean of top-k retrieval
    # scores minus the corpus baseline. Starting weight 0.02 — depends on
    # the underlying retrieval scorer being well-calibrated.
    "wig.enabled": "true",
    "wig.ranking_weight": "0.02",
    "wig.top_k": "5",
    "wig.scorer": "bm25",
    "wig.length_normalization": "true",
    # FR-172 — Normalized Query Commitment (NQC)
    # Research basis: Shtok, Kurland, Carmel (SIGIR 2009). Standard
    # deviation of top-k scores normalised by absolute corpus baseline.
    # Starting weight 0.02 — twin of WIG, same caveats.
    "nqc.enabled": "true",
    "nqc.ranking_weight": "0.02",
    "nqc.top_k": "100",
    "nqc.scorer": "bm25",
    "nqc.absolute_corpus_baseline": "true",
    # FR-173 — Simplified Clarity Score (SCS)
    # Research basis: He & Ounis (SIGIR 2004). Pre-retrieval cousin of
    # FR-170: mean negative log collection probability of distinct query
    # terms. Starting weight 0.02 — fast and cheap, low noise floor.
    "scs.enabled": "true",
    "scs.ranking_weight": "0.02",
    "scs.distinct_terms_only": "true",
    "scs.smoothing_epsilon": "1e-6",
    # FR-174 — Query Scope
    # Research basis: He & Ounis (SIGIR 2004). Negative log fraction of the
    # corpus that contains any query term. Starting weight 0.02 — cheap
    # pre-retrieval predictor based on posting-list union size.
    "query_scope.enabled": "true",
    "query_scope.ranking_weight": "0.02",
    "query_scope.use_distinct_terms": "true",
    "query_scope.empty_set_fallback": "neutral",
    # FR-175 — Query Feedback
    # Research basis: Zhou & Croft (CIKM 2007). Stability of top-k under
    # paraphrased query. Starting weight 0.02 — paraphrase generation cost
    # is the bottleneck; held conservative until cache is warm.
    "query_feedback.enabled": "true",
    "query_feedback.ranking_weight": "0.02",
    "query_feedback.top_k": "50",
    "query_feedback.paraphrase_extra_terms": "5",
    "query_feedback.paraphrase_seed": "42",
    # FR-176 — Average Inverse Collection-Term Frequency (Avg ICTF)
    # Research basis: He & Ounis (SIGIR 2004). Mean log inverse collection
    # term frequency across distinct query terms. Starting weight 0.02 —
    # very cheap, single linear pass on precomputed table.
    "avgictf.enabled": "true",
    "avgictf.ranking_weight": "0.02",
    "avgictf.distinct_terms_only": "true",
    "avgictf.smoothing_epsilon": "1e-6",
    # FR-177 — Summed Collection Query (SCQ) Predictor
    # Research basis: Zhao, Scholer, Tsegay (CIKM 2008). Sum of (1 + log tf
    # in collection) * idf for query terms. Starting weight 0.02 — same
    # family as Avg ICTF, computed from the same lookup tables.
    "scq.enabled": "true",
    "scq.ranking_weight": "0.02",
    "scq.variant": "sum",
    "scq.distinct_terms_only": "true",
    "scq.smoothing_epsilon": "1e-6",
    # =====================================================================
    # Block J — Information-theoretic divergences (FR-178 .. FR-185)
    # Term-association and distribution-comparison signals used to score
    # source/destination affinity and term co-occurrence strength.
    # =====================================================================
    # FR-178 — Pointwise Mutual Information (PMI)
    # Research basis: Church & Hanks (Computational Linguistics 1990).
    # Log of joint probability over product of marginals. Starting weight
    # 0.02 — well-known but noisy on rare pairs without smoothing.
    "pmi.enabled": "true",
    "pmi.ranking_weight": "0.02",
    "pmi.window_size_W": "10",
    "pmi.log_base": "2",
    "pmi.smoothing_epsilon": "0.5",
    # FR-179 — Normalized PMI (NPMI)
    # Research basis: Bouma (GSCL 2009). PMI divided by -log of joint
    # probability, bounded to [-1, 1]. Starting weight 0.02 — reuses PMI
    # scaffolding, slightly more stable on rare pairs.
    "npmi.enabled": "true",
    "npmi.ranking_weight": "0.02",
    "npmi.window_size_W": "10",
    "npmi.log_base": "2",
    "npmi.smoothing_epsilon": "0.5",
    "npmi.clamp_negative_to_zero": "true",
    # FR-180 — Log-Likelihood Ratio (Dunning LLR) Term Association
    # Research basis: Dunning (Computational Linguistics 1993). G^2
    # statistic on a 2x2 contingency table. Starting weight 0.02 — robust
    # for rare events; threshold ~10.83 maps to chi^2 p<0.001.
    "llr.enabled": "true",
    "llr.ranking_weight": "0.02",
    "llr.significance_threshold": "10.83",
    "llr.zero_count_handling": "skip_term",
    # FR-181 — KL Divergence (Source -> Destination)
    # Research basis: Lafferty & Zhai (SIGIR 2001). Asymmetric divergence
    # between source and destination LMs. Starting weight 0.02 — directional
    # so the source -> dest framing matters; smoothing avoids zero-mass.
    "kl_div.enabled": "true",
    "kl_div.ranking_weight": "0.02",
    "kl_div.smoothing": "jelinek_mercer",
    "kl_div.smoothing_lambda": "0.4",
    "kl_div.log_base": "2",
    "kl_div.direction": "source_to_dest",
    # FR-182 — Jensen-Shannon Divergence
    # Research basis: Lin (IEEE Trans. Inf. Theory 1991). Symmetric and
    # smoothed variant of KL. Starting weight 0.02 — safer default than
    # KL because it's symmetric and bounded.
    "js_div.enabled": "true",
    "js_div.ranking_weight": "0.02",
    "js_div.log_base": "2",
    "js_div.return_distance": "false",
    "js_div.smoothing_lambda": "0.4",
    # FR-183 — Renyi Divergence
    # Research basis: Renyi (1961). Generalised divergence parameterised
    # by alpha; alpha=0.5 yields Bhattacharyya. Starting weight 0.02 —
    # alpha=0.5 chosen because it balances tail vs. mode sensitivity.
    "renyi_div.enabled": "true",
    "renyi_div.ranking_weight": "0.02",
    "renyi_div.alpha": "0.5",
    "renyi_div.log_base": "2",
    "renyi_div.smoothing_lambda": "0.4",
    # FR-184 — Hellinger Distance
    # Research basis: Hellinger (1909). True metric on probability
    # distributions, bounded in [0, 1]. Starting weight 0.02 — preferred
    # over KL for downstream clustering because of metric property.
    "hellinger.enabled": "true",
    "hellinger.ranking_weight": "0.02",
    "hellinger.return_squared": "false",
    "hellinger.smoothing_lambda": "0.0",
    # FR-185 — Word Mover's Distance (WMD)
    # Research basis: Kusner et al. (ICML 2015). Earth-mover's distance in
    # word-embedding space. Starting weight 0.03 — slightly higher because
    # WMD captures semantic similarity beyond surface lexicon overlap.
    # Relaxed lower bound (RWMD) is used as an O(n^2) prefilter before
    # exact WMD on the top-k candidates.
    "wmd.enabled": "true",
    "wmd.ranking_weight": "0.03",
    "wmd.embedding_dim": "300",
    "wmd.use_relaxed_lower_bound": "true",
    "wmd.exact_threshold_top_k": "50",
    "wmd.distance_type": "euclidean",
    # =====================================================================
    # Block K — Site / host-level authority (FR-186 .. FR-194)
    # Graph-based authority signals on the host/site graph plus
    # site-quality boosts and penalties.
    # =====================================================================
    # FR-186 — Site-Level PageRank
    # Research basis: Brin & Page (WWW 1998), Wu & Davison (WWW 2005).
    # PageRank computed on the host graph instead of the page graph.
    # Starting weight 0.05 — site-level authority is a foundational signal
    # and the C++ implementation is well-validated.
    "site_pagerank.enabled": "true",
    "site_pagerank.ranking_weight": "0.05",
    "site_pagerank.damping": "0.85",
    "site_pagerank.max_iterations": "100",
    "site_pagerank.convergence_tol": "1e-6",
    # FR-187 — Host TrustRank
    # Research basis: Gyongyi, Garcia-Molina, Pedersen (VLDB 2004).
    # PageRank biased toward a small set of trusted seed hosts.
    # Starting weight 0.04 — depends on quality of the seed list, which is
    # a manual curation effort; raise once seed coverage is audited.
    "host_trustrank.enabled": "true",
    "host_trustrank.ranking_weight": "0.04",
    "host_trustrank.damping": "0.85",
    "host_trustrank.seed_size": "200",
    "host_trustrank.max_iterations": "50",
    # FR-188 — SpamRank Propagation
    # Research basis: Benczur, Csalogany, Sarlos (AIRWeb 2005). Forward
    # propagation of bias from spam seeds. Starting weight 0.03 — purely
    # subtractive; raise after seed list and bias_max are calibrated.
    "spamrank.enabled": "true",
    "spamrank.ranking_weight": "0.03",
    "spamrank.bias_max": "0.30",
    "spamrank.max_iterations": "30",
    "spamrank.seed_size": "500",
    # FR-189 — BadRank (Inverse PageRank)
    # Research basis: Sobek (2003), formalised by Wu & Chellapilla.
    # PageRank on the transposed host graph from spam seeds. Starting
    # weight 0.03 — twin of SpamRank, runs on transposed CSR.
    "badrank.enabled": "true",
    "badrank.ranking_weight": "0.03",
    "badrank.damping": "0.85",
    "badrank.max_iterations": "50",
    "badrank.seed_size": "500",
    # FR-190 — Host Age Boost
    # Research basis: Acharya et al. US7346839B2 (Google historical data).
    # Sigmoid boost based on host age in days vs. threshold. Starting
    # weight 0.03 — domain age is a weak but very stable quality signal.
    "host_age.enabled": "true",
    "host_age.ranking_weight": "0.03",
    "host_age.threshold_days": "365",
    "host_age.slope_beta": "0.005",
    # FR-191 — Subdomain Diversity Penalty
    # Research basis: Wu & Davison (WWW 2005) on subdomain spam patterns.
    # Penalty grows with number of thin subdomains under one root host.
    # Starting weight 0.02 — narrow signal, only fires on suspicious
    # subdomain proliferation; easily overpowered by legitimate signals.
    "subdomain_diversity.enabled": "true",
    "subdomain_diversity.ranking_weight": "0.02",
    "subdomain_diversity.gamma": "1.0",
    "subdomain_diversity.page_threshold": "5",
    "subdomain_diversity.body_length_threshold": "500",
    # FR-192 — Doorway Page Detector
    # Research basis: Google webmaster guidelines on doorway pages.
    # Composite score combining text overlap, token repeat, and cloaking
    # Jaccard. Starting weight 0.03 — penalty signal; thresholds pulled
    # straight from the spec defaults.
    "doorway_detector.enabled": "true",
    "doorway_detector.ranking_weight": "0.03",
    "doorway_detector.text_overlap_threshold": "0.7",
    "doorway_detector.token_repeat_threshold": "0.15",
    "doorway_detector.cloaking_jaccard": "0.6",
    # FR-193 — Block-Level PageRank
    # Research basis: Cai et al. (WWW 2004), Kamvar et al. on block-
    # decomposition. Two-level PageRank: local within blocks, then
    # cross-block aggregation. Starting weight 0.04 — converges 5x faster
    # than flat PR and is more stable on tightly-clustered host graphs.
    "block_pagerank.enabled": "true",
    "block_pagerank.ranking_weight": "0.04",
    "block_pagerank.damping": "0.85",
    "block_pagerank.block_unit": "host",
    "block_pagerank.max_iterations": "100",
    # FR-194 — Host Cluster Cohesion
    # Research basis: Wu & Davison (WWW 2005) — same-host link fraction
    # as a quality signal. Starting weight 0.02 — penalty applied only
    # when cohesion drops below penalty_below.
    "host_cohesion.enabled": "true",
    "host_cohesion.ranking_weight": "0.02",
    "host_cohesion.target_min": "0.50",
    "host_cohesion.penalty_below": "0.30",
    # =====================================================================
    # Block L — Anti-spam / adversarial detectors (FR-195 .. FR-203)
    # Subtractive quality guardrails that detect link-pattern manipulation,
    # cloaking, keyword stuffing, content spinning, and astroturfing.
    # =====================================================================
    # FR-195 — Link Pattern Naturalness
    # Research basis: Becchetti et al. (Web Spam Challenge 2008).
    # Detects unnatural patterns (cliques, rings, stars, wheels) in the
    # local host neighbourhood. Starting weight 0.03 — signal is strong
    # but expensive (capped at degree 200 for tractability).
    "link_naturalness.enabled": "true",
    "link_naturalness.ranking_weight": "0.03",
    "link_naturalness.min_clique_k": "4",
    "link_naturalness.min_ring_k": "5",
    "link_naturalness.neighbourhood_hops": "2",
    # FR-196 — Cloaking Detector
    # Research basis: Wu & Davison (WWW 2005), Lin (TKDE 2009).
    # Shingle-overlap divergence between browser and bot fetches.
    # Starting weight 0.03 — high precision but only fires when both
    # fetches are available; otherwise inert.
    "cloaking.enabled": "true",
    "cloaking.ranking_weight": "0.03",
    "cloaking.shingle_k": "4",
    "cloaking.threshold": "0.30",
    "cloaking.use_cosine_fallback": "true",
    # FR-197 — Link-Farm Ring Detector
    # Research basis: Tarjan SCC (1972), Saito et al. on link-farm SCCs.
    # Identifies dense strongly-connected components in the host graph.
    # Starting weight 0.03 — penalty grows with SCC density; lambda
    # controls penalty curve shape.
    "link_farm.enabled": "true",
    "link_farm.ranking_weight": "0.03",
    "link_farm.min_scc_size": "3",
    "link_farm.density_threshold": "0.6",
    "link_farm.lambda": "0.8",
    # FR-198 — Keyword Stuffing Detector
    # Research basis: Fetterly, Manasse, Najork (WebDB 2005). KL
    # divergence of document term distribution from corpus baseline.
    # Starting weight 0.03 — top_k_stuff_terms surfaces the worst
    # offenders for diagnostics; tau tunes false-positive rate.
    "keyword_stuffing.enabled": "true",
    "keyword_stuffing.ranking_weight": "0.03",
    "keyword_stuffing.alpha": "6.0",
    "keyword_stuffing.tau": "0.30",
    "keyword_stuffing.dirichlet_mu": "2000",
    "keyword_stuffing.top_k_stuff_terms": "5",
    # FR-199 — Content Spin Detector
    # Research basis: Bendersky et al. (WWW 2011) on near-duplicate
    # content detection. MinHash + LSH on shingle sets to flag spun
    # content. Starting weight 0.03 — tuned for high precision via
    # tau=0.55 (well above incidental near-duplicate rate).
    "content_spin.enabled": "true",
    "content_spin.ranking_weight": "0.03",
    "content_spin.shingle_k": "5",
    "content_spin.minhash_K": "256",
    "content_spin.tau": "0.55",
    "content_spin.lsh_bands": "32",
    "content_spin.lsh_rows": "8",
    # FR-200 — Sybil Attack Detector
    # Research basis: Yu et al. SybilGuard (SIGCOMM 2006), SybilLimit
    # (S&P 2008). Random walks from honest seeds to estimate sybil
    # likelihood. Starting weight 0.02 — applies only on community/
    # author-graph signals; threshold 0.50 is decision midpoint.
    "sybil.enabled": "true",
    "sybil.ranking_weight": "0.02",
    "sybil.walk_count_r": "256",
    "sybil.walk_length_factor": "1.0",
    "sybil.honest_seed_count": "32",
    "sybil.threshold": "0.50",
    # FR-201 — Astroturf Pattern Detector
    # Research basis: Ratkiewicz et al. (ICWSM 2011) on coordinated
    # campaigns. Weighted linear blend of share-ratio, account-age,
    # burstiness, and clustering features through a sigmoid. Starting
    # weight 0.02 — feature weights sum to 1.0 (0.30+0.20+0.30+0.20).
    "astroturf.enabled": "true",
    "astroturf.ranking_weight": "0.02",
    "astroturf.w_share_ratio": "0.30",
    "astroturf.w_account_age": "0.20",
    "astroturf.w_burstiness": "0.30",
    "astroturf.w_clustering": "0.20",
    "astroturf.tau_age_days": "30.0",
    "astroturf.tau_decision": "0.50",
    "astroturf.alpha_sigmoid": "4.0",
    # FR-202 — Clickbait Classifier
    # Research basis: Chakraborty et al. (ASONAM 2016), Potthast et al.
    # (ECIR 2018). Linear SVM on hyperbolic-lexicon and POS features
    # over titles. Starting weight 0.03 — model artefact path is the
    # spec default; classifier output is bounded in [0, 1].
    "clickbait.enabled": "true",
    "clickbait.ranking_weight": "0.03",
    "clickbait.tau_decision": "0.50",
    "clickbait.model_path": "models/clickbait_svm_v1.json",
    "clickbait.hyperbolic_lexicon": "data/clickbait_hyperbolic.txt",
    # FR-203 — Content Farm Detector
    # Research basis: Yang & Wang (ICWE 2014). LDA-based topic mass on
    # a low-quality topic list per source. Starting weight 0.03 — depth
    # normaliser maps source size into a bounded score.
    "content_farm.enabled": "true",
    "content_farm.ranking_weight": "0.03",
    "content_farm.lda_topic_count": "100",
    "content_farm.lq_topic_path": "data/low_quality_topics.json",
    "content_farm.depth_norm": "4.0",
    "content_farm.n_max": "10000",
}
