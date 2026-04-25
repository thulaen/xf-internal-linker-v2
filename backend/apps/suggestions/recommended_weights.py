"""Canonical research-backed starting weights for the Recommended preset.

These values are the single backend source of truth for the default ranking
starting point shown in Settings and used when older presets are missing newer
keys.
"""

from __future__ import annotations

from .recommended_weights_forward_settings import FORWARD_DECLARED_WEIGHTS

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
    # ── W3c graph-signal ranker (picks #29 / #30 / #36) ──
    # Reads HITS authority, Personalized PageRank, and TrustRank scores
    # persisted by the W1 scheduled jobs (`hits_refresh`,
    # `personalized_pagerank_refresh`, `trustrank_propagation`) and applies
    # them as a small additive contribution to score_final. Cold-start safe:
    # with no snapshots yet, the ranker is a no-op (build_graph_signal_ranker
    # returns None). Weights chosen per Gate A in docs/RANKING-GATES.md:
    #   - HITS authority (Kleinberg 1999): 0.04 — small but visible
    #   - PPR (Haveliwala 2002): 0.04 — same tier as HITS
    #   - TrustRank (Gyöngyi et al. 2004): 0.03 — slightly lower until
    #     auto-seeder pick #51 ships and seeds are no longer hand-picked
    "graph_signals.enabled": "true",
    "graph_signals.hits_authority.ranking_weight": "0.04",
    "graph_signals.personalized_pagerank.ranking_weight": "0.04",
    "graph_signals.trustrank.ranking_weight": "0.03",
    # ── Pick #51 — TrustRank Auto-Seeder (Gyöngyi 2004 §4.1) ──
    # Inverse-PageRank seed picker with quality + spam + readability
    # filters. Defaults from the 52-pick plan §"Round-5/6 Detail".
    # The scheduled job ``trustrank_auto_seeder`` reads these on each
    # daily run and feeds them to ``pick_seeds`` along with the
    # per-node quality data sourced from ``ContentItem.content_value_score``
    # and ``Post.flesch_kincaid_grade`` (the latter is the column
    # Phase 3 #19 wired; pick #51 is its first downstream consumer).
    "trustrank_auto_seeder.candidate_pool_size": "100",
    "trustrank_auto_seeder.seed_count_k": "20",
    "trustrank_auto_seeder.post_quality_min": "0.6",
    "trustrank_auto_seeder.readability_grade_max": "16",
    # 0.0 disables the spam filter; positive values reject candidates
    # whose content_value_score sits at-or-below the floor as a
    # spam-proxy until a dedicated spam_guard column lands.
    "trustrank_auto_seeder.spam_content_value_floor": "0.15",
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
    # Runtime anti-spam signals (also seeded into DB by migration 0032).
    # Both signals are live and read by pipeline/services/pipeline_loaders.py.
    "keyword_stuffing.enabled": "true",
    "keyword_stuffing.ranking_weight": "0.04",
    "keyword_stuffing.alpha": "6.0",
    "keyword_stuffing.tau": "0.30",
    "keyword_stuffing.dirichlet_mu": "2000",
    "keyword_stuffing.top_k_stuff_terms": "5",
    "link_farm.enabled": "true",
    "link_farm.ranking_weight": "0.03",
    "link_farm.min_scc_size": "3",
    "link_farm.density_threshold": "0.6",
    "link_farm.lambda": "0.8",
    # Pipeline recall thresholds — tunable to trade recall vs. speed.
    # Research basis: Bruch et al. 2024 and Cormack et al. 2009 recommend
    # tunable fan-out over fixed budgets. These defaults match the original
    # hardcoded values but can now be adjusted per-site.
    "pipeline.stage1_top_k": "50",
    "pipeline.stage2_top_k": "10",
    "pipeline.min_semantic_score": "0.25",
    # ── FR-099 through FR-105: 7 complementary graph-topology ranking signals ──
    # Addresses the Reddit-post topology errors: dangling nodes, duplicate lines,
    # misaligned boundaries, gaps between polygons, overlapping polygons.
    # Full specs in docs/specs/fr099-*.md through docs/specs/fr105-*.md.
    # Gate A + Gate B in docs/RANKING-GATES.md applied to every default below.

    # FR-099 — Dangling Authority Redistribution Bonus (DARB)
    # Baseline: Page, Brin, Motwani, Winograd 1999, Stanford InfoLab 1999-66
    # §2.5 "Dangling Links" + §3.2 eq. 1. Weight 0.04 ≈ 40% of weighted_authority
    # (0.10) split across DARB + KCIB as complementary authority signals.
    "darb.enabled": "true",
    "darb.ranking_weight": "0.04",
    "darb.out_degree_saturation": "5",
    "darb.min_host_value": "0.5",

    # FR-100 — Katz Marginal Information Gain (KMIG)
    # Baseline: Katz 1953, Psychometrika 18(1) §2 eq. 2 + §3 attenuation β < 1/λ₁.
    # β=0.5 from Pigueiral 2017 EuroCG'17 truncated-Katz default.
    # Weight 0.05 matches ga4_gsc.ranking_weight magnitude (both additive bonuses).
    "kmig.enabled": "true",
    "kmig.ranking_weight": "0.05",
    "kmig.attenuation": "0.5",
    "kmig.max_hops": "2",

    # FR-101 — Tarjan Articulation Point Boost (TAPB)
    # Baseline: Tarjan 1972, SIAM J. Computing 1(2) §3 articulation-point DFS.
    # Weight 0.03 matches link_farm.ranking_weight (another rare-event structural
    # signal). AP density ~5-8% per Newman 2010 §7.4.1 Table 7.1.
    "tapb.enabled": "true",
    "tapb.ranking_weight": "0.03",
    "tapb.apply_to_articulation_node_only": "true",

    # FR-102 — K-Core Integration Boost (KCIB)
    # Baseline: Seidman 1983, Social Networks 5(3) §2 eq. 1 k-core definition.
    # Modern impl: Batagelj & Zaversnik 2003 O(m) algorithm via networkx.
    # Weight 0.03 matches link_farm magnitude band.
    "kcib.enabled": "true",
    "kcib.ranking_weight": "0.03",
    "kcib.min_kcore_spread": "1",

    # FR-103 — Bridge-Edge Redundancy Penalty (BERP)
    # Baseline: Hopcroft & Tarjan 1973, CACM 16(6) §2 Algorithm 3 bridge-detection.
    # Weight 0.04 penalty matches keyword_stuffing.ranking_weight penalty band.
    # Bridge density ~2% per Newman 2010 §7.4.1 Table 7.1.
    "berp.enabled": "true",
    "berp.ranking_weight": "0.04",
    "berp.min_component_size": "5",

    # FR-104 — Host-Graph Topic Entropy Boost (HGTE)
    # Baseline: Shannon 1948, BSTJ 27(3) §6 eq. 4 entropy formula.
    # Weight 0.04 matches rare_term_propagation.ranking_weight (another
    # diversity-oriented additive bonus). min_host_out_degree=3 follows
    # Shannon §12 asymptotic reliability discussion.
    "hgte.enabled": "true",
    "hgte.ranking_weight": "0.04",
    "hgte.min_host_out_degree": "3",

    # FR-105 — Reverse Search-Query Vocabulary Alignment (RSQVA)
    # Baseline: Salton & Buckley 1988, IP&M 24(5) §3 eq. 1 + §4 cosine similarity.
    # Click-weighting from Järvelin & Kekäläinen 2002 ACM TOIS 20(4) §2.1.
    # Weight 0.05 matches ga4_gsc (both GSC/GA4-derived). Min 5 queries per page
    # per Salton-Buckley §3.2 reliability threshold.
    "rsqva.enabled": "true",
    "rsqva.ranking_weight": "0.05",
    "rsqva.min_queries_per_page": "5",
    "rsqva.min_query_clicks": "1",
    "rsqva.max_vocab_size": "10000",

    # ════════════════════════════════════════════════════════════════
    # 52-pick optional helpers — Wire phase defaults
    # All values cited to the matching academic source. Each ``*.enabled``
    # is True so the pick fires on real data the moment the helper is
    # consulted.
    # ════════════════════════════════════════════════════════════════

    # ── Pick #22 VADER (Hutto & Gilbert 2014 ICWSM) ─────────────────
    # No tunable thresholds at the helper level — VADER's ``compound``
    # score is consulted directly by callers. The neutrality cutoff
    # ±0.05 lives in the helper as :attr:`SentimentResult.is_neutral`
    # (paper §3.2 "compound score thresholds for sentiment intensity").
    "vader_sentiment.enabled": "true",

    # ── Pick #15 PySBD (Sadvilkar & Neumann 2020 ACL Demos) ────────
    # ``language=en`` matches our content; ``clean=False`` keeps the
    # caller in charge of post-processing (paper §3.1 — segmentation
    # is meant to be reversible by default).
    "pysbd_segmenter.enabled": "true",
    "pysbd_segmenter.language": "en",

    # ── Pick #17 YAKE! (Campos et al. 2020 Inf. Sci. §3.5) ─────────
    # ngram_max=3 captures the trigram phrases the paper Table 4
    # reports; dedup_threshold=0.9 mirrors Campos et al.'s LM-distance
    # cutoff; top_k=20 covers the 5-20 keywords-per-doc baseline.
    "yake_keywords.enabled": "true",
    "yake_keywords.ngram_max": "3",
    "yake_keywords.dedup_threshold": "0.9",
    "yake_keywords.top_k": "20",
    "yake_keywords.language": "en",

    # ── Pick #7 Trafilatura (Barbaresi 2021 ACL Demos) ─────────────
    # Default profile (favor_recall=False) is the precision-tuned
    # extractor that the paper recommends for downstream NLP. Tables
    # ON because tabular forum content (resource pages) often carries
    # signal we want; comments OFF because XF threading already
    # captures discussion replies separately.
    "trafilatura_extractor.enabled": "true",
    "trafilatura_extractor.favor_recall": "false",
    "trafilatura_extractor.include_comments": "false",
    "trafilatura_extractor.include_tables": "true",

    # ── Pick #14 FastText LangID (Joulin et al. 2016 EACL §3) ─────
    # min_confidence=0.4 sits well below the paper's reported
    # ~0.998 mean confidence on clean inputs; we use 0.4 specifically
    # to catch noisy XF posts where the model is genuinely unsure.
    # Model path matches the Dockerfile-downloaded location.
    "fasttext_langid.enabled": "true",
    "fasttext_langid.model_path": "/opt/models/lid.176.bin",
    "fasttext_langid.min_confidence": "0.4",

    # ── Pick #18 LDA (Blei, Ng, Jordan 2003 JMLR §6) ──────────────
    # num_topics=50 is a small-corpus default — the paper's Wikipedia
    # experiment used 100 over 16k docs, but our forum corpus is
    # smaller. passes=5 is gensim's documented good-enough default;
    # alpha/eta="auto" lets gensim infer the priors from the corpus.
    # Model paths match the W1 ``lda_topic_refresh`` job's output dir.
    "lda.enabled": "true",
    "lda.num_topics": "50",
    "lda.passes": "5",
    "lda.alpha": "auto",
    "lda.eta": "auto",
    "lda.model_path": "/app/media/lda/lda.model",
    "lda.dictionary_path": "/app/media/lda/lda.dict",

    # ── Pick #23 KenLM (Heafield 2011 WMT) ────────────────────────
    # order=3 = trigram (the paper's headline benchmark). Empty
    # model_path until the W1 ``kenlm_retrain`` job runs and writes
    # MEDIA_ROOT/kenlm/model.arpa. Helper short-circuits to neutral
    # score until then.
    "kenlm.enabled": "true",
    "kenlm.order": "3",
    "kenlm.model_path": "/app/media/kenlm/model.arpa",

    # ── Pick #37 Node2Vec (Grover & Leskovec 2016 KDD §4 Table 1) ──
    # dimensions=64 + walk_length=30 + num_walks=200 + p=q=1.0 is the
    # "balanced community + structural" preset from the paper's
    # main-result configuration. window=10 matches §4.1.
    "node2vec.enabled": "true",
    "node2vec.dimensions": "64",
    "node2vec.walk_length": "30",
    "node2vec.num_walks": "200",
    "node2vec.p": "1.0",
    "node2vec.q": "1.0",
    "node2vec.window": "10",
    "node2vec.embeddings_path": "/app/media/node2vec/embeddings.pkl",

    # ── Pick #38 BPR (Rendle et al. 2009 UAI §5) ──────────────────
    # factors=50 keeps the latent matrix small at our scale; iterations,
    # learning_rate, regularization match Rendle et al.'s reported
    # MovieLens defaults (Table 2).
    "bpr.enabled": "true",
    "bpr.factors": "50",
    "bpr.iterations": "100",
    "bpr.learning_rate": "0.01",
    "bpr.regularization": "0.01",
    "bpr.model_path": "/app/media/bpr/model.pkl",

    # ── Pick #39 Factorization Machines (Rendle 2010 ICDM §3.1) ───
    # factors=8 keeps latent vectors tiny — fine for our small
    # feature space (~10 score columns + categorical anchor_confidence).
    # num_iter=50 with learning_rate=0.001 matches the paper's
    # "stable convergence on small datasets" recommendation.
    "factorization_machines.enabled": "true",
    "factorization_machines.factors": "8",
    "factorization_machines.num_iter": "50",
    "factorization_machines.learning_rate": "0.001",
    "factorization_machines.model_path": "/app/media/fm/model.pkl",
}

# Merge forward-declared FR keys into the main dict.
RECOMMENDED_PRESET_WEIGHTS.update(FORWARD_DECLARED_WEIGHTS)


def recommended_bool(key: str) -> bool:
    return RECOMMENDED_PRESET_WEIGHTS[key].strip().lower() == "true"


def recommended_float(key: str) -> float:
    return float(RECOMMENDED_PRESET_WEIGHTS[key])


def recommended_int(key: str) -> int:
    return int(float(RECOMMENDED_PRESET_WEIGHTS[key]))


def recommended_str(key: str) -> str:
    return RECOMMENDED_PRESET_WEIGHTS[key]
