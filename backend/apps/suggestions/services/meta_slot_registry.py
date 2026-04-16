"""
FR-225 Meta Slot Registry.

Defines which meta-algorithms belong to which stage slot and how they rotate.

rotation_mode options:
  "single_active"  — Only one meta drives at a time. Others wait in queue.
                     A monthly tournament picks the best based on NDCG@10.
  "all_active"     — All members run sequentially and complement each other.
                     No tournament needed; no member fights another.
"""

from dataclasses import dataclass


@dataclass
class MetaSlotConfig:
    members: list[str]
    active_default: str  # meta_id of the current winner, or "all" for all_active slots
    rotation_mode: str  # "single_active" | "all_active"
    description: str = ""
    pinned: bool = False  # operator manual override — skip tournament when True


# ---------------------------------------------------------------------------
# Registry — 36 stage slots covering META-40 through META-249
# ---------------------------------------------------------------------------
META_SLOT_REGISTRY: dict[str, MetaSlotConfig] = {
    # ── Optimisers (single_active) ─────────────────────────────────────────
    "second_order_optimizer": MetaSlotConfig(
        members=[
            "newton",
            "gauss_newton",
            "levenberg_marquardt",
            "lbfgs_b",
            "bfgs",
            "fletcher_reeves_cg",
        ],
        active_default="lbfgs_b",
        rotation_mode="single_active",
        description="Second-order gradient methods for weight tuning.",
    ),
    # ── Loss functions (single_active) ────────────────────────────────────
    "loss_function": MetaSlotConfig(
        members=["approx_ndcg", "lambda_loss", "ranknet", "softmax_loss", "focal_loss"],
        active_default="lambda_loss",
        rotation_mode="single_active",
        description="Listwise / pairwise loss functions for learning-to-rank.",
    ),
    # ── Calibrators (single_active) ───────────────────────────────────────
    "calibrator": MetaSlotConfig(
        members=[
            "platt_scaling",
            "isotonic_regression",
            "beta_calibration",
            "temperature_scaling",
        ],
        active_default="platt_scaling",
        rotation_mode="single_active",
        description="Post-hoc score calibration to produce well-calibrated probabilities.",
    ),
    # ── Learning-rate schedulers (single_active) ──────────────────────────
    "lr_scheduler": MetaSlotConfig(
        members=[
            "cosine_annealing",
            "one_cycle",
            "step_decay",
            "warmup_cosine",
            "cyclical_lr",
        ],
        active_default="cosine_annealing",
        rotation_mode="single_active",
        description="Learning-rate schedule for gradient-based meta-optimisers.",
    ),
    # ── Hyperparameter optimisation (single_active) ───────────────────────
    "hyperparameter_optimizer": MetaSlotConfig(
        members=[
            "bayesian_hpo",
            "hyperband",
            "successive_halving",
            "random_search",
            "tpe",
        ],
        active_default="bayesian_hpo",
        rotation_mode="single_active",
        description="Outer-loop HPO strategy for meta-algorithm configuration.",
    ),
    # ── Reinforcement learning (single_active) ────────────────────────────
    "rl_policy": MetaSlotConfig(
        members=["ucb1", "thompson_sampling", "epsilon_greedy", "exp3"],
        active_default="ucb1",
        rotation_mode="single_active",
        description="Bandit / RL policy for explore-exploit reranking (FR-013).",
    ),
    # ── Matrix factorisation (single_active) ──────────────────────────────
    "matrix_factorization": MetaSlotConfig(
        members=["als", "sgd_mf", "bpr", "warp"],
        active_default="als",
        rotation_mode="single_active",
        description="Collaborative-filtering factorisation for behavioural co-occurrence.",
    ),
    # ── Dimensionality reduction (single_active) ──────────────────────────
    "dimensionality_reduction": MetaSlotConfig(
        members=["pca", "umap", "tsne", "autoencoder_dim"],
        active_default="pca",
        rotation_mode="single_active",
        description="Embedding compression before FAISS indexing.",
    ),
    # ── Streaming / incremental trees (single_active) ─────────────────────
    "streaming_tree": MetaSlotConfig(
        members=["hoeffding_tree", "arf", "mondrian_forest", "lccrf"],
        active_default="hoeffding_tree",
        rotation_mode="single_active",
        description="Online-learning tree for incremental reranking updates.",
    ),
    # ── Metric learning (single_active) ───────────────────────────────────
    "metric_learning": MetaSlotConfig(
        members=["triplet_loss", "contrastive_loss", "arcface", "proto_net"],
        active_default="triplet_loss",
        rotation_mode="single_active",
        description="Distance-metric learning for embedding space fine-tuning.",
    ),
    # ── Ensembling (single_active) ────────────────────────────────────────
    "ensembler": MetaSlotConfig(
        members=["stacking", "blending", "voting", "bayesian_model_averaging"],
        active_default="blending",
        rotation_mode="single_active",
        description="Ensemble strategy for combining multiple ranker outputs.",
    ),
    # ── Graph propagation (single_active) ─────────────────────────────────
    "graph_propagation": MetaSlotConfig(
        members=["label_propagation", "deep_pagerank", "pixie_random_walk", "node2vec"],
        active_default="pixie_random_walk",
        rotation_mode="single_active",
        description="Graph-based authority propagation for click-distance scoring.",
    ),
    # ── Feature attribution (all_active) ──────────────────────────────────
    "feature_attribution": MetaSlotConfig(
        members=[
            "permutation_importance",
            "shap_kernel",
            "lime",
            "integrated_gradients",
            "mdi_importance",
        ],
        active_default="all",
        rotation_mode="all_active",
        description="Complementary attribution methods run sequentially for explainability.",
    ),
    # ── Anomaly detection (all_active) ────────────────────────────────────
    "anomaly_detection": MetaSlotConfig(
        members=["isolation_forest", "lof", "one_class_svm", "autoencoder_anomaly"],
        active_default="all",
        rotation_mode="all_active",
        description="Complementary anomaly detectors for outlier suppression.",
    ),
    # ── Data augmentation (all_active) ────────────────────────────────────
    "data_augmentation": MetaSlotConfig(
        members=["synonym_swap", "back_translation", "mixup", "eda"],
        active_default="all",
        rotation_mode="all_active",
        description="Complementary augmentation strategies for training-data diversity.",
    ),
    # ── Initialisation / normalisation (all_active) ───────────────────────
    "initializer_normalizer": MetaSlotConfig(
        members=["he_init", "xavier_init", "batch_norm", "layer_norm", "spectral_norm"],
        active_default="all",
        rotation_mode="all_active",
        description="Complementary weight-init and normalisation passes.",
    ),
    # ── Feature selection (all_active) ────────────────────────────────────
    "feature_selection": MetaSlotConfig(
        members=["rfe", "lasso_selection", "mutual_info_selection", "boruta"],
        active_default="all",
        rotation_mode="all_active",
        description="Complementary feature-selection passes before ranking.",
    ),
    # ── Information-theoretic criteria (all_active) ───────────────────────
    "info_theoretic": MetaSlotConfig(
        members=["mutual_info", "kl_divergence", "js_divergence", "normalized_entropy"],
        active_default="all",
        rotation_mode="all_active",
        description="Complementary info-theoretic signal enrichers.",
    ),
    # ── Causal estimators (all_active) ────────────────────────────────────
    "causal_estimator": MetaSlotConfig(
        members=["doubly_robust", "ipw", "tarnet", "dragonnet"],
        active_default="all",
        rotation_mode="all_active",
        description="Complementary causal-inference estimators for debiased scoring.",
    ),
    # ── Active learning (all_active) ──────────────────────────────────────
    "active_learning": MetaSlotConfig(
        members=["uncertainty_sampling", "query_by_committee", "core_set", "badge"],
        active_default="all",
        rotation_mode="all_active",
        description="Complementary active-learning acquisition strategies.",
    ),
    # ── Validation / population-based training (all_active) ───────────────
    "validation_strategy": MetaSlotConfig(
        members=["stratified_kfold", "time_series_cv", "pbt", "asha"],
        active_default="all",
        rotation_mode="all_active",
        description="Complementary validation and population-based training strategies.",
    ),
    # ── Sampling (all_active) ─────────────────────────────────────────────
    "sampler": MetaSlotConfig(
        members=[
            "oversampling_smote",
            "undersampling_enn",
            "class_weight_rebalance",
            "focal_resampling",
        ],
        active_default="all",
        rotation_mode="all_active",
        description="Complementary class-imbalance samplers.",
    ),
    # ── Semi-supervised learning (single_active) ──────────────────────────
    "semi_supervised": MetaSlotConfig(
        members=["label_spreading", "self_training", "mean_teacher", "pseudo_label"],
        active_default="label_spreading",
        rotation_mode="single_active",
        description="Semi-supervised method for low-annotation regimes.",
    ),
    # ── Knowledge distillation (single_active) ────────────────────────────
    "knowledge_distillation": MetaSlotConfig(
        members=[
            "response_distillation",
            "feature_distillation",
            "relation_distillation",
        ],
        active_default="response_distillation",
        rotation_mode="single_active",
        description="Distillation strategy for compressing large embeddings.",
    ),
    # ── Contrastive pre-training (single_active) ──────────────────────────
    "contrastive_pretraining": MetaSlotConfig(
        members=["simcse", "supcon", "moco", "byol"],
        active_default="simcse",
        rotation_mode="single_active",
        description="Contrastive pre-training objective for embedding fine-tuning.",
    ),
    # ── Prompt / context expansion (single_active) ────────────────────────
    "prompt_expander": MetaSlotConfig(
        members=[
            "query_expansion_bow",
            "query_expansion_lm",
            "pseudo_relevance_feedback",
        ],
        active_default="query_expansion_bow",
        rotation_mode="single_active",
        description="Query/context expansion before embedding lookup.",
    ),
    # ── Re-ranking fusion (single_active) ─────────────────────────────────
    "reranking_fusion": MetaSlotConfig(
        members=["rrf", "combsum", "combmnz", "bordafuse"],
        active_default="rrf",
        rotation_mode="single_active",
        description="Score fusion strategy when multiple ranker outputs are combined.",
    ),
    # ── Diversity / MMR variant (single_active) ───────────────────────────
    "diversity_reranker": MetaSlotConfig(
        members=["mmr", "dpp", "greedy_coverage", "bounded_greedy"],
        active_default="mmr",
        rotation_mode="single_active",
        description="Diversity-aware reranker for the final suggestion slate.",
    ),
    # ── Graph attention (single_active) ───────────────────────────────────
    "graph_attention": MetaSlotConfig(
        members=["gat", "graphsage", "gcn", "han"],
        active_default="gat",
        rotation_mode="single_active",
        description="Graph neural network for structural embedding enrichment.",
    ),
    # ── Cross-encoder reranker (single_active) ────────────────────────────
    "cross_encoder": MetaSlotConfig(
        members=["bert_cross", "distilbert_cross", "minilm_cross", "deberta_cross"],
        active_default="minilm_cross",
        rotation_mode="single_active",
        description="Cross-encoder fine-ranking layer applied to the top-K candidates.",
    ),
    # ── Sparse retrieval (single_active) ──────────────────────────────────
    "sparse_retriever": MetaSlotConfig(
        members=["bm25", "bm25_plus", "tfidf_vsm", "ql_dirichlet"],
        active_default="bm25",
        rotation_mode="single_active",
        description="Sparse lexical retrieval method for keyword recall.",
    ),
    # ── Dense retrieval (single_active) ───────────────────────────────────
    "dense_retriever": MetaSlotConfig(
        members=["faiss_flat", "faiss_ivf", "faiss_hnsw", "scann"],
        active_default="faiss_hnsw",
        rotation_mode="single_active",
        description="Dense ANN index strategy for embedding recall.",
    ),
    # ── Tokeniser / text normaliser (single_active) ───────────────────────
    "tokenizer": MetaSlotConfig(
        members=["wordpiece", "bpe", "unigram_lm", "spacy_tokenizer"],
        active_default="wordpiece",
        rotation_mode="single_active",
        description="Tokenisation strategy for text pre-processing.",
    ),
    # ── Deduplication / clustering (single_active) ────────────────────────
    "deduplication": MetaSlotConfig(
        members=["simhash", "minhash_lsh", "exact_dedup", "near_dup_faiss"],
        active_default="minhash_lsh",
        rotation_mode="single_active",
        description="Near-duplicate detection strategy for cluster suppression (FR-014).",
    ),
    # ── Feedback aggregation (single_active) ──────────────────────────────
    "feedback_aggregator": MetaSlotConfig(
        members=[
            "ema_feedback",
            "bayesian_update",
            "sliding_window_avg",
            "kalman_filter",
        ],
        active_default="ema_feedback",
        rotation_mode="single_active",
        description="How historical approval/rejection signals are aggregated into priors.",
    ),
}
