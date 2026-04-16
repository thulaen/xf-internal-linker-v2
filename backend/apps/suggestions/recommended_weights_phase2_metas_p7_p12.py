"""Forward-declared Phase 2 meta-algorithm weights — Blocks P7 through P12."""
# Covers 30 meta-algorithms across:
#   - Block P7: Listwise losses (6; winner META-77 LambdaLoss)
#   - Block P8: Regularisation (5; winner META-82 FISTA)
#   - Block P9: Calibration (4; winner META-87 Platt scaling)
#   - Block P10: LR schedulers (5; winner META-91 Cosine annealing)
#   - Block P11: Model averaging (4; winner META-96 SWA)
#   - Block P12: Robustness & sampling (6; META-100 DRO + 4 sampling methods active,
#               META-101 Wasserstein-DRO is alt to META-100)
#
# Each entry has researched starting hyperparameters. Winners default enabled=true;
# alternates default enabled=false but pre-filled. See FR-225 for rotation framework.

from __future__ import annotations

FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_P7_P12: dict[str, str] = {
    # =====================================================================
    # BLOCK P7 — LISTWISE LOSSES (META-76 to META-81)
    # =====================================================================
    # META-76 — ApproxNDCG Listwise Loss
    # Paper: Qin, Liu, Li 2010 — "A general approximation framework for direct
    # optimization of information retrieval measures." Information Retrieval 13(4).
    # Rationale: alternative; smooth-rank surrogate via per-pair sigmoid. Disabled
    # because META-77 LambdaLoss carries a stronger metric-bound theoretical guarantee.
    "approx_ndcg.enabled": "false",
    "approx_ndcg.alpha": "1.0",
    "approx_ndcg.truncation_k": "0",
    "approx_ndcg.batch_size": "32",
    "approx_ndcg.max_candidates_per_query": "1000",
    # META-77 — LambdaLoss Listwise Loss (WINNER for P7)
    # Paper: Wang, Li, Golbandi, Bendersky, Najork 2018 — "The LambdaLoss framework
    # for ranking metric optimization." CIKM 2018, pp. 1313-1322.
    # Rationale: theoretically justified upper bound on metric-weighted pairwise log
    # loss (Wang 2018 Thm 1); inherits well-behaved LambdaRank gradients with a true
    # loss function. Default enabled. metric_kind=0 selects full NDCG.
    "lambda_loss.enabled": "true",
    "lambda_loss.metric_kind": "0",
    "lambda_loss.truncation_k": "0",
    "lambda_loss.batch_size": "32",
    "lambda_loss.max_candidates_per_query": "1000",
    # META-78 — NeuralNDCG Listwise Loss
    # Paper: Pobrotyn, Bialobrzeski 2021 — "NeuralNDCG: direct optimisation of a
    # ranking metric via differentiable relaxation of sorting." arXiv:2102.07831.
    # Rationale: alternative; NeuralSort soft-permutation. Disabled in favour of
    # META-77. tau=1.0 is a moderate temperature; lower yields sharper sort.
    "neural_ndcg.enabled": "false",
    "neural_ndcg.tau": "1.0",
    "neural_ndcg.truncation_k": "0",
    "neural_ndcg.batch_size": "16",
    "neural_ndcg.max_candidates_per_query": "500",
    # META-79 — SoftRank Listwise Loss
    # Paper: Taylor, Guiver, Robertson, Minka 2008 — "SoftRank: optimizing non-smooth
    # rank metrics." WSDM 2008, pp. 77-86.
    # Rationale: alternative; Gaussian-noise rank distribution via DP. Disabled in
    # favour of META-77. sigma=1.0 balances smoothness vs fidelity.
    "softrank.enabled": "false",
    "softrank.sigma": "1.0",
    "softrank.truncation_k": "0",
    "softrank.batch_size": "8",
    "softrank.max_candidates_per_query": "200",
    # META-80 — Smooth-AP Listwise Loss
    # Paper: Brown, Xie, Kalogeiton, Zisserman 2020 — "Smooth-AP: smoothing the path
    # towards large-scale image retrieval." ECCV 2020, LNCS 12350.
    # Rationale: alternative; optimises Average Precision (binary relevance) directly.
    # Disabled for graded-relevance settings; META-77 NDCG-bound is preferred.
    "smooth_ap.enabled": "false",
    "smooth_ap.tau": "0.01",
    "smooth_ap.batch_size": "16",
    "smooth_ap.max_candidates_per_query": "2000",
    # META-81 — Listwise Cross-Entropy (ListNet Top-1)
    # Paper: Cao, Qin, Liu, Tsai, Li 2007 — "Learning to rank: from pairwise approach
    # to listwise approach." ICML 2007, pp. 129-136.
    # Rationale: alternative; cheaper O(n) Plackett-Luce top-1 cross-entropy. Disabled
    # in favour of META-77 because it lacks a metric-bound guarantee.
    "listwise_ce.enabled": "false",
    "listwise_ce.batch_size": "32",
    "listwise_ce.max_candidates_per_query": "10000",
    "listwise_ce.target_kind": "graded",
    # =====================================================================
    # BLOCK P8 — REGULARISATION (META-82 to META-86)
    # =====================================================================
    # META-82 — FISTA Proximal Gradient (WINNER for P8)
    # Paper: Beck, Teboulle 2009 — "A Fast Iterative Shrinkage-Thresholding Algorithm
    # for Linear Inverse Problems." SIAM J. Imaging Sciences 2(1):183-202.
    # Rationale: accelerated proximal gradient with O(1/t^2) convergence — strong
    # baseline for L1/elastic-net penalties. Default enabled.
    "fista.enabled": "true",
    "fista.max_iter": "1000",
    "fista.tol": "1e-6",
    "fista.lipschitz_init": "1.0",
    "fista.lipschitz_backtrack": "true",
    # META-83 — Nuclear-Norm Regularisation
    # Paper: Fazel, Hindi, Boyd 2001 — "A Rank Minimization Heuristic with
    # Application to Minimum Order System Approximation." ACC 2001.
    # Rationale: alternative; singular-value soft-threshold for low-rank matrices.
    # Disabled because no current weight matrices need rank constraints.
    "nuclear_norm.enabled": "false",
    "nuclear_norm.lambda": "0.01",
    "nuclear_norm.step": "0.1",
    "nuclear_norm.max_iter": "500",
    "nuclear_norm.tol": "1e-5",
    # META-84 — Group LASSO
    # Paper: Yuan, Lin 2006 — "Model Selection and Estimation in Regression with
    # Grouped Variables." JRSS-B 68(1):49-67.
    # Rationale: alternative; structured sparsity over feature blocks. Disabled until
    # group definitions (sections, n-gram blocks) are formalised in feature pipeline.
    "group_lasso.enabled": "false",
    "group_lasso.lambda": "0.01",
    "group_lasso.step": "0.1",
    "group_lasso.max_iter": "500",
    "group_lasso.tol": "1e-5",
    "group_lasso.weight_kind": "sqrt_size",
    # META-85 — Fused LASSO
    # Paper: Tibshirani, Saunders, Rosset, Zhu, Knight 2005 — "Sparsity and Smoothness
    # via the Fused Lasso." JRSS-B 67(1):91-108.
    # Rationale: alternative; encourages adjacent weights to share values via TV prox.
    # Disabled until ordered-feature blocks are defined (positional bins, ordered
    # importance buckets).
    "fused_lasso.enabled": "false",
    "fused_lasso.lambda1": "0.01",
    "fused_lasso.lambda2": "0.01",
    "fused_lasso.step": "0.1",
    "fused_lasso.max_iter": "500",
    "fused_lasso.tol": "1e-5",
    # META-86 — SCAD Penalty
    # Paper: Fan, Li 2001 — "Variable Selection via Nonconcave Penalized Likelihood
    # and Its Oracle Properties." JASA 96(456):1348-1360.
    # Rationale: alternative; non-convex penalty avoids LASSO bias on large coefs.
    # Disabled because non-convex local-optimum risk needs warm start from META-82.
    "scad.enabled": "false",
    "scad.lambda": "0.01",
    "scad.a": "3.7",
    "scad.step": "0.1",
    "scad.max_iter": "500",
    "scad.tol": "1e-5",
    # =====================================================================
    # BLOCK P9 — CALIBRATION (META-87 to META-90)
    # =====================================================================
    # META-87 — Platt Sigmoid Scaling (WINNER for P9)
    # Paper: Platt 1999 — "Probabilistic Outputs for Support Vector Machines and
    # Comparisons to Regularized Likelihood Methods." Adv. Large Margin Classifiers.
    # Rationale: industry-standard binary calibrator with smoothed targets to avoid
    # over-fitting; quadratic-converging Newton-Raphson. Default enabled.
    "platt.enabled": "true",
    "platt.max_iter": "100",
    "platt.tol": "1e-7",
    "platt.use_smoothed_targets": "true",
    # META-88 — Beta Calibration
    # Paper: Kull, Silva Filho, Flach 2017 — "Beta Calibration: A Well-Founded and
    # Easily Implemented Improvement on Logistic Calibration for Binary Classifiers."
    # AISTATS 2017, PMLR 54:623-631.
    # Rationale: alternative; 3-parameter family for asymmetric calibration. Disabled
    # in favour of META-87 unless asymmetric miscalibration is observed in diagnostics.
    "beta_calibration.enabled": "false",
    "beta_calibration.max_iter": "100",
    "beta_calibration.tol": "1e-7",
    "beta_calibration.eps_clip": "1e-6",
    # META-89 — Dirichlet Calibration
    # Paper: Kull, Perello-Nieto, Kangsepp, Silva Filho, Song, Flach 2019 — "Beyond
    # Temperature Scaling: Obtaining Well-Calibrated Multi-class Probabilities with
    # Dirichlet Calibration." NeurIPS 2019.
    # Rationale: alternative; multiclass log-domain linear calibrator. Disabled until
    # multiclass intent buckets (K>2) are exposed in scoring API.
    "dirichlet_calibration.enabled": "false",
    "dirichlet_calibration.l2_reg": "0.01",
    "dirichlet_calibration.max_iter": "100",
    "dirichlet_calibration.tol": "1e-6",
    "dirichlet_calibration.eps_floor": "1e-6",
    # META-90 — Histogram Binning Calibration
    # Paper: Zadrozny, Elkan 2001 — "Obtaining Calibrated Probability Estimates from
    # Decision Trees and Naive Bayesian Classifiers." ICML 2001, pp. 609-616.
    # Rationale: alternative; non-parametric piecewise-constant calibrator. Disabled
    # in favour of META-87 because parametric calibration is more sample-efficient.
    "histogram_binning.enabled": "false",
    "histogram_binning.n_bins": "20",
    "histogram_binning.equal_frequency": "true",
    "histogram_binning.laplace_smoothing": "true",
    # =====================================================================
    # BLOCK P10 — LR SCHEDULERS (META-91 to META-95)
    # =====================================================================
    # META-91 — Cosine Annealing with Warm Restarts (SGDR) (WINNER for P10)
    # Paper: Loshchilov, Hutter 2017 — "SGDR: Stochastic Gradient Descent with Warm
    # Restarts." ICLR 2017.
    # Rationale: best convergence empirically, restarts escape sharp minima, enables
    # snapshot ensembling (META-98). Default enabled. T_0 sized for ~10-epoch cycles.
    "cosine_annealing.enabled": "true",
    "cosine_annealing.eta_max": "0.01",
    "cosine_annealing.eta_min": "1e-5",
    "cosine_annealing.T_0": "10",
    "cosine_annealing.T_mult": "2.0",
    # META-92 — 1-Cycle Learning Rate Policy
    # Paper: Smith 2018 — "A Disciplined Approach to Neural Network Hyper-Parameters:
    # Part 1." arXiv:1803.09820.
    # Rationale: alternative; super-convergence in ~1/4 epochs. Disabled in favour of
    # META-91 because total_steps must be known at training start (incompatible with
    # plateau-driven training).
    "one_cycle_lr.enabled": "false",
    "one_cycle_lr.eta_init": "1e-4",
    "one_cycle_lr.eta_max": "0.01",
    "one_cycle_lr.eta_final_div": "10000.0",
    "one_cycle_lr.total_steps": "1000",
    "one_cycle_lr.pct_start": "0.3",
    "one_cycle_lr.m_max": "0.95",
    "one_cycle_lr.m_min": "0.85",
    # META-93 — Transformer Warmup + Inverse-Sqrt Decay
    # Paper: Vaswani et al. 2017 — "Attention Is All You Need." NIPS 2017, Section 5.3
    # Equation 3.
    # Rationale: alternative; warmup + inverse-sqrt decay for transformer-style
    # attention heads. Disabled until cross-encoder reranker training is in scope.
    "transformer_lr.enabled": "false",
    "transformer_lr.d_model": "512",
    "transformer_lr.warmup_steps": "4000",
    # META-94 — Polynomial Decay LR
    # Paper: Goyal et al. 2017 — "Accurate, Large Minibatch SGD: Training ImageNet in
    # 1 Hour." arXiv:1706.02677, Section 2.2.
    # Rationale: alternative; smooth monotone decay with configurable curvature.
    # Disabled in favour of META-91 cosine annealing.
    "polynomial_decay.enabled": "false",
    "polynomial_decay.eta_0": "0.01",
    "polynomial_decay.eta_end": "0.0",
    "polynomial_decay.T": "1000",
    "polynomial_decay.power": "1.0",
    # META-95 — Step Decay with Plateau Detection
    # Paper: He, Zhang, Ren, Sun 2015 — "Deep Residual Learning for Image Recognition."
    # ICCV 2015, Sections 3.4 and 4.1.
    # Rationale: alternative; reactive plateau-driven decay. Disabled in favour of
    # META-91; useful fallback when validation NDCG plateaus unpredictably.
    "step_decay_plateau.enabled": "false",
    "step_decay_plateau.eta_0": "0.01",
    "step_decay_plateau.gamma": "0.1",
    "step_decay_plateau.patience": "10",
    "step_decay_plateau.cooldown": "0",
    "step_decay_plateau.threshold": "1e-4",
    "step_decay_plateau.min_lr": "0.0",
    "step_decay_plateau.mode": "max",
    # =====================================================================
    # BLOCK P11 — MODEL AVERAGING (META-96 to META-99)
    # =====================================================================
    # META-96 — Stochastic Weight Averaging (SWA) (WINNER for P11)
    # Paper: Izmailov, Podoprikhin, Garipov, Vetrov, Wilson 2018 — "Averaging Weights
    # Leads to Wider Optima and Better Generalization." UAI 2018.
    # Rationale: free generalization improvement (~0.5-1.5% test accuracy bump);
    # composes with META-91 cyclic LR. Default enabled. swa_start fraction is a
    # share of total epochs (begin averaging after 75% of training).
    "swa.enabled": "true",
    "swa.swa_start_fraction": "0.75",
    "swa.swa_lr": "0.005",
    "swa.k_avg": "1",
    "swa.bn_reestimate": "true",
    # META-97 — Polyak-Ruppert Averaging
    # Paper: Polyak, Juditsky 1992 — "Acceleration of Stochastic Approximation by
    # Averaging." SIAM J. Control & Optim. 30(4):838-855.
    # Rationale: alternative; pure running mean of all iterates with optional burn-in.
    # Disabled in favour of META-96 because SWA's selective sampling is empirically
    # stronger.
    "polyak_ruppert.enabled": "false",
    "polyak_ruppert.burn_in": "0",
    # META-98 — Snapshot Ensemble
    # Paper: Huang, Li, Pleiss, Liu, Hopcroft, Weinberger 2017 — "Snapshot Ensembles:
    # Train 1, Get M for Free." ICLR 2017.
    # Rationale: alternative; averages predictions across cosine-annealing minima.
    # Disabled in favour of META-96 (averages weights, single inference cost).
    "snapshot_ensemble.enabled": "false",
    "snapshot_ensemble.K": "5",
    "snapshot_ensemble.average_mode": "logits",
    # META-99 — Deep Ensembles
    # Paper: Lakshminarayanan, Pritzel, Blundell 2017 — "Simple and Scalable Predictive
    # Uncertainty Estimation using Deep Ensembles." NIPS 2017.
    # Rationale: alternative; N independent training runs. Disabled because N times
    # training cost is prohibitive; META-96 SWA delivers similar gains for free.
    "deep_ensembles.enabled": "false",
    "deep_ensembles.N": "5",
    "deep_ensembles.compute_variance": "true",
    "deep_ensembles.adversarial_training": "false",
    # =====================================================================
    # BLOCK P12 — ROBUSTNESS & SAMPLING (META-100 to META-105)
    # =====================================================================
    # META-100 — Distributionally Robust Optimisation (DRO) (WINNER robustness)
    # Paper: Ben-Tal, El Ghaoui, Nemirovski 2009 — Robust Optimization, Princeton
    # University Press, Chapter 14.
    # Rationale: protects against tail subgroups (rare query types, minority sections)
    # via phi-divergence ambiguity ball. Default enabled. rho=0.1 is a conservative
    # KL radius; raise after diagnostics confirm worst-case slice gap is acceptable.
    "dro.enabled": "true",
    "dro.ambiguity": "kl",
    "dro.rho": "0.1",
    "dro.tol": "1e-6",
    "dro.max_bisect": "60",
    # META-101 — Wasserstein DRO
    # Paper: Mohajerin Esfahani, Kuhn 2018 — "Data-Driven Distributionally Robust
    # Optimization Using the Wasserstein Metric." Math. Programming 171:115-166.
    # Rationale: alternative to META-100; geometric-distance ambiguity protects against
    # perturbations that move mass within the metric. Disabled because plain DRO is
    # the simpler default.
    "wasserstein_dro.enabled": "false",
    "wasserstein_dro.rho": "0.1",
    "wasserstein_dro.p": "2.0",
    "wasserstein_dro.tol": "1e-6",
    "wasserstein_dro.max_bisect": "60",
    # META-102 — Hard Negative Mining (OHEM) (ACTIVE — complementary)
    # Paper: Shrivastava, Gupta, Girshick 2016 — "Training Region-based Object
    # Detectors with Online Hard Example Mining." CVPR 2016.
    # Rationale: focuses gradient capacity on hardest cases; complementary sampling
    # method to META-100 DRO and other active samplers below. Default enabled.
    # keep_fraction=0.5 retains the loss-heaviest half of each batch.
    "ohem.enabled": "true",
    "ohem.keep_fraction": "0.5",
    "ohem.class_aware": "false",
    "ohem.positive_negative_ratio": "0.33",
    # META-103 — Reservoir Sampling (Algorithm R) (ACTIVE — complementary)
    # Paper: Vitter 1985 — "Random Sampling with a Reservoir." ACM TOMS 11(1):37-57.
    # Rationale: streaming uniform k-sample in O(k) memory; complementary to other
    # samplers. Default enabled. reservoir_size=1000 is a sensible audit-sample size.
    "reservoir_sampling.enabled": "true",
    "reservoir_sampling.k": "1000",
    "reservoir_sampling.algorithm": "R",
    "reservoir_sampling.rng_seed": "42",
    # META-104 — Importance-Weighted Mini-Batch Sampling (ACTIVE — complementary)
    # Paper: Csiba, Richtarik 2018 — "Importance Sampling for Minibatches."
    # arXiv:1602.02283 / arXiv:1805.07929.
    # Rationale: variance-reduced unbiased gradient estimator; complementary to other
    # samplers. Default enabled. m=64 is a common mini-batch size.
    "importance_minibatch.enabled": "true",
    "importance_minibatch.m": "64",
    "importance_minibatch.with_replacement": "false",
    "importance_minibatch.rng_seed": "42",
    # META-105 — Stratified k-Fold Mini-Batching (ACTIVE — complementary)
    # Paper: Kohavi 1995 — "A Study of Cross-Validation and Bootstrap for Accuracy
    # Estimation and Model Selection." IJCAI 1995. (Builds on Geisser 1975, JASA.)
    # Rationale: preserves per-class proportions in each fold; essential when relevance
    # buckets have few examples. Complementary to other samplers. Default enabled.
    "stratified_kfold.enabled": "true",
    "stratified_kfold.K": "5",
    "stratified_kfold.require_class_in_every_fold": "true",
    "stratified_kfold.rng_seed": "42",
}
