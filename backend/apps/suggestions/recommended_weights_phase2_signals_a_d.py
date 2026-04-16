"""Forward-declared Phase 2 ranking-signal weights for Blocks A through D."""
# Covers 35 ranking signals across:
#   - Block A: Classical IR scoring models (FR-099 .. FR-107, 9 signals)
#   - Block B: Proximity and dependence models (FR-108 .. FR-115, 8 signals)
#   - Block C: Graph authority and centrality (FR-116 .. FR-125, 10 signals)
#   - Block D: Result diversification (FR-126 .. FR-133, 8 signals)
#
# Each entry has a researched starting ranking_weight (typically 0.02-0.05) and
# all algorithm-specific hyperparameters from the spec's "Starting weight preset"
# section. Signals go LIVE the moment the C++ extension is wired - no manual
# weight-flip required. The auto-tuner (FR-018) adjusts the weight from there.
#
# Where the spec uses a different key prefix than the task's mapping table, the
# spec wins (the C++ extension reads the spec's key); the per-FR comment notes
# any such discrepancy.
#
# This file replaces the previous "ranking_weight=0.0" forward-declared block
# for the same FR range. After the C++ implementation lands, FR-018 should
# re-tune from the values seeded here, not from zero.

from __future__ import annotations

FORWARD_DECLARED_WEIGHTS_PHASE2_SIGNALS_A_D: dict[str, str] = {
    # =====================================================================
    # Block A - Classical IR scoring models (FR-099 .. FR-107)
    # =====================================================================
    # FR-099 - BM25+ Lower-Bound Term-Frequency Normalization
    # Lv & Zhai, CIKM 2011, DOI 10.1145/2063576.2063584
    # ranking_weight 0.03 - conservative; safe IR fallback that fixes BM25's
    # long-document under-weighting on forum threads. Same calibration knobs
    # as FR-011 BM25, plus delta floor.
    "bm25_plus.enabled": "true",
    "bm25_plus.ranking_weight": "0.03",
    "bm25_plus.k1": "1.2",
    "bm25_plus.b": "0.75",
    "bm25_plus.delta": "1.0",
    # FR-100 - BM25L Length-Unbiased Term-Frequency Normalization
    # Lv & Zhai, SIGIR 2011, DOI 10.1145/2009916.2010070
    # ranking_weight 0.03 - parallel to FR-099; corrects medium-long doc
    # over-penalty. delta=0.5 (smaller than FR-099's 1.0) because it sits
    # inside the saturation curve.
    "bm25l.enabled": "true",
    "bm25l.ranking_weight": "0.03",
    "bm25l.k1": "1.2",
    "bm25l.b": "0.75",
    "bm25l.delta": "0.5",
    # FR-101 - DFR PL2 (Poisson-Laplace 2)
    # Amati & van Rijsbergen, TOIS 2002, DOI 10.1145/582415.582416
    # ranking_weight 0.02 - low-correlation alternative to BM25 family;
    # auto-tuner gets a parameter-free-IDF feature. c=7.0 per paper short-query
    # default.
    "dfr_pl2.enabled": "true",
    "dfr_pl2.ranking_weight": "0.02",
    "dfr_pl2.c": "7.0",
    # FR-102 - DFR InL2 (Inverse-Document-Frequency + Laplace After-Effect)
    # Amati 2003 PhD thesis (Glasgow); same TOIS 2002 framework
    # ranking_weight 0.03 - rare-term-strong; pairs naturally with FR-010
    # rare-term propagation. c=7.0 per Amati 2003 Table 4.10.
    "dfr_inl2.enabled": "true",
    "dfr_inl2.ranking_weight": "0.03",
    "dfr_inl2.c": "7.0",
    # FR-103 - DFR DPH (Hypergeometric, Parameter-Free)
    # Amati, ECIR 2006, DOI 10.1007/11735106_3
    # ranking_weight 0.03 - safest cold-start DFR scorer because it has zero
    # tunables; spec keeps "no other knobs" by design.
    "dfr_dph.enabled": "true",
    "dfr_dph.ranking_weight": "0.03",
    # FR-104 - Axiomatic F2EXP Retrieval
    # Fang & Zhai, SIGIR 2006, DOI 10.1145/1148170.1148193
    # ranking_weight 0.03 - axiomatically grounded; acts as sanity floor in
    # the LTR ensemble. k=0.35, s=0.5 per Fang & Zhai 2004 Table 2.
    "axiomatic_f2exp.enabled": "true",
    "axiomatic_f2exp.ranking_weight": "0.03",
    "axiomatic_f2exp.k": "0.35",
    "axiomatic_f2exp.s": "0.5",
    # FR-105 - Two-Stage Language Model
    # Zhai & Lafferty, SIGIR 2002, DOI 10.1145/564376.564387
    # ranking_weight 0.04 - probabilistic LM with explicit per-stage
    # explainability; well-validated baseline. mu=2500, lambda_jm=0.7
    # (short-query default).
    "two_stage_lm.enabled": "true",
    "two_stage_lm.ranking_weight": "0.04",
    "two_stage_lm.mu": "2500",
    "two_stage_lm.lambda_jm": "0.7",
    # FR-106 - Positional Language Model
    # Lv & Zhai, SIGIR 2009, DOI 10.1145/1571941.1572005
    # ranking_weight 0.03 - position-aware LM rewards docs where query terms
    # cluster in opening positions (forum titles/OP body). Spec uses prefix
    # "plm.*" not the task table's "positional_lm.*" - honoring spec.
    "plm.enabled": "true",
    "plm.ranking_weight": "0.03",
    "plm.kernel": "gaussian",
    "plm.sigma": "50",
    "plm.mu": "2500",
    "plm.aggregation": "best_pos",
    # FR-107 - Relevance Language Model (RM3)
    # Lavrenko & Croft, SIGIR 2001, DOI 10.1145/383952.383972
    # ranking_weight 0.03 - per-query expansion catches synonyms missed by
    # short anchor text; complements FR-009 offline anchor vocabulary.
    # k=10, m=50, alpha=0.5 per Abdul-Jaleel et al. 2004 RM3.
    "rm3.enabled": "true",
    "rm3.ranking_weight": "0.03",
    "rm3.k_feedback_docs": "10",
    "rm3.m_expansion_terms": "50",
    "rm3.alpha_mix": "0.5",
    # =====================================================================
    # Block B - Proximity and dependence models (FR-108 .. FR-115)
    # =====================================================================
    # FR-108 - Sequential Dependence Model (SDM)
    # Metzler & Croft, SIGIR 2005, DOI 10.1145/1076034.1076115
    # ranking_weight 0.04 - strict generalisation of unigram LM; lambda
    # defaults from paper section 3.3 (T=0.85, O=0.10, U=0.05). Strong
    # baseline for term-dependence retrieval.
    "sdm.enabled": "true",
    "sdm.ranking_weight": "0.04",
    "sdm.lambda_T": "0.85",
    "sdm.lambda_O": "0.10",
    "sdm.lambda_U": "0.05",
    "sdm.mu": "2500",
    "sdm.uw_window": "8",
    # FR-109 - Weighted Sequential Dependence Model (WSDM)
    # Bendersky, Metzler, Croft, WSDM 2010, DOI 10.1145/1718487.1718492
    # ranking_weight 0.03 - per-pair learned lambda; cold-start defaults
    # equal SDM (bias-only weights, idf coefficients zero). Spec uses prefix
    # "wsdm.*" not the task table's "wsdm_weighted.*" - honoring spec.
    "wsdm.enabled": "true",
    "wsdm.ranking_weight": "0.03",
    "wsdm.lambda_T_bias": "0.85",
    "wsdm.lambda_O_bias": "0.10",
    "wsdm.lambda_U_bias": "0.05",
    "wsdm.lambda_T_idf": "0.0",
    "wsdm.lambda_O_idf": "0.0",
    "wsdm.lambda_U_idf": "0.0",
    "wsdm.mu": "2500",
    "wsdm.uw_window": "8",
    # FR-110 - Full Dependence Model (FDM)
    # Metzler & Croft, SIGIR 2005, DOI 10.1145/1076034.1076115 (variant)
    # ranking_weight 0.03 - all-subsets MRF; more expensive than SDM, so
    # weight kept slightly lower until benchmarks show net win. K_max=6
    # caps subset blowup; longer queries silently fall back to SDM. Spec
    # uses prefix "fdm.*" not the task table's "full_dependence.*" -
    # honoring spec.
    "fdm.enabled": "true",
    "fdm.ranking_weight": "0.03",
    "fdm.lambda_T": "0.80",
    "fdm.lambda_O": "0.10",
    "fdm.lambda_U": "0.10",
    "fdm.mu": "2500",
    "fdm.uw_window_per_term": "4",
    "fdm.max_query_len": "6",
    # FR-111 - BM25TP (BM25 + Term Proximity)
    # Rasolofo & Savoy, ECIR 2003, DOI 10.1007/3-540-36618-0_15
    # ranking_weight 0.04 - cheapest proximity add-on (single position pass);
    # universally compatible with any BM25 base. window=5 per paper's
    # "minimal context" default.
    "bm25tp.enabled": "true",
    "bm25tp.ranking_weight": "0.04",
    "bm25tp.k1": "1.2",
    "bm25tp.b": "0.75",
    "bm25tp.window": "5",
    # FR-112 - MinSpan Proximity Score
    # Tao & Zhai, SIGIR 2007, DOI 10.1145/1277741.1277794
    # ranking_weight 0.03 - intuitive whole-query span signal; corpus-free,
    # cheap. alpha=0.3 per paper section 4.1 grid search. Spec uses prefix
    # "minspan.*" not the task table's "minspan_prox.*" - honoring spec.
    "minspan.enabled": "true",
    "minspan.ranking_weight": "0.03",
    "minspan.alpha": "0.3",
    "minspan.usage": "standalone",
    # FR-113 - Ordered Span Proximity (Buttcher-Clarke-Lushman)
    # Buttcher, Clarke, Lushman, SIGIR 2006, DOI 10.1145/1148170.1148285
    # ranking_weight 0.03 - order-aware proximity; pairs with FR-112 for
    # full coverage. Spec uses prefix "osp.*" not the task table's
    # "ordered_span_prox.*" - honoring spec.
    "osp.enabled": "true",
    "osp.ranking_weight": "0.03",
    "osp.distance_decay": "inverse_square",
    "osp.idf_weighted": "true",
    # FR-114 - BoolProx (Boolean Conjunction Weighted by Proximity)
    # Svore, Kanani, Khan, SIGIR 2010, DOI 10.1145/1835449.1835477
    # ranking_weight 0.02 - soft-AND multiplied by proximity factor;
    # conservative because soft-AND can zero out scores when one query term
    # is missing. gamma=0.5, beta=1.0 per paper section 4.1.
    "boolprox.enabled": "true",
    "boolprox.ranking_weight": "0.02",
    "boolprox.gamma": "0.5",
    "boolprox.beta": "1.0",
    # FR-115 - Markov Random Field Per-Field Ranking
    # Huston & Croft, CIKM 2014, DOI 10.1145/2661829.2661888
    # ranking_weight 0.04 - per-field SDM with field-specific mu and lambda;
    # critical for forums where titles/OP body outweigh reply bodies. All
    # defaults from Huston & Croft 2013 section 4 (web-data settings).
    "mrf_per_field.enabled": "true",
    "mrf_per_field.ranking_weight": "0.04",
    "mrf_per_field.fields": "title,body,anchor,heading",
    "mrf_per_field.w_title": "0.4",
    "mrf_per_field.w_body": "0.4",
    "mrf_per_field.w_anchor": "0.15",
    "mrf_per_field.w_heading": "0.05",
    "mrf_per_field.lambda_T_title": "0.80",
    "mrf_per_field.lambda_O_title": "0.15",
    "mrf_per_field.lambda_U_title": "0.05",
    "mrf_per_field.lambda_T_body": "0.85",
    "mrf_per_field.lambda_O_body": "0.10",
    "mrf_per_field.lambda_U_body": "0.05",
    "mrf_per_field.mu_title": "100",
    "mrf_per_field.mu_body": "2500",
    "mrf_per_field.mu_anchor": "500",
    "mrf_per_field.mu_heading": "200",
    "mrf_per_field.uw_window": "8",
    # =====================================================================
    # Block C - Graph authority and centrality (FR-116 .. FR-125)
    # =====================================================================
    # FR-116 - HITS Authority Score
    # Kleinberg, JACM 1999, DOI 10.1145/324133.324140
    # ranking_weight 0.03 - destination-side hub-converged authority;
    # uncorrelated with FR-006 PageRank because HITS runs on the topic-induced
    # subgraph. subgraph_size=200 per typical anchor candidate pool.
    "hits_authority.enabled": "true",
    "hits_authority.ranking_weight": "0.03",
    "hits_authority.subgraph_size": "200",
    "hits_authority.max_iterations": "50",
    "hits_authority.convergence_tolerance": "1e-6",
    # FR-117 - HITS Hub Score
    # Kleinberg, JACM 1999, DOI 10.1145/324133.324140
    # ranking_weight 0.02 - host-side score; lighter weight than authority
    # because hub character is a quality cue more than a relevance signal.
    "hits_hub.enabled": "true",
    "hits_hub.ranking_weight": "0.02",
    "hits_hub.subgraph_size": "200",
    "hits_hub.max_iterations": "50",
    "hits_hub.convergence_tolerance": "1e-6",
    # FR-118 - TrustRank
    # Gyongyi, Garcia-Molina, Pedersen, VLDB 2004
    # ranking_weight 0.04 - trust propagation from operator-curated seeds
    # is a strong quality signal; safe default because it only rewards.
    # damping=0.85 per paper.
    "trustrank.enabled": "true",
    "trustrank.ranking_weight": "0.04",
    "trustrank.damping": "0.85",
    "trustrank.max_iterations": "100",
    "trustrank.convergence_tolerance": "1e-7",
    "trustrank.seed_source": "operator_curated",
    # FR-119 - Anti-TrustRank
    # Krishnan & Raj, AIRWeb 2006
    # ranking_weight 0.02 - subtractive guard from moderator-flagged seeds;
    # conservative because false-positive bad seeds can wrongly demote
    # legitimate pages. Combine via trust_minus_distrust at scoring time.
    "anti_trustrank.enabled": "true",
    "anti_trustrank.ranking_weight": "0.02",
    "anti_trustrank.damping": "0.85",
    "anti_trustrank.max_iterations": "100",
    "anti_trustrank.convergence_tolerance": "1e-7",
    "anti_trustrank.distrust_lambda": "1.0",
    "anti_trustrank.bad_seed_source": "moderator_flags",
    # FR-120 - SALSA (Stochastic Approach for Link-Structure Analysis)
    # Lempel & Moran, WWW9 2000, DOI 10.1016/S1389-1286(00)00034-7
    # ranking_weight 0.03 - TKC-resistant successor to HITS; starts equal
    # to FR-116 then auto-tuner can favour SALSA on graphs where tightly-
    # knit cliques distort HITS. score_axis=authority for destination scoring.
    "salsa.enabled": "true",
    "salsa.ranking_weight": "0.03",
    "salsa.subgraph_size": "200",
    "salsa.score_axis": "authority",
    # FR-121 - SimRank
    # Jeh & Widom, KDD 2002, DOI 10.1145/775047.775126
    # ranking_weight 0.03 - structural-twin signal (text-agnostic); useful
    # when semantic similarity is weak but link graph clearly groups pages.
    # decay_C=0.8, max_iter=5 (5% error per paper Theorem 4.2).
    "simrank.enabled": "true",
    "simrank.ranking_weight": "0.03",
    "simrank.decay_C": "0.8",
    "simrank.max_iterations": "5",
    "simrank.candidate_pair_cap": "10000",
    # FR-122 - Katz Centrality
    # Katz, Psychometrika 1953, DOI 10.1007/BF02289026
    # ranking_weight 0.02 - all-paths attenuated walk count; conservative
    # weight because Katz can saturate on dense subgraphs. alpha=0.05 per
    # spec's "safe for forum graphs" note (must satisfy alpha<1/lambda_max).
    # Spec uses prefix "katz.*" matching the task table.
    "katz.enabled": "true",
    "katz.ranking_weight": "0.02",
    "katz.alpha": "0.05",
    "katz.beta": "1.0",
    "katz.max_iterations": "200",
    "katz.convergence_tolerance": "1e-7",
    # FR-123 - K-Shell Coreness
    # Kitsak et al., Nature Physics 2010, DOI 10.1038/nphys1746
    # ranking_weight 0.03 - combinatorial density measure that Kitsak et al.
    # showed beats PageRank/betweenness for true influence prediction. Spec
    # uses prefix "k_shell.*" not the task table's "kshell.*" - honoring spec.
    "k_shell.enabled": "true",
    "k_shell.ranking_weight": "0.03",
    "k_shell.directionality": "undirected",
    "k_shell.normalisation": "max_coreness",
    # FR-124 - Harmonic Centrality
    # Marchiori & Latora, Physica A 2000, DOI 10.1016/S0378-4371(00)00311-3
    # ranking_weight 0.03 - global closeness measure that handles disconnected
    # forum subgraphs cleanly (closeness centrality cannot). bfs_depth_cap=8
    # (typical forum diameter is 4-6). Spec uses prefix "harmonic_centrality.*"
    # not the task table's "harmonic.*" - honoring spec.
    "harmonic_centrality.enabled": "true",
    "harmonic_centrality.ranking_weight": "0.03",
    "harmonic_centrality.weighted": "false",
    "harmonic_centrality.bfs_depth_cap": "8",
    # FR-125 - LeaderRank
    # Lu, Zhang, Yeung, Zhou, PLOS ONE 2011, DOI 10.1371/journal.pone.0021202
    # ranking_weight 0.03 - parameter-free PageRank variant that fixes
    # dangling-node leakage; provably more robust to graph perturbations.
    # No damping factor by design.
    "leaderrank.enabled": "true",
    "leaderrank.ranking_weight": "0.03",
    "leaderrank.max_iterations": "100",
    "leaderrank.convergence_tolerance": "1e-7",
    # =====================================================================
    # Block D - Result diversification (FR-126 .. FR-133)
    # =====================================================================
    # FR-126 - IA-Select Diversification
    # Agrawal, Gollapudi, Halverson, Ieong, WSDM 2009,
    # DOI 10.1145/1498759.1498766
    # ranking_weight 0.03 - greedy aspect-coverage maximisation with
    # (1-1/e) approximation guarantee. Operates after candidate ranking,
    # so weight is moderate. target_slate_size=10 (operator-tunable).
    "ia_select.enabled": "true",
    "ia_select.ranking_weight": "0.03",
    "ia_select.aspect_source": "host_classified_topics",
    "ia_select.satisfaction_proxy": "semantic_similarity",
    "ia_select.target_slate_size": "10",
    # FR-127 - xQuAD Aspect Diversification
    # Santos, Macdonald, Ounis, WWW 2010, DOI 10.1145/1772690.1772780
    # ranking_weight 0.04 - explicit relevance-vs-diversity trade-off via
    # lambda; safer default than pure IA-Select because lambda=0.5 keeps
    # half the weight on relevance.
    "xquad.enabled": "true",
    "xquad.ranking_weight": "0.04",
    "xquad.lambda_diversity": "0.5",
    "xquad.aspect_source": "host_classified_topics",
    "xquad.target_slate_size": "10",
    # FR-128 - PM2 Proportional Diversification
    # Dang & Croft, SIGIR 2012, DOI 10.1145/2348283.2348296
    # ranking_weight 0.03 - Sainte-Lague proportional aspect representation;
    # gives operators predictable topic mix.
    "pm2.enabled": "true",
    "pm2.ranking_weight": "0.03",
    "pm2.lambda_proportionality": "0.5",
    "pm2.aspect_source": "host_classified_topics",
    "pm2.target_slate_size": "10",
    # FR-129 - DPP (Determinantal Point Process) Diversification
    # Kulesza & Taskar, FnT 2012, DOI 10.1561/2200000044
    # ranking_weight 0.03 - aspect-free; volume-based diversity using only
    # the similarity kernel we already compute. Greedy MAP per Chen et al.
    # 2018 NeurIPS gives (1-1/e) bound.
    "dpp.enabled": "true",
    "dpp.ranking_weight": "0.03",
    "dpp.kernel_source": "semantic_embedding_cosine",
    "dpp.relevance_weight_alpha": "1.0",
    "dpp.target_slate_size": "10",
    # FR-130 - Submodular Coverage Reranking
    # Lin & Bilmes, ACL-HLT 2011 (greedy bound: Nemhauser et al. 1978)
    # ranking_weight 0.03 - unified diversification framework with
    # provable (1-1/e) approximation. Spec uses prefix
    # "submodular_coverage.*" not the task table's "submod_cov.*" -
    # honoring spec.
    "submodular_coverage.enabled": "true",
    "submodular_coverage.ranking_weight": "0.03",
    "submodular_coverage.alpha_saturation": "0.5",
    "submodular_coverage.coverage_diversity_mix": "0.5",
    "submodular_coverage.cluster_count_K": "10",
    "submodular_coverage.target_slate_size": "10",
    # FR-131 - Portfolio Theory Reranking
    # Wang & Zhu, SIGIR 2009, DOI 10.1145/1571941.1571963
    # ranking_weight 0.02 - Markowitz mean-variance reranking with single
    # risk-aversion knob. Conservative weight because uncertainty estimates
    # (sigma_i) are noisy until ranker outputs stabilise.
    "portfolio.enabled": "true",
    "portfolio.ranking_weight": "0.02",
    "portfolio.risk_aversion_b": "1.0",
    "portfolio.uncertainty_source": "ranking_score_std",
    "portfolio.correlation_source": "embedding_cosine",
    "portfolio.target_slate_size": "10",
    # FR-132 - Latent Diversity Model (LDM)
    # Ashkan, Clarke, Agichtein, Guo, CIKM 2015, DOI 10.1145/2806416.2806613
    # ranking_weight 0.03 - LDA-based aspect-free diversification; works
    # without a hand-curated aspect taxonomy. T=100 per paper experiments.
    "ldm.enabled": "true",
    "ldm.ranking_weight": "0.03",
    "ldm.lda_topics_T": "100",
    "ldm.lambda_diversity": "0.5",
    "ldm.candidate_pool_size_N": "200",
    "ldm.target_slate_size": "10",
    # FR-133 - Quota-Based Diversity
    # Capannini, Nardini, Perego, Silvestri, SIGIR 2011 + VLDB 2011,
    # DOI 10.14778/1988776.1988779
    # ranking_weight 0.02 - hard min/max quota constraints; conservative
    # because operators must explicitly set quotas (empty defaults =
    # no-op). Spec uses prefix "quota_diversity.*" not the task table's
    # "quota_div.*" - honoring spec.
    "quota_diversity.enabled": "true",
    "quota_diversity.ranking_weight": "0.02",
    "quota_diversity.class_source": "destination_category",
    "quota_diversity.target_slate_size": "10",
    "quota_diversity.lower_quotas_json": "{}",
    "quota_diversity.upper_quotas_json": "{}",
}
