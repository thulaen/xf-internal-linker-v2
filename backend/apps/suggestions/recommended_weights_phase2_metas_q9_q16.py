"""Forward-declared Phase 2 meta-algorithm weights — Blocks Q9 through Q16."""
# Covers 43 meta-algorithms across:
#   - Block Q9:  Info-theoretic model selection (5; ALL enabled — different criteria)
#   - Block Q10: Clustering (8; winner META-168 k-means)
#   - Block Q11: Feature attribution (5; ALL enabled — different views)
#   - Block Q12: Active learning (5; ALL enabled — different selection strategies)
#   - Block Q13: Semi-supervised (5; winner META-188 Label propagation)
#   - Block Q14: Causal inference (5; ALL enabled — different estimators)
#   - Block Q15: RL (6; winner META-200 PPO)
#   - Block Q16: Bandits (4; winner META-203 LinUCB)
#
# Each entry has researched starting hyperparameters. Alternates default
# enabled=false but pre-filled. See FR-225 for rotation framework.

from __future__ import annotations

FORWARD_DECLARED_WEIGHTS_PHASE2_METAS_Q9_Q16: dict[str, str] = {
    # =====================================================================
    # BLOCK Q9 — Info-theoretic model selection (META-163..167)
    # ALL 5 enabled — AIC, BIC, MDL, MI, IB are different criteria.
    # =====================================================================
    # META-163 — Kraskov Mutual Information Estimator
    # Kraskov 2004; k-NN k=3 is the paper default for low-bias MI in nats.
    "kraskov_mi.enabled": "true",
    "kraskov_mi.k_neighbors": "3",
    "kraskov_mi.min_samples": "32",
    # META-164 — Information Bottleneck (Tishby/Pereira/Bialek 1999)
    # beta trades I(X;T) compression against I(T;Y) preservation.
    "information_bottleneck.enabled": "true",
    "information_bottleneck.n_clusters": "32",
    "information_bottleneck.beta": "5.0",
    "information_bottleneck.max_iters": "1e2",
    "information_bottleneck.tol": "1e-4",
    # META-165 — Minimum Description Length (Rissanen 1978)
    # Two-part code; param_precision_bits per parameter.
    "mdl_selector.enabled": "true",
    "mdl_selector.param_precision_bits": "8",
    "mdl_selector.min_samples": "16",
    # META-166 — Akaike Information Criterion (Akaike 1974)
    # Pure formula; no tunable hyperparameters beyond an enable flag.
    "aic_selector.enabled": "true",
    "aic_selector.min_models": "2",
    # META-167 — Bayesian Information Criterion (Schwarz 1978)
    # Same shape as AIC; consistency requires n_samples >= 2.
    "bic_selector.enabled": "true",
    "bic_selector.min_models": "2",
    "bic_selector.min_samples": "2",
    # =====================================================================
    # BLOCK Q10 — Clustering (META-168..175)
    # Winner: META-168 k-means (classic baseline). Others pre-filled at false.
    # =====================================================================
    # META-168 — k-means (Lloyd 1982 + k-means++ seeding) — WINNER
    # Common defaults: K=8 starting centroids, tol = 1e-4 inertia.
    "kmeans.enabled": "true",
    "kmeans.n_clusters": "8",
    "kmeans.max_iters": "3e2",
    "kmeans.tol": "1e-4",
    "kmeans.kmeans_plus_plus_seeding": "true",
    # META-169 — k-medoids PAM (Kaufman & Rousseeuw 1987)
    # Robust alternate; off by default until outlier-heavy data is observed.
    "kmedoids_pam.enabled": "false",
    "kmedoids_pam.n_clusters": "8",
    "kmedoids_pam.max_iters": "3e2",
    # META-170 — DBSCAN (Ester 1996)
    # Density-based; eps and min_pts must be tuned per embedding scale.
    "dbscan.enabled": "false",
    "dbscan.eps": "0.5",
    "dbscan.min_pts": "5",
    # META-171 — HDBSCAN (Campello 2013)
    # Hierarchical density; min_cluster_size is the only required knob.
    "hdbscan.enabled": "false",
    "hdbscan.min_cluster_size": "5",
    "hdbscan.min_samples": "5",
    # META-172 — OPTICS (Ankerst 1999)
    # Reachability ordering; eps acts as a maximum radius cutoff.
    "optics.enabled": "false",
    "optics.eps": "0.5",
    "optics.min_pts": "5",
    # META-173 — Mean Shift (Comaniciu & Meer 2002)
    # Bandwidth chosen via Scott rule fallback if not set; tol stops trajectory.
    "mean_shift.enabled": "false",
    "mean_shift.bandwidth": "1.0",
    "mean_shift.kernel": "gaussian",
    "mean_shift.max_iters": "3e2",
    "mean_shift.tol": "1e-3",
    # META-174 — Affinity Propagation (Frey & Dueck 2007)
    # Damping in [0.5, 1); 0.9 is the usual robust choice for noisy similarity.
    "affinity_propagation.enabled": "false",
    "affinity_propagation.damping": "0.9",
    "affinity_propagation.max_iters": "2e2",
    "affinity_propagation.tol": "1e-4",
    # META-175 — BIRCH (Zhang 1996)
    # Branching factor and threshold control CF-tree growth.
    "birch.enabled": "false",
    "birch.branching_factor": "5e1",
    "birch.threshold": "0.5",
    # =====================================================================
    # BLOCK Q11 — Feature attribution (META-176..180)
    # ALL 5 enabled — SHAP, LIME, Permutation, IG, MDI are different lenses.
    # =====================================================================
    # META-176 — Permutation Importance (Breiman 2001)
    # n_repeats=30 is the sklearn standard giving SE ~ 1/sqrt(30).
    "permutation_importance.enabled": "true",
    "permutation_importance.n_repeats": "3e1",
    "permutation_importance.random_seed": "42",
    # META-177 — KernelSHAP (Lundberg & Lee 2017)
    # 2000 coalition samples is the practical default for d <= 30.
    "shap_kernel.enabled": "true",
    "shap_kernel.n_coalition_samples": "2e3",
    "shap_kernel.background_size": "1e2",
    "shap_kernel.random_seed": "42",
    # META-178 — LIME (Ribeiro 2016)
    # 5000 perturbations + Lasso surrogate is the lime package default.
    "lime.enabled": "true",
    "lime.n_samples": "5e3",
    "lime.kernel_width": "0.75",
    "lime.lasso_alpha": "0.01",
    "lime.random_seed": "42",
    # META-179 — Integrated Gradients (Sundararajan 2017)
    # 50 Riemann steps balances accuracy and forward-pass cost.
    "integrated_gradients.enabled": "true",
    "integrated_gradients.n_steps": "5e1",
    "integrated_gradients.completeness_warn_gap": "0.01",
    # META-180 — Mean Decrease Impurity (Breiman 2001)
    # Pure aggregation over a fitted forest; only the normalize toggle matters.
    "mdi_importance.enabled": "true",
    "mdi_importance.normalize": "true",
    # =====================================================================
    # BLOCK Q12 — Active learning (META-181..185)
    # ALL 5 enabled — different selection strategies that can be paired.
    # =====================================================================
    # META-181 — Uncertainty Sampling (Lewis & Catlett 1994)
    # Entropy strategy is the most informative for >=3 classes.
    "uncertainty_sampling.enabled": "true",
    "uncertainty_sampling.strategy": "entropy",
    "uncertainty_sampling.top_k": "1e1",
    # META-182 — Query by Committee (Seung 1992)
    # Committee size = 5 is the canonical default for reliable vote entropy.
    "query_by_committee.enabled": "true",
    "query_by_committee.committee_size": "5",
    "query_by_committee.top_k": "1e1",
    # META-183 — Expected Model Change (Settles & Craven 2008)
    # Gradient-norm scoring under the model's posterior.
    "expected_model_change.enabled": "true",
    "expected_model_change.top_k": "1e1",
    # META-184 — Density-Weighted Sampling (Settles 2012)
    # beta=1 weights uncertainty by representativeness equally.
    "density_weighted_sampling.enabled": "true",
    "density_weighted_sampling.beta": "1.0",
    "density_weighted_sampling.top_k": "1e1",
    # META-185 — Batch-Mode Active Learning (Hoi 2006)
    # Batch size = 10, lambda controls diversity penalty (submodular).
    "batch_mode_al.enabled": "true",
    "batch_mode_al.batch_size": "1e1",
    "batch_mode_al.lambda_redundancy": "0.5",
    # =====================================================================
    # BLOCK Q13 — Semi-supervised (META-186..190)
    # Winner: META-188 Label propagation (graph-based, established for forums).
    # =====================================================================
    # META-186 — Self-Training (Scudder 1965)
    # Threshold tau=0.95 is the standard high-confidence pseudo-label cutoff.
    "self_training.enabled": "false",
    "self_training.tau": "0.95",
    # META-187 — Co-Training (Blum & Mitchell 1998)
    # Two-view mutual teaching; symmetric thresholds keep balance.
    "co_training.enabled": "false",
    "co_training.tau1": "0.95",
    "co_training.tau2": "0.95",
    "co_training.cap_per_class": "1e1",
    # META-188 — Label Propagation Graph (Zhu/Ghahramani/Lafferty 2003) — WINNER
    # alpha=0.99 gives strong smoothing; tol checks convergence per iter.
    "label_propagation.enabled": "true",
    "label_propagation.alpha": "0.99",
    "label_propagation.max_iter": "3e1",
    "label_propagation.tol": "1e-3",
    # META-189 — MixMatch (Berthelot 2019)
    # K=2 augmentations, sharpen T=0.5, Mixup alpha=0.75 per the paper.
    "mixmatch.enabled": "false",
    "mixmatch.k_augmentations": "2",
    "mixmatch.sharpen_temperature": "0.5",
    "mixmatch.alpha_beta": "0.75",
    "mixmatch.lambda_unsupervised": "75.0",
    # META-190 — FixMatch (Sohn 2020)
    # tau=0.95 is the high-confidence threshold from the paper.
    "fixmatch.enabled": "false",
    "fixmatch.tau": "0.95",
    "fixmatch.lambda_unsupervised": "1.0",
    # =====================================================================
    # BLOCK Q14 — Causal inference (META-191..195)
    # ALL 5 enabled — IPW, DML, DR, Causal Forest, T/S/X estimate
    # different quantities and can be reported together.
    # =====================================================================
    # META-191 — Inverse Propensity Weighting (Rosenbaum & Rubin 1983)
    # eps_clip = 1e-3 prevents Inf when propensity drifts to the boundary.
    "ipw.enabled": "true",
    "ipw.eps_clip": "1e-3",
    # META-192 — Double Machine Learning (Chernozhukov 2018)
    # Cross-fit folds K=5; orthogonalisation is the core of the estimator.
    "dml.enabled": "true",
    "dml.cross_fit_folds": "5",
    # META-193 — Doubly Robust / AIPW (Bang & Robins 2005)
    # Same eps_clip discipline as IPW; consistent if either nuisance is right.
    "doubly_robust.enabled": "true",
    "doubly_robust.eps_clip": "1e-3",
    # META-194 — Causal Forest (Athey/Tibshirani/Wager 2019)
    # 500 honest trees, subsample 0.5, depth 12 follows the GRF defaults.
    "causal_forest.enabled": "true",
    "causal_forest.n_trees": "5e2",
    "causal_forest.subsample_frac": "0.5",
    "causal_forest.max_depth": "12",
    "causal_forest.min_leaf_size": "5",
    "causal_forest.random_seed": "42",
    # META-195 — T/S/X-Learner Family (Künzel 2019)
    # Default to X-learner — most robust on imbalanced treatment.
    "meta_learners.enabled": "true",
    "meta_learners.variant": "x",
    # =====================================================================
    # BLOCK Q15 — Reinforcement Learning (META-196..201)
    # Winner: META-200 PPO (state-of-the-art on-policy RL).
    # =====================================================================
    # META-196 — Q-learning (Watkins & Dayan 1992)
    # alpha=0.1, gamma=0.99 are the canonical tabular control defaults.
    "q_learning.enabled": "false",
    "q_learning.alpha": "0.1",
    "q_learning.gamma": "0.99",
    # META-197 — SARSA (Rummery & Niranjan 1994)
    # Same magnitudes as Q-learning; SARSA is on-policy and conservative.
    "sarsa.enabled": "false",
    "sarsa.alpha": "0.1",
    "sarsa.gamma": "0.99",
    # META-198 — REINFORCE (Williams 1992)
    # alpha=1e-3 is the standard policy-gradient learning rate; gamma=0.99.
    "reinforce.enabled": "false",
    "reinforce.alpha": "1e-3",
    "reinforce.gamma": "0.99",
    "reinforce.use_baseline": "false",
    # META-199 — Actor-Critic (Konda & Tsitsiklis 2000)
    # Asymmetric rates: critic learns faster than actor.
    "actor_critic.enabled": "false",
    "actor_critic.alpha_actor": "1e-4",
    "actor_critic.alpha_critic": "1e-3",
    "actor_critic.gamma": "0.99",
    # META-200 — PPO (Schulman 2017) — WINNER
    # Clip eps=0.2, K=4 epochs, GAE lambda=0.95 — paper defaults.
    "ppo.enabled": "true",
    "ppo.clip_eps": "0.2",
    "ppo.epochs": "4",
    "ppo.gae_lambda": "0.95",
    "ppo.gamma": "0.99",
    "ppo.learning_rate": "3e-4",
    "ppo.minibatch_size": "64",
    # META-201 — DDPG (Lillicrap 2016)
    # Polyak tau=5e-3, replay 1e6 transitions are the paper defaults.
    "ddpg.enabled": "false",
    "ddpg.polyak_tau": "5e-3",
    "ddpg.replay_buffer_capacity": "1e6",
    "ddpg.batch_size": "64",
    "ddpg.gamma": "0.99",
    "ddpg.alpha_actor": "1e-4",
    "ddpg.alpha_critic": "1e-3",
    # =====================================================================
    # BLOCK Q16 — Bandits (META-202..205)
    # Winner: META-203 LinUCB (linear payoff with regret bound).
    # =====================================================================
    # META-202 — epsilon-greedy (Watkins 1989)
    # epsilon=0.1 is the standard exploration rate baseline.
    "epsilon_greedy.enabled": "false",
    "epsilon_greedy.epsilon": "0.1",
    "epsilon_greedy.epsilon_min": "0.01",
    "epsilon_greedy.decay_lambda": "0.0",
    # META-203 — LinUCB (Li/Chu/Langford/Schapire 2010) — WINNER
    # alpha=1.0 gives the canonical regret bound; ridge_lambda regularises A.
    "linucb.enabled": "true",
    "linucb.alpha": "1.0",
    "linucb.ridge_lambda": "1.0",
    "linucb.feature_dim": "8",
    # META-204 — LinTS (Agrawal & Goyal 2013)
    # v=0.25 is a calibrated exploration variance for click-rate problems.
    "lints.enabled": "false",
    "lints.v": "0.25",
    "lints.ridge_lambda": "1.0",
    "lints.feature_dim": "8",
    # META-205 — Cascading Bandits (Kveton 2015)
    # K=10 list size matches typical SERP slot count.
    "cascading_bandits.enabled": "false",
    "cascading_bandits.k_list_size": "1e1",
    "cascading_bandits.ucb_constant": "1.5",
}
