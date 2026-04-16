"""Forward-declared Phase 2 meta-algorithm weights — Blocks P1 through P6."""
# Covers 36 meta-algorithms across:
#   - Block P1: Second-order and trust-region optimisers (6 metas; winner META-43 L-BFGS-B)
#   - Block P2: Adaptive deep-learning optimisers (8 metas; existing META-34 Adam stays winner)
#   - Block P3: Bayesian and surrogate HPO (6 metas; winner META-55 TPE)
#   - Block P4: Multi-objective optimisation (5 metas; winner META-60 NSGA-II)
#   - Block P5: Swarm and nature-inspired metaheuristics (5 metas; specialty, all off)
#   - Block P6: Online learning (6 metas; winner META-70 FTRL-Proximal)
#
# Each entry has researched starting hyperparameters from the spec. Winners
# default to enabled=true; alternates default to enabled=false but with
# hyperparameters pre-filled so an operator can swap them in instantly.
# See FR-225 Meta Rotation Scheduler for the planned alternation framework.
#
# Source specs live under docs/specs/meta-NN-*.md (META-40 through META-75).
# All values are quoted strings, matching recommended_weights_forward_settings.py.

from __future__ import annotations

FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_P1_P6: dict[str, str] = {
    # =====================================================================
    # Block P1 — Second-order and trust-region optimisers (META-40 .. META-45)
    # =====================================================================
    # META-40 — Newton's Method (Newton 1685 / Raphson 1690; Nocedal & Wright Ch. 3).
    # Alt to META-43 in second-order slot. Locally quadratic convergence but
    # O(d^3) Cholesky per step makes it unsuitable for d > 200.
    "newton.enabled": "false",
    "newton.tolerance": "1e-6",
    "newton.max_iterations": "100",
    "newton.armijo_c": "1e-4",
    # META-41 — Gauss-Newton (Gauss 1809; Nocedal & Wright Ch. 10).
    # Specialised for non-linear least-squares; falls back to META-42 when
    # JᵀJ is rank-deficient. Disabled in favour of L-BFGS-B for general loss.
    "gauss_newton.enabled": "false",
    "gauss_newton.tolerance": "1e-6",
    "gauss_newton.max_iterations": "100",
    "gauss_newton.armijo_c": "1e-4",
    # META-42 — Levenberg-Marquardt (Levenberg 1944; Marquardt 1963).
    # Damped LSQ with adaptive λ. Robust on rank-deficient Jacobians but
    # narrower applicability than L-BFGS-B; disabled by default.
    "levenberg_marquardt.enabled": "false",
    "levenberg_marquardt.lambda0": "1e-3",
    "levenberg_marquardt.tol_grad": "1e-6",
    "levenberg_marquardt.tol_step": "1e-8",
    "levenberg_marquardt.max_iterations": "100",
    # META-43 — L-BFGS-B [WINNER for P1 — bounded quasi-Newton, production grade].
    # Byrd, Lu, Nocedal & Zhu (1995). Industry-standard bounded optimiser used
    # by SciPy. Memory size m=10 is the SciPy default. Superlinear convergence
    # under standard assumptions (Byrd 1995 Thm 3.2).
    "lbfgs_b.enabled": "true",
    "lbfgs_b.memory_size": "10",
    "lbfgs_b.tol_grad": "1e-5",
    "lbfgs_b.tol_f": "1e-7",
    "lbfgs_b.max_iterations": "200",
    "lbfgs_b.max_line_search": "20",
    # META-44 — Full BFGS (Broyden, Fletcher, Goldfarb, Shanno 1970).
    # Dense O(d²) Hessian approximation; superseded by L-BFGS-B for d > 50.
    # Disabled by default but kept for small-d comparison.
    "bfgs.enabled": "false",
    "bfgs.tol_grad": "1e-5",
    "bfgs.max_iterations": "200",
    "bfgs.max_line_search": "20",
    # META-45 — Fletcher-Reeves Conjugate Gradient (Fletcher & Reeves 1964;
    # Al-Baali 1985 convergence). Matrix-free, O(d) memory — only relevant for
    # very large d (>2000) where L-BFGS-B history becomes wasteful.
    "fletcher_reeves.enabled": "false",
    "fletcher_reeves.tol_grad": "1e-5",
    "fletcher_reeves.max_iterations": "500",
    "fletcher_reeves.max_line_search": "20",
    "fletcher_reeves.restart_every": "0",
    # =====================================================================
    # Block P2 — Adaptive deep-learning optimisers (META-46 .. META-53)
    # =====================================================================
    # NOTE: Existing META-34 Adam stays the production default for this slot.
    # All eight P2 alternates remain enabled=false with hyperparameters seeded
    # so an operator can rotate via FR-225 Meta Rotation Scheduler.
    #
    # META-46 — AdaGrad (Duchi, Hazan & Singer 2011, JMLR).
    # Cumulative-gradient adaptive lr; strong on sparse features but vanishing
    # learning rate over long horizons. Alternate only.
    "adagrad.enabled": "false",
    "adagrad.learning_rate": "0.01",
    "adagrad.epsilon": "1e-10",
    # META-47 — AdaDelta (Zeiler 2012, arXiv:1212.5701).
    # Units-correcting EMA fixes AdaGrad's vanishing lr; Zeiler default ρ=0.95.
    "adadelta.enabled": "false",
    "adadelta.rho": "0.95",
    "adadelta.epsilon": "1e-6",
    # META-48 — Nadam (Dozat 2016, ICLR Workshop).
    # Adam + Nesterov momentum; PyTorch defaults β1=0.9, β2=0.999, ε=1e-8.
    "nadam.enabled": "false",
    "nadam.learning_rate": "2e-3",
    "nadam.beta1": "0.9",
    "nadam.beta2": "0.999",
    "nadam.epsilon": "1e-8",
    # META-49 — AMSGrad (Reddi, Kale & Kumar 2018, ICLR Best Paper).
    # Fixes Adam's non-convergence via non-decreasing v̂_t; same defaults as Adam.
    "amsgrad.enabled": "false",
    "amsgrad.learning_rate": "1e-3",
    "amsgrad.beta1": "0.9",
    "amsgrad.beta2": "0.999",
    "amsgrad.epsilon": "1e-8",
    # META-50 — Lookahead Optimizer Wrapper (Zhang, Lucas, Hinton & Ba 2019).
    # Slow/fast weight averaging around any inner optimiser. Paper defaults
    # k=5 inner steps, slow lr α=0.5.
    "lookahead.enabled": "false",
    "lookahead.k_inner_steps": "5",
    "lookahead.slow_lr_alpha": "0.5",
    # META-51 — RAdam Rectified Adam (Liu et al. 2020, ICLR).
    # Closed-form variance rectification removes warm-up requirement.
    # Defaults from PyTorch torch.optim.RAdam.
    "radam.enabled": "false",
    "radam.learning_rate": "1e-3",
    "radam.beta1": "0.9",
    "radam.beta2": "0.999",
    "radam.epsilon": "1e-8",
    # META-52 — Lion EvoLved Sign Momentum (Chen et al. 2023, arXiv:2302.06675).
    # Single-state sign-of-momentum optimiser. Paper defaults lr=1e-4, β1=0.9,
    # β2=0.99, weight_decay=0 (Lion typically uses smaller lr than Adam).
    "lion.enabled": "false",
    "lion.learning_rate": "1e-4",
    "lion.beta1": "0.9",
    "lion.beta2": "0.99",
    "lion.weight_decay": "0.0",
    # META-53 — Yogi (Zaheer, Reddi, Sachan, Kale & Kumar 2018, NeurIPS).
    # Additive v_t update for non-convex stability. Paper recommends initial v
    # of 1e-6 to avoid div-by-zero.
    "yogi.enabled": "false",
    "yogi.learning_rate": "1e-2",
    "yogi.beta1": "0.9",
    "yogi.beta2": "0.999",
    "yogi.epsilon": "1e-3",
    "yogi.v_init": "1e-6",
    # =====================================================================
    # Block P3 — Bayesian and surrogate HPO (META-54 .. META-59)
    # =====================================================================
    # META-54 — GP-EI Gaussian Process + Expected Improvement (Močkus 1974;
    # Jones, Schonlau & Welch 1998). Strong on small-d (≤20) continuous spaces
    # but O(T³) Cholesky cost; alternate to TPE.
    "gp_ei.enabled": "false",
    "gp_ei.n_init": "10",
    "gp_ei.total_budget": "100",
    "gp_ei.kernel": "matern52",
    "gp_ei.xi": "0.01",
    "gp_ei.random_seed": "0",
    # META-55 — TPE Tree-Structured Parzen Estimator [WINNER for P3 —
    # scales to many dims and conditional/categorical spaces]. Bergstra,
    # Bardenet, Bengio & Kégl (2011, NeurIPS). Optuna defaults γ=0.15 quantile,
    # 24 candidate samples per acquisition.
    "tpe.enabled": "true",
    "tpe.gamma_quantile": "0.15",
    "tpe.n_candidates": "24",
    "tpe.n_init": "10",
    "tpe.random_seed": "0",
    # META-56 — SMAC Sequential Model-based Algorithm Configuration
    # (Hutter, Hoos & Leyton-Brown 2011, LION). RF surrogate for mixed
    # categorical/continuous spaces. Paper defaults n_trees=10, min_leaf=3.
    "smac.enabled": "false",
    "smac.n_trees": "10",
    "smac.max_depth": "20",
    "smac.min_samples_leaf": "3",
    "smac.n_candidates": "100",
    "smac.random_seed": "0",
    # META-57 — BOHB Bayesian + Hyperband hybrid (Falkner, Klein & Hutter
    # 2018, ICML). Paper defaults η=3 reduction factor, γ=0.15 TPE quantile,
    # n_min=N_min for TPE fallback.
    "bohb.enabled": "false",
    "bohb.eta": "3",
    "bohb.gamma_quantile": "0.15",
    "bohb.n_min_for_tpe": "8",
    "bohb.r_min": "1.0",
    "bohb.r_max": "81.0",
    "bohb.random_seed": "0",
    # META-58 — Hyperband (Li, Jamieson, DeSalvo, Rostamizadeh & Talwalkar
    # 2017, JMLR). Pure successive-halving bandit. Paper defaults η=3, R=81.
    "hyperband.enabled": "false",
    "hyperband.eta": "3",
    "hyperband.r_min": "1.0",
    "hyperband.r_max": "81.0",
    "hyperband.n_outer_loops": "1",
    "hyperband.random_seed": "0",
    # META-59 — GP-UCB (Srinivas, Krause, Kakade & Seeger 2010, ICML).
    # Sublinear regret bound via β_t schedule. Confidence δ default 0.1
    # (Srinivas 2010 §4.1).
    "gp_ucb.enabled": "false",
    "gp_ucb.n_init": "10",
    "gp_ucb.total_budget": "100",
    "gp_ucb.kernel": "matern52",
    "gp_ucb.delta_confidence": "0.1",
    "gp_ucb.random_seed": "0",
    # =====================================================================
    # Block P4 — Multi-objective optimisation (META-60 .. META-64)
    # =====================================================================
    # META-60 — NSGA-II [WINNER for P4 — most established Pareto+crowding
    # multi-objective EA]. Deb, Pratap, Agarwal & Meyarivan (2002, IEEE TEC).
    # pymoo defaults: pop=100, max_gen=100, p_crossover=0.9, p_mutation=1/d.
    "nsga_ii.enabled": "true",
    "nsga_ii.population_size": "100",
    "nsga_ii.max_generations": "100",
    "nsga_ii.p_crossover": "0.9",
    "nsga_ii.p_mutation": "0.1",
    "nsga_ii.random_seed": "0",
    # META-61 — NSGA-III many-objective with reference points (Deb & Jain
    # 2014, IEEE TEC). Use only for M ≥ 4 objectives. Das-Dennis p divisions
    # default 12 (yields 91 points for M=3, 364 for M=4).
    "nsga_iii.enabled": "false",
    "nsga_iii.population_size": "100",
    "nsga_iii.max_generations": "100",
    "nsga_iii.p_divisions": "12",
    "nsga_iii.p_crossover": "0.9",
    "nsga_iii.p_mutation": "0.1",
    "nsga_iii.random_seed": "0",
    # META-62 — MOEA/D Decomposition (Zhang & Li 2007, IEEE TEC).
    # Decomposes MO into N scalar subproblems. Default neighbourhood size
    # T=20 (Zhang 2007 §IV.A); scalarisation 0=Tchebycheff (recommended).
    "moea_d.enabled": "false",
    "moea_d.population_size": "100",
    "moea_d.max_generations": "200",
    "moea_d.neighbourhood_size": "20",
    "moea_d.scalarisation": "0",
    "moea_d.p_crossover": "0.9",
    "moea_d.p_mutation": "0.1",
    "moea_d.random_seed": "0",
    # META-63 — ε-Constraint Method (Haimes, Lasdon & Wismer 1971; Miettinen
    # 1999 §3.2). Use when one objective is primary, others are bounded.
    # K_grid=10 yields K^(M-1) points (e.g. 100 for M=3).
    "epsilon_constraint.enabled": "false",
    "epsilon_constraint.k_grid_per_axis": "10",
    "epsilon_constraint.primary_index": "0",
    "epsilon_constraint.inner_solver_id": "0",
    # META-64 — Tchebycheff Scalarisation (Miettinen 1999 §3.4.3).
    # Pure primitive; consumed by META-62 MOEA/D. Augmented Tchebycheff
    # uses ρ ≈ 1e-3 to ensure proper Pareto-optimality.
    "tchebycheff.enabled": "false",
    "tchebycheff.rho_augmentation": "1e-3",
    # =====================================================================
    # Block P5 — Swarm and nature-inspired metaheuristics (META-65 .. META-69)
    # =====================================================================
    # NOTE: All P5 metas are SPECIALTY/RESEARCH only. They underperform
    # gradient-aware optimisers on smooth losses; kept enabled=false with
    # canonical defaults for offline benchmarking and comparison studies.
    #
    # META-65 — PSO (Kennedy & Eberhart 1995, IEEE ICNN).
    # Stable when ω + c1/2 + c2/2 < 1 (Clerc & Kennedy 2002). Standard
    # canonical PSO defaults: ω=0.7298, c1=c2=1.49618.
    "pso.enabled": "false",
    "pso.swarm_size": "30",
    "pso.max_iterations": "500",
    "pso.omega_inertia": "0.7298",
    "pso.c1_cognitive": "1.49618",
    "pso.c2_social": "1.49618",
    "pso.v_max_fraction": "0.5",
    "pso.random_seed": "0",
    # META-66 — Ant Colony Optimization (Dorigo 1992 PhD; Dorigo & Stützle
    # 2004 textbook). For combinatorial selection. AS canonical defaults:
    # α=1, β=2..5, ρ=0.5, Q=1.
    "aco.enabled": "false",
    "aco.n_ants": "30",
    "aco.max_cycles": "100",
    "aco.alpha_pheromone": "1.0",
    "aco.beta_heuristic": "2.0",
    "aco.rho_evaporation": "0.5",
    "aco.q_deposit": "1.0",
    "aco.tau0_initial": "1e-6",
    "aco.random_seed": "0",
    # META-67 — Cuckoo Search via Lévy Flights (Yang & Deb 2009, NaBIC).
    # Paper defaults p_a=0.25 abandonment, β=1.5 Mantegna Lévy exponent,
    # α=0.01 step scale.
    "cuckoo_search.enabled": "false",
    "cuckoo_search.n_nests": "25",
    "cuckoo_search.max_iterations": "500",
    "cuckoo_search.p_abandon": "0.25",
    "cuckoo_search.beta_levy": "1.5",
    "cuckoo_search.alpha_step": "0.01",
    "cuckoo_search.random_seed": "0",
    # META-68 — Firefly Algorithm (Yang 2008 textbook Ch. 10).
    # Canonical defaults: β0=1.0 base attractiveness, γ=1.0 absorption,
    # α=0.2 randomisation, cooling 0.97 per iteration.
    "firefly.enabled": "false",
    "firefly.n_fireflies": "30",
    "firefly.max_iterations": "200",
    "firefly.beta0_attractiveness": "1.0",
    "firefly.gamma_absorption": "1.0",
    "firefly.alpha_randomisation": "0.2",
    "firefly.alpha_cooling": "0.97",
    "firefly.random_seed": "0",
    # META-69 — Bat Algorithm (Yang 2010, NICSO).
    # Yang 2010 defaults: f_min=0, f_max=2, A0=1, r0=0.5, α=0.9, γ=0.9.
    "bat_algorithm.enabled": "false",
    "bat_algorithm.n_bats": "30",
    "bat_algorithm.max_iterations": "500",
    "bat_algorithm.f_min": "0.0",
    "bat_algorithm.f_max": "2.0",
    "bat_algorithm.a0_loudness": "1.0",
    "bat_algorithm.r0_pulse_rate": "0.5",
    "bat_algorithm.alpha_loudness_decay": "0.9",
    "bat_algorithm.gamma_pulse_growth": "0.9",
    "bat_algorithm.random_seed": "0",
    # =====================================================================
    # Block P6 — Online learning (META-70 .. META-75)
    # =====================================================================
    # META-70 — FTRL-Proximal [WINNER for P6 — Google Ads workhorse for
    # streaming click-through prediction]. McMahan et al. (2013, KDD).
    # Paper defaults α=0.1 per-coordinate lr, β=1.0, λ1=1.0, λ2=1.0.
    "ftrl.enabled": "true",
    "ftrl.alpha_lr": "0.1",
    "ftrl.beta": "1.0",
    "ftrl.lambda1_l1": "1.0",
    "ftrl.lambda2_l2": "1.0",
    # META-71 — Online Newton Step (Hazan, Agarwal & Kale 2007, ML).
    # O(log T) regret for exp-concave losses but O(d²) per-step cost limits
    # to dense d ≤ 500. Default ε=1.0 regularisation, η=1.0.
    "online_newton.enabled": "false",
    "online_newton.eta_lr": "1.0",
    "online_newton.epsilon_regulariser": "1.0",
    # META-72 — Online Mirror Descent (Beck & Teboulle 2003, OR Letters).
    # mirror_kind: 0=Euclidean, 1=Entropic (simplex), 2=p-norm. Default
    # Euclidean which recovers projected OGD; η default 0.01.
    "online_mirror_descent.enabled": "false",
    "online_mirror_descent.eta_lr": "0.01",
    "online_mirror_descent.mirror_kind": "0",
    "online_mirror_descent.p_param": "2.0",
    # META-73 — Online AdaBoost.OC (Chen, Lin & Lu 2012, JMLR).
    # T=10 weak learners is a typical default; γ_decay=0.99 keeps decayed
    # sums bounded; smoothing 1e-6 keeps log finite.
    "online_adaboost.enabled": "false",
    "online_adaboost.n_weak_learners": "10",
    "online_adaboost.gamma_decay": "0.99",
    "online_adaboost.smoothing": "1e-6",
    "online_adaboost.random_seed": "0",
    # META-74 — Projected OGD (Zinkevich 2003, ICML).
    # Optimal step is η = R / (G·sqrt(T)); we expose a default lr instead.
    # proj_kind: 0=box, 1=L2-ball, 2=simplex.
    "projected_online_gradient.enabled": "false",
    "projected_online_gradient.eta_lr": "0.01",
    "projected_online_gradient.proj_kind": "0",
    "projected_online_gradient.r_radius": "1.0",
    # META-75 — Streaming ADMM (Boyd, Parikh, Chu, Peleato & Eckstein 2011,
    # FnT in ML). Boyd 2011 default ρ=1.0 penalty, ε_pri=ε_dual=1e-4. Use for
    # consensus across N blocks (e.g. query clusters).
    "admm_streaming.enabled": "false",
    "admm_streaming.rho_penalty": "1.0",
    "admm_streaming.eps_primal": "1e-4",
    "admm_streaming.eps_dual": "1e-4",
    "admm_streaming.max_iterations": "200",
}
