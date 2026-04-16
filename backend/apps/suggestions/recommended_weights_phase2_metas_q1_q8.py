"""Forward-declared Phase 2 meta-algorithm weights — Blocks Q1 through Q8."""
# Covers 57 meta-algorithms across:
#   - Block Q1: MCMC sampling (8; winner META-110 NUTS)
#   - Block Q2: Variational inference (6; winner META-118 Reparam-VI)
#   - Block Q3: Evolutionary search (8; winner META-122 NES)
#   - Block Q4: Advanced gradient methods (8; winner META-130 NAG)
#   - Block Q5: Reg via augmentation/noise (7; ALL enabled — they layer naturally)
#   - Block Q6: Feature engineering (8; ALL enabled — different feature types)
#   - Block Q7: Dim reduction (7; winner META-151 PCA)
#   - Block Q8: Kernel methods (5; winner META-162 GPR)
#
# Each entry has researched starting hyperparameters. Alternates default
# enabled=false but pre-filled. See FR-225 for rotation scheduling framework.

from __future__ import annotations

FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_Q1_Q8: dict[str, str] = {
    # =====================================================================
    # BLOCK Q1 — MCMC POSTERIOR SAMPLING (META-106..113; winner META-110)
    # =====================================================================
    # META-106 — Metropolis-Hastings (Metropolis 1953; Hastings 1970).
    # Random-walk baseline; superseded by NUTS for smooth densities.
    "mh.enabled": "false",
    "mh.n_samples": "5e3",
    "mh.burn_in": "1e3",
    "mh.proposal_scale": "0.5",
    # META-107 — Gibbs Sampler (Geman & Geman, IEEE PAMI 1984).
    # Coordinate-wise; needs tractable conditionals.
    "gibbs.enabled": "false",
    "gibbs.n_samples": "5e3",
    "gibbs.burn_in": "1e3",
    # META-108 — Slice Sampler (Neal, Annals of Statistics 2003).
    # Tuning-free; step-out + shrinkage; cap step-out for safety.
    "slice.enabled": "false",
    "slice.n_samples": "5e3",
    "slice.step_size": "1.0",
    "slice.max_step_out": "50",
    # META-109 — Hamiltonian Monte Carlo (Duane et al., Phys Lett B 1987).
    # Gradient-based; needs L tuning — prefer NUTS instead.
    "hmc.enabled": "false",
    "hmc.n_samples": "2e3",
    "hmc.step_eps": "0.05",
    "hmc.n_leapfrog": "20",
    # META-110 — No-U-Turn Sampler (Hoffman & Gelman, JMLR 2014). WINNER.
    # Adaptive HMC: dual-averaging ε; no tree-depth tuning; cap depth ≤12.
    "nuts.enabled": "true",
    "nuts.n_samples": "2e3",
    "nuts.n_warmup": "1e3",
    "nuts.target_accept": "0.8",
    "nuts.max_depth": "10",
    # META-111 — SGLD (Welling & Teh, ICML 2011).
    # Mini-batch posterior; activate when data.n exceeds full-batch cost.
    "sgld.enabled": "false",
    "sgld.n_iters": "5e4",
    "sgld.step_a": "0.01",
    "sgld.step_gamma": "0.55",
    # META-112 — Elliptical Slice (Murray, Adams, MacKay, AISTATS 2010).
    # Specialised for Gaussian priors (e.g. GP latents).
    "ess.enabled": "false",
    "ess.n_samples": "2e3",
    # META-113 — Sequential Monte Carlo (Del Moral, CRAS 1996).
    # Tempered particle population for multi-modal posteriors.
    "smc.enabled": "false",
    "smc.n_particles": "2e3",
    "smc.n_temperature_steps": "20",
    "smc.ess_resample_threshold": "0.5",
    # =====================================================================
    # BLOCK Q2 — VARIATIONAL INFERENCE (META-114..119; winner META-118)
    # =====================================================================
    # META-114 — Mean-Field VI / CAVI (Beal, PhD thesis 2003).
    # Factorised q; ELBO monotonic; fast but ignores correlations.
    "mfvi.enabled": "false",
    "mfvi.max_epochs": "2e2",
    "mfvi.tol": "1e-4",
    # META-115 — Expectation Propagation (Minka, UAI 2001).
    # Moment matching; needs damping to stabilise.
    "ep.enabled": "false",
    "ep.max_iters": "1e2",
    "ep.damping": "0.5",
    "ep.tol": "1e-4",
    # META-116 — Stein Variational Gradient Descent (Liu & Wang, NeurIPS 2016).
    # Particle-based VI with RBF + median-heuristic bandwidth.
    "svgd.enabled": "false",
    "svgd.n_particles": "1e2",
    "svgd.step_eps": "0.05",
    "svgd.n_iters": "1e3",
    # META-117 — Black-Box VI (Ranganath, Gerrish, Blei, AISTATS 2014).
    # Score-function gradient; high variance; use control variates.
    "bbvi.enabled": "false",
    "bbvi.n_mc_samples": "32",
    "bbvi.n_iters": "5e3",
    "bbvi.lr": "0.01",
    # META-118 — Reparameterization-Trick VI (Kingma & Welling, ICLR 2014). WINNER.
    # Pathwise (low-variance) gradient; foundational for VAEs.
    "reparam_vi.enabled": "true",
    "reparam_vi.n_mc_samples": "16",
    "reparam_vi.n_iters": "5e3",
    "reparam_vi.lr": "0.01",
    # META-119 — Amortised VI (Gershman & Goodman, CogSci 2014).
    # Shared encoder; pair with reparam VI inside a VAE.
    "amortised_vi.enabled": "false",
    "amortised_vi.batch_size": "64",
    "amortised_vi.n_iters": "1e4",
    "amortised_vi.lr": "1e-3",
    # =====================================================================
    # BLOCK Q3 — EVOLUTIONARY SEARCH (META-120..127; winner META-122)
    # =====================================================================
    # META-120 — Genetic Algorithm (Holland 1975).
    # Tournament + uniform crossover; bit-flip mutation.
    "ga.enabled": "false",
    "ga.pop_size": "2e2",
    "ga.crossover_rate": "0.8",
    "ga.mutation_rate": "0.05",
    "ga.n_generations": "2e2",
    # META-121 — (1+1)-Evolution Strategies (Rechenberg 1973).
    # Rechenberg 1/5 success rule; continuous Gaussian perturbation.
    "es.enabled": "false",
    "es.initial_sigma": "0.5",
    "es.adaptation_window": "20",
    "es.n_generations": "5e3",
    # META-122 — Natural Evolution Strategies (Wierstra et al., JMLR 2014). WINNER.
    # Natural-gradient ascent on E[f]; rotation/scale invariant; scales well.
    "nes.enabled": "true",
    "nes.population_lambda": "50",
    "nes.lr_mu": "1.0",
    "nes.lr_sigma": "0.1",
    "nes.n_generations": "5e2",
    # META-123 — Tabu Search (Glover, Operations Research 1986).
    # Memory-based local search; aspiration override.
    "tabu.enabled": "false",
    "tabu.tabu_tenure": "20",
    "tabu.n_iters": "5e3",
    # META-124 — GRASP (Feo & Resende, J Global Optim 1995).
    # Greedy-randomised construction + local search; multi-start.
    "grasp.enabled": "false",
    "grasp.alpha": "0.3",
    "grasp.n_restarts": "50",
    # META-125 — Variable Neighborhood Search (Mladenović & Hansen, COR 1997).
    # Nested neighborhoods; shake-then-LS pattern.
    "vns.enabled": "false",
    "vns.k_max": "5",
    "vns.n_iters": "2e3",
    # META-126 — Adaptive Large Neighborhood Search (Ropke & Pisinger, TS 2006).
    # Destroy-repair with adaptive operator weights and SA acceptance.
    "alns.enabled": "false",
    "alns.destroy_q": "10",
    "alns.n_iters": "1e4",
    "alns.segment_size": "1e2",
    "alns.reaction_rho": "0.1",
    "alns.cooling": "0.999",
    # META-127 — Harmony Search (Geem, Kim, Loganathan, Simulation 2001).
    # Music-inspired memory; HMCR and PAR control exploration.
    "harmony.enabled": "false",
    "harmony.hms": "30",
    "harmony.hmcr": "0.9",
    "harmony.par": "0.3",
    "harmony.n_iters": "5e3",
    # =====================================================================
    # BLOCK Q4 — ADVANCED GRADIENT METHODS (META-128..135; winner META-130)
    # =====================================================================
    # META-128 — Natural Gradient (Amari 1998).
    # Fisher-preconditioned step; O(d^3) Cholesky cost limits dimensionality.
    "nat_grad.enabled": "false",
    "nat_grad.lr": "0.01",
    "nat_grad.damping": "1e-4",
    # META-129 — AdaBelief (Zhuang et al., NeurIPS 2020).
    # Adam variant: belief variance over (g - m)^2.
    "adabelief.enabled": "false",
    "adabelief.lr": "1e-3",
    "adabelief.beta1": "0.9",
    "adabelief.beta2": "0.999",
    "adabelief.eps": "1e-8",
    # META-130 — Nesterov Accelerated Gradient (Nesterov 1983). WINNER.
    # Lookahead momentum; classic O(1/t^2) on smooth convex.
    "nag.enabled": "true",
    "nag.lr": "0.01",
    "nag.momentum": "0.9",
    # META-131 — Mirror Descent / EG (Nemirovski & Yudin 1983).
    # Negative-entropy Bregman; for simplex-constrained convex weights.
    "mirror_descent.enabled": "false",
    "mirror_descent.lr": "0.05",
    # META-132 — Proximal Gradient / ISTA (Daubechies et al. 2004).
    # Soft-threshold for L1-regularised weight tuning (sparsity).
    "ista.enabled": "false",
    "ista.lr": "0.01",
    "ista.l1_weight": "1e-3",
    # META-133 — Apollo (Ma, NeurIPS 2021).
    # Diagonal quasi-Newton; Adam alternative.
    "apollo.enabled": "false",
    "apollo.lr": "1e-2",
    "apollo.beta": "0.9",
    "apollo.eps": "1e-4",
    "apollo.clip": "0.01",
    # META-134 — LAMB (You et al., ICLR 2020).
    # Layer-wise trust ratio + decoupled weight decay; large-batch friendly.
    "lamb.enabled": "false",
    "lamb.lr": "1e-3",
    "lamb.beta1": "0.9",
    "lamb.beta2": "0.999",
    "lamb.weight_decay": "0.01",
    # META-135 — LARS (You, Gitman, Ginsburg 2017).
    # Layer-wise local-LR scaling; very-large-batch SGD.
    "lars.enabled": "false",
    "lars.lr": "0.1",
    "lars.momentum": "0.9",
    "lars.weight_decay": "5e-4",
    "lars.eta_local": "1e-3",
    # =====================================================================
    # BLOCK Q5 — REG VIA AUGMENTATION / NOISE (META-136..142; ALL enabled)
    # Different augmentations layer naturally — keep all on by default.
    # =====================================================================
    # META-136 — Label Smoothing (Szegedy et al., CVPR 2016).
    # Shrinks max-logit confidence; soft target = (1-ε)·1{k=y} + ε/K.
    "label_smoothing.enabled": "true",
    "label_smoothing.epsilon": "0.1",
    # META-137 — Mixup (Zhang et al., ICLR 2018).
    # Convex blend of pairs; α controls Beta distribution skew.
    "mixup.enabled": "true",
    "mixup.alpha": "0.2",
    # META-138 — CutMix (Yun et al., ICCV 2019).
    # Patch-replacement variant of Mixup; spatial inputs only.
    "cutmix.enabled": "true",
    "cutmix.beta": "1.0",
    # META-139 — Cutout (DeVries & Taylor, arXiv:1708.04552 2017).
    # Square zero-mask on input; complements Mixup/CutMix.
    "cutout.enabled": "true",
    "cutout.mask_size": "16",
    # META-140 — DropConnect (Wan et al., ICML 2013).
    # Bernoulli mask on weights (vs activations); inverted scaling.
    "dropconnect.enabled": "true",
    "dropconnect.keep_prob": "0.9",
    # META-141 — Stochastic Depth (Huang et al., ECCV 2016).
    # Linear-decay survival probability across L residual blocks.
    "stoch_depth.enabled": "true",
    "stoch_depth.p_final": "0.5",
    # META-142 — Gradient Noise Injection (Neelakantan et al., arXiv:1511.06807).
    # σ_t² = η·(1+t)^(-γ); escapes saddles; γ=0.55 is the paper default.
    "grad_noise.enabled": "true",
    "grad_noise.eta": "0.01",
    "grad_noise.gamma": "0.55",
    # =====================================================================
    # BLOCK Q6 — FEATURE ENGINEERING (META-143..150; ALL enabled)
    # Different transforms apply to different feature types — keep all on.
    # =====================================================================
    # META-143 — Polynomial Feature Expansion (Fukunaga 1990).
    # Degree-2 default; output dim grows as C(d+p,p).
    "poly_features.enabled": "true",
    "poly_features.degree": "2",
    "poly_features.include_bias": "false",
    # META-144 — B-Spline Basis (de Boor 1978).
    # Cubic order=4 default; partition of unity preserved.
    "bspline.enabled": "true",
    "bspline.order": "4",
    "bspline.n_basis": "16",
    # META-145 — Natural Cubic Spline Basis (Green & Silverman 1993).
    # Linear tails; K interior knots; minimum-curvature smoother.
    "ncs.enabled": "true",
    "ncs.n_knots": "5",
    # META-146 — Fourier Random Features (Rahimi & Recht, NIPS 2007).
    # Linear-predictor primalisation of RBF; D cosines.
    "fourier_rff.enabled": "true",
    "fourier_rff.n_features": "5e2",
    "fourier_rff.sigma": "1.0",
    # META-147 — Hashing Trick (Weinberger et al., ICML 2009).
    # MurmurHash3 + signed accumulate; J=2^20 default for forum-scale.
    "hashing.enabled": "true",
    "hashing.n_buckets": "1048576",
    "hashing.hash_seed": "42",
    # META-148 — Target Encoding (Micci-Barreca, SIGKDD 2001).
    # Bayesian-smoothed per-category target mean; m controls shrinkage.
    "target_enc.enabled": "true",
    "target_enc.smoothing": "10",
    # META-149 — Count Encoding (Pargent, Bischl, Thomas, NeurIPS 2021).
    # Frequency replacement; log(1+n) variant for skewed distributions.
    "count_enc.enabled": "true",
    "count_enc.log_transform": "true",
    "count_enc.normalise": "false",
    # META-150 — Leave-One-Out Target Encoding (Micci-Barreca 2001 LOO variant).
    # Leakage-free training-time encoding via sum-minus-self.
    "loo_enc.enabled": "true",
    "loo_enc.fallback_to_global_mean": "true",
    # =====================================================================
    # BLOCK Q7 — DIMENSIONALITY REDUCTION (META-151..157; winner META-151)
    # =====================================================================
    # META-151 — PCA (Pearson 1901). WINNER.
    # Closed-form linear; whiten=false to preserve scale by default.
    "pca.enabled": "true",
    "pca.n_components": "32",
    "pca.whiten": "false",
    # META-152 — Kernel PCA (Schölkopf, Smola, Müller, Neural Comp 1998).
    # Non-linear via RBF; n^2 Gram limits scale.
    "kpca.enabled": "false",
    "kpca.n_components": "32",
    "kpca.kernel": "rbf",
    "kpca.gamma": "0.1",
    # META-153 — FastICA (Hyvärinen & Oja, Neural Networks 2000).
    # Non-Gaussian source separation; tanh non-linearity default.
    "ica.enabled": "false",
    "ica.n_components": "16",
    "ica.nonlinearity": "tanh",
    "ica.max_iter": "2e2",
    "ica.tol": "1e-4",
    # META-154 — Sparse PCA (Zou, Hastie, Tibshirani, JCGS 2006).
    # Elastic-net loadings for interpretable components.
    "sparse_pca.enabled": "false",
    "sparse_pca.n_components": "16",
    "sparse_pca.alpha_l1": "1.0",
    "sparse_pca.alpha_l2": "0.01",
    # META-155 — LDA (Fisher, Annals of Eugenics 1936).
    # Class-discriminative; rank capped at C-1.
    "lda.enabled": "false",
    "lda.n_components": "8",
    "lda.shrinkage": "0.0",
    # META-156 — CCA (Hotelling, Biometrika 1936).
    # Two-view alignment; ridge stabilises Σ⁻¹ inversions.
    "cca.enabled": "false",
    "cca.n_components": "16",
    "cca.reg_x": "1e-3",
    "cca.reg_y": "1e-3",
    # META-157 — Random Projection / JL (Johnson & Lindenstrauss 1984; Achlioptas 2003).
    # Data-oblivious; m = ⌈8·log(n)/ε²⌉; ε=0.3 default.
    "jl_proj.enabled": "false",
    "jl_proj.epsilon": "0.3",
    "jl_proj.density": "one_third",
    "jl_proj.seed": "1",
    # =====================================================================
    # BLOCK Q8 — KERNEL METHODS (META-158..162; winner META-162)
    # =====================================================================
    # META-158 — Kernel Ridge Regression (Saunders, Gammerman, Vovk, ICML 1998).
    # Closed-form dual; n^2 Gram cost; pair with Nyström or RFF for scale.
    "krr.enabled": "false",
    "krr.kernel": "rbf",
    "krr.gamma": "0.1",
    "krr.lambda_reg": "1.0",
    # META-159 — Support Vector Regression (Drucker et al., NIPS 1996).
    # ε-insensitive loss; SMO; sparse support vectors.
    "svr.enabled": "false",
    "svr.kernel": "rbf",
    "svr.C": "1.0",
    "svr.epsilon": "0.1",
    "svr.tol": "1e-3",
    # META-160 — Nyström Approximation (Williams & Seeger, NIPS 2001).
    # Low-rank Gram via m landmarks; enables KRR/SVR at large n.
    "nystrom.enabled": "false",
    "nystrom.n_landmarks": "5e2",
    "nystrom.strategy": "uniform",
    "nystrom.kernel": "rbf",
    "nystrom.gamma": "0.1",
    # META-161 — RFF for Kernel Regression (Rahimi & Recht, NIPS 2007).
    # Distinct from META-146: replaces n^2 Gram with primal-space ZᵀZ.
    "rff_kernel.enabled": "false",
    "rff_kernel.n_features": "1e3",
    "rff_kernel.sigma": "1.0",
    "rff_kernel.lambda_reg": "1.0",
    # META-162 — Gaussian Process Regression (Rasmussen & Williams 2006). WINNER.
    # Calibrated (μ, σ) per prediction; ideal for HPO + active learning.
    "gpr.enabled": "true",
    "gpr.kernel": "rbf",
    "gpr.length_scale": "1.0",
    "gpr.variance": "1.0",
    "gpr.noise_variance": "1e-3",
    "gpr.optimise_hyperparams": "true",
    "gpr.n_restarts": "5",
}
