"""Forward-declared Phase 2 ranking signal weights — Blocks G through N.

Covers FR-152 through FR-224 (73 feature requests, 146 keys total):
  - Block G: Linguistic and stylistic quality (FR-152 .. FR-161)
  - Block H: Click models (FR-162 .. FR-169)
  - Block I: Pre-retrieval query performance predictors (FR-170 .. FR-177)
  - Block J: Term associations and divergences (FR-178 .. FR-185)
  - Block K: Host- and site-level web-spam signals (FR-186 .. FR-203)
  - Block L: Author and community authority (FR-204 .. FR-212)
  - Block M: Technical page quality and SEO structure (FR-213 .. FR-220)
  - Block N: Passage segmentation algorithms (FR-221 .. FR-224)

These keys are inert until their corresponding FR is implemented and reads them.
They live in a separate file to keep each module under the file-length limit.

``FORWARD_DECLARED_WEIGHTS_PHASE2_SIGNALS_G_O`` is merged into
``RECOMMENDED_PRESET_WEIGHTS`` at import time by the main module.

All keys use ``.enabled="true"`` and ``.ranking_weight="0.0"`` (inert by default).

Source specs: docs/specs/fr152-*.md through docs/specs/fr224-*.md
"""

from __future__ import annotations

FORWARD_DECLARED_WEIGHTS_PHASE2_SIGNALS_G_O: dict[str, str] = {
    # =====================================================================
    # Block G — Linguistic and stylistic quality (FR-152 .. FR-161)
    # =====================================================================
    # FR-152 — Passive Voice Ratio
    "passive_voice.enabled": "true",
    "passive_voice.ranking_weight": "0.0",
    # FR-153 — Nominalization Density
    "nominalization.enabled": "true",
    "nominalization.ranking_weight": "0.0",
    # FR-154 — Hedging Language Density
    "hedging.enabled": "true",
    "hedging.ranking_weight": "0.0",
    # FR-155 — Discourse Connective Density
    "discourse_connective.enabled": "true",
    "discourse_connective.ranking_weight": "0.0",
    # FR-156 — Coh-Metrix Cohesion Score
    "cohesion.enabled": "true",
    "cohesion.ranking_weight": "0.0",
    # FR-157 — Part-of-Speech Diversity
    "pos_diversity.enabled": "true",
    "pos_diversity.ranking_weight": "0.0",
    # FR-158 — Sentence Length Variance
    "sentence_variance.enabled": "true",
    "sentence_variance.ranking_weight": "0.0",
    # FR-159 — Yule-K Lexical Concentration
    "yule_k.enabled": "true",
    "yule_k.ranking_weight": "0.0",
    # FR-160 — MTLD Lexical Diversity
    "mtld.enabled": "true",
    "mtld.ranking_weight": "0.0",
    # FR-161 — Punctuation Entropy
    "punctuation_entropy.enabled": "true",
    "punctuation_entropy.ranking_weight": "0.0",
    # =====================================================================
    # Block H — Click models (FR-162 .. FR-169)
    # =====================================================================
    # FR-162 — Cascade Click Model
    "cascade_click.enabled": "true",
    "cascade_click.ranking_weight": "0.0",
    # FR-163 — Dynamic Bayesian Network Click Model
    "dbn_click.enabled": "true",
    "dbn_click.ranking_weight": "0.0",
    # FR-164 — User Browsing Model
    "user_browsing_model.enabled": "true",
    "user_browsing_model.ranking_weight": "0.0",
    # FR-165 — Position-Bias Click Model
    "position_bias.enabled": "true",
    "position_bias.ranking_weight": "0.0",
    # FR-166 — Dependent Click Model
    "dependent_click.enabled": "true",
    "dependent_click.ranking_weight": "0.0",
    # FR-167 — Click-Chain Click Model
    "click_chain.enabled": "true",
    "click_chain.ranking_weight": "0.0",
    # FR-168 — Click-Graph Random Walk
    "click_graph_walk.enabled": "true",
    "click_graph_walk.ranking_weight": "0.0",
    # FR-169 — Regression Click Propensity
    "regression_click.enabled": "true",
    "regression_click.ranking_weight": "0.0",
    # =====================================================================
    # Block I — Pre-retrieval query performance predictors (FR-170 .. FR-177)
    # =====================================================================
    # FR-170 — Query Clarity Score
    "query_clarity.enabled": "true",
    "query_clarity.ranking_weight": "0.0",
    # FR-171 — Weighted Information Gain
    "weighted_info_gain.enabled": "true",
    "weighted_info_gain.ranking_weight": "0.0",
    # FR-172 — Normalized Query Commitment
    "nqc.enabled": "true",
    "nqc.ranking_weight": "0.0",
    # FR-173 — Simplified Clarity Score
    "simplified_clarity.enabled": "true",
    "simplified_clarity.ranking_weight": "0.0",
    # FR-174 — Query Scope
    "query_scope.enabled": "true",
    "query_scope.ranking_weight": "0.0",
    # FR-175 — Query Feedback Predictor
    "query_feedback.enabled": "true",
    "query_feedback.ranking_weight": "0.0",
    # FR-176 — Average ICTF Pre-Retrieval Predictor
    "avg_ictf.enabled": "true",
    "avg_ictf.ranking_weight": "0.0",
    # FR-177 — SCQ Pre-Retrieval Predictor
    "scq.enabled": "true",
    "scq.ranking_weight": "0.0",
    # =====================================================================
    # Block J — Term associations and divergences (FR-178 .. FR-185)
    # =====================================================================
    # FR-178 — Pointwise Mutual Information
    "pmi.enabled": "true",
    "pmi.ranking_weight": "0.0",
    # FR-179 — Normalized PMI
    "npmi.enabled": "true",
    "npmi.ranking_weight": "0.0",
    # FR-180 — Log-Likelihood Ratio Term Association
    "llr_term.enabled": "true",
    "llr_term.ranking_weight": "0.0",
    # FR-181 — KL Divergence Source-Destination
    "kl_divergence.enabled": "true",
    "kl_divergence.ranking_weight": "0.0",
    # FR-182 — Jensen-Shannon Divergence
    "js_divergence.enabled": "true",
    "js_divergence.ranking_weight": "0.0",
    # FR-183 — Renyi Divergence
    "renyi_divergence.enabled": "true",
    "renyi_divergence.ranking_weight": "0.0",
    # FR-184 — Hellinger Distance
    "hellinger.enabled": "true",
    "hellinger.ranking_weight": "0.0",
    # FR-185 — Word Mover's Distance
    "wmd.enabled": "true",
    "wmd.ranking_weight": "0.0",
    # =====================================================================
    # Block K — Host- and site-level web-spam signals (FR-186 .. FR-203)
    # =====================================================================
    # FR-186 — Site-Level PageRank
    "site_pagerank.enabled": "true",
    "site_pagerank.ranking_weight": "0.0",
    # FR-187 — Host TrustRank
    "host_trustrank.enabled": "true",
    "host_trustrank.ranking_weight": "0.0",
    # FR-188 — SpamRank Propagation
    "spamrank.enabled": "true",
    "spamrank.ranking_weight": "0.0",
    # FR-189 — BadRank Inverse PageRank
    "badrank.enabled": "true",
    "badrank.ranking_weight": "0.0",
    # FR-190 — Host Age Boost
    "host_age.enabled": "true",
    "host_age.ranking_weight": "0.0",
    # FR-191 — Subdomain Diversity Penalty
    "subdomain_diversity.enabled": "true",
    "subdomain_diversity.ranking_weight": "0.0",
    # FR-192 — Doorway Page Detector
    "doorway_page.enabled": "true",
    "doorway_page.ranking_weight": "0.0",
    # FR-193 — Block-Level PageRank
    "block_pagerank.enabled": "true",
    "block_pagerank.ranking_weight": "0.0",
    # FR-194 — Host-Cluster Cohesion
    "host_cluster_cohesion.enabled": "true",
    "host_cluster_cohesion.ranking_weight": "0.0",
    # FR-195 — Link-Pattern Naturalness
    "link_naturalness.enabled": "true",
    "link_naturalness.ranking_weight": "0.0",
    # FR-196 — Cloaking Detector
    "cloaking.enabled": "true",
    "cloaking.ranking_weight": "0.0",
    # FR-197 — Link-Farm Ring Detector
    "link_farm_ring.enabled": "true",
    "link_farm_ring.ranking_weight": "0.0",
    # FR-198 — Keyword Stuffing Detector
    "keyword_stuffing.enabled": "true",
    "keyword_stuffing.ranking_weight": "0.0",
    # FR-199 — Content Spin Detector
    "content_spin.enabled": "true",
    "content_spin.ranking_weight": "0.0",
    # FR-200 — Sybil Attack Detector
    "sybil_attack.enabled": "true",
    "sybil_attack.ranking_weight": "0.0",
    # FR-201 — Astroturf Pattern Detector
    "astroturf.enabled": "true",
    "astroturf.ranking_weight": "0.0",
    # FR-202 — Clickbait Classifier
    "clickbait.enabled": "true",
    "clickbait.ranking_weight": "0.0",
    # FR-203 — Content-Farm Detector
    "content_farm.enabled": "true",
    "content_farm.ranking_weight": "0.0",
    # =====================================================================
    # Block L — Author and community authority (FR-204 .. FR-212)
    # =====================================================================
    # FR-204 — Author H-Index Within Forum
    "author_h_index.enabled": "true",
    "author_h_index.ranking_weight": "0.0",
    # FR-205 — Co-Authorship Graph PageRank
    "coauthor_pagerank.enabled": "true",
    "coauthor_pagerank.ranking_weight": "0.0",
    # FR-206 — Account Age Gravity
    "account_age.enabled": "true",
    "account_age.ranking_weight": "0.0",
    # FR-207 — Edit History Density
    "edit_history.enabled": "true",
    "edit_history.ranking_weight": "0.0",
    # FR-208 — Moderator Endorsement Signal
    "moderator_endorsement.enabled": "true",
    "moderator_endorsement.ranking_weight": "0.0",
    # FR-209 — Reply Quality-to-Post Ratio
    "reply_quality.enabled": "true",
    "reply_quality.ranking_weight": "0.0",
    # FR-210 — Cross-Thread Topic Consistency
    "cross_thread_consistency.enabled": "true",
    "cross_thread_consistency.ranking_weight": "0.0",
    # FR-211 — Trust Propagation User Graph
    "user_trust_propagation.enabled": "true",
    "user_trust_propagation.ranking_weight": "0.0",
    # FR-212 — User EigenTrust
    "user_eigentrust.enabled": "true",
    "user_eigentrust.ranking_weight": "0.0",
    # =====================================================================
    # Block M — Technical page quality and SEO structure (FR-213 .. FR-220)
    # =====================================================================
    # FR-213 — Heading Hierarchy Correctness
    "heading_hierarchy.enabled": "true",
    "heading_hierarchy.ranking_weight": "0.0",
    # FR-214 — Alt-Text Coverage Ratio
    "alt_text_coverage.enabled": "true",
    "alt_text_coverage.ranking_weight": "0.0",
    # FR-215 — Schema.org Completeness
    "schema_completeness.enabled": "true",
    "schema_completeness.ranking_weight": "0.0",
    # FR-216 — Open Graph Completeness
    "open_graph.enabled": "true",
    "open_graph.ranking_weight": "0.0",
    # FR-217 — Mobile-Friendly Score
    "mobile_friendly.enabled": "true",
    "mobile_friendly.ranking_weight": "0.0",
    # FR-218 — Core Web Vital LCP
    "cwv_lcp.enabled": "true",
    "cwv_lcp.ranking_weight": "0.0",
    # FR-219 — Core Web Vital CLS
    "cwv_cls.enabled": "true",
    "cwv_cls.ranking_weight": "0.0",
    # FR-220 — Core Web Vital INP
    "cwv_inp.enabled": "true",
    "cwv_inp.ranking_weight": "0.0",
    # =====================================================================
    # Block N — Passage segmentation algorithms (FR-221 .. FR-224)
    # =====================================================================
    # FR-221 — Passage TextTiling Boundary Strength
    "texttiling.enabled": "true",
    "texttiling.ranking_weight": "0.0",
    # FR-222 — C99 Passage Segmentation
    "c99_segmentation.enabled": "true",
    "c99_segmentation.ranking_weight": "0.0",
    # FR-223 — DotPlotting Topic Boundary
    "dotplotting.enabled": "true",
    "dotplotting.ranking_weight": "0.0",
    # FR-224 — BayesSeg Bayesian Segmentation
    "bayesseg.enabled": "true",
    "bayesseg.ranking_weight": "0.0",
}
