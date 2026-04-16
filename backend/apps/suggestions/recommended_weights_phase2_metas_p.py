"""Forward-declared Phase 2 meta-algorithm weights — Blocks P1 through Q1.

Covers META-40 through META-105 (66 keys total):
  - Block P1:  Second-order and trust-region optimisers (META-40 .. META-50)
  - Block P2:  Adaptive deep-learning optimisers (META-51 .. META-53)
  - Block P3:  Bayesian and surrogate hyperparameter optimisation (META-54 .. META-59)
  - Block P4:  Multi-objective optimisation (META-60 .. META-64)
  - Block P5:  Swarm and nature-inspired metaheuristics (META-65 .. META-69)
  - Block P6:  Online learning and streaming optimisation (META-70 .. META-75)
  - Block P7:  Listwise and smooth-rank loss surrogates (META-76 .. META-81)
  - Block P8:  Proximal, structured-sparsity regularisers (META-82 .. META-86)
  - Block P9:  Calibration (META-87 .. META-90)
  - Block P10: Learning-rate schedules (META-91 .. META-95)
  - Block P11: Ensembling and weight averaging (META-96 .. META-99)
  - Block P12: Distributionally robust optimisation (META-100 .. META-101)
  - Block Q1:  Mini-batch and sampling strategies (META-102 .. META-105)

These keys are inert until their corresponding META is implemented and an
operator selects it. They live in a separate file to keep each module under the
file-length limit.

``FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_P`` is merged into
``RECOMMENDED_PRESET_WEIGHTS`` at import time by the main module.

All keys use ``.enabled="false"`` (metas stay off until an operator selects one).

Source specs: docs/specs/meta-40-*.md through docs/specs/meta-105-*.md
"""

from __future__ import annotations

FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_P: dict[str, str] = {
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
}
