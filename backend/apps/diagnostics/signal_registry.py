"""Registry of all 23 scoring and value signals for the Algorithm Weights Diagnostic Tab.

This registry maps signal IDs to their human-readable names, describing their
purpose, and identifying their data persistence (database tables) and
acceleration status (C++ kernels).
"""

from dataclasses import dataclass
from typing import Literal

SignalType = Literal["ranking", "value"]

@dataclass(frozen=True)
class SignalDefinition:
    id: str
    name: str
    type: SignalType
    description: str
    table_name: str
    cpp_kernel: str | None = None
    weight_key: str | None = None

SIGNALS: list[SignalDefinition] = [
    # --- RANKING SIGNALS (16) ---
    SignalDefinition(
        id="semantic_similarity",
        name="Semantic Similarity",
        type="ranking",
        description="Cosine similarity between sentence and destination embeddings (BGE-M3).",
        table_name="content_sentence (embedding), content_contentitem (embedding)",
        cpp_kernel="simsearch.score_and_topk",
        weight_key="w_semantic",
    ),
    SignalDefinition(
        id="keyword_jaccard",
        name="Keyword Jaccard",
        type="ranking",
        description="Overlapping token similarity ratio after stopword removal.",
        table_name="content_sentence (tokens), content_contentitem (tokens)",
        cpp_kernel="texttok.tokenize_text_batch",
        weight_key="w_keyword",
    ),
    SignalDefinition(
        id="node_proximity",
        name="Node Proximity (Affinity)",
        type="ranking",
        description="Scope tree distance (same category, parent, or grandparent).",
        table_name="content_scope",
        weight_key="w_node",
    ),
    SignalDefinition(
        id="post_quality",
        name="Post Quality (Host Auth)",
        type="ranking",
        description="Weighted PageRank of the host page providing the link.",
        table_name="content_contentitem (march_2026_pagerank_score)",
        cpp_kernel="pagerank.pagerank_step",
        weight_key="w_quality",
    ),
    SignalDefinition(
        id="weighted_authority",
        name="Weighted Authority (Dest Auth)",
        type="ranking",
        description="Weighted PageRank of the destination page receiving the link.",
        table_name="content_contentitem (march_2026_pagerank_score)",
        cpp_kernel="pagerank.pagerank_step",
        weight_key="weighted_authority.ranking_weight",
    ),
    SignalDefinition(
        id="link_freshness",
        name="Link Freshness (Velocity)",
        type="ranking",
        description="Decay-adjusted score based on time since last update or reply.",
        table_name="content_contentitem (link_freshness_score)",
        weight_key="link_freshness.ranking_weight",
    ),
    SignalDefinition(
        id="phrase_match",
        name="Phrase Match",
        type="ranking",
        description="Detection of destination title fragments within host sentences.",
        table_name="content_contentitem (title)",
        cpp_kernel="phrasematch.longest_contiguous_overlap",
        weight_key="phrase_matching.ranking_weight",
    ),
    SignalDefinition(
        id="learned_anchor",
        name="Learned Anchor",
        type="ranking",
        description="Corroboration against existing human-created anchor text.",
        table_name="graph_existinglink (anchor_text)",
        weight_key="learned_anchor.ranking_weight",
    ),
    SignalDefinition(
        id="rare_term_propagation",
        name="Rare-Term Propagation",
        type="ranking",
        description="Keyword boost for low-frequency relevant terms across silos.",
        table_name="content_contentitem (tokens)",
        cpp_kernel="rareterm.evaluate_rare_terms",
        weight_key="rare_term_propagation.ranking_weight",
    ),
    SignalDefinition(
        id="field_aware_relevance",
        name="Field-Aware Relevance",
        type="ranking",
        description="Separate weights for title, body, and scope-field matches.",
        table_name="content_contentitem, content_scope",
        cpp_kernel="fieldrel.score_field_tokens",
        weight_key="field_aware_relevance.ranking_weight",
    ),
    SignalDefinition(
        id="search_demand",
        name="GA4/GSC Search Demand",
        type="ranking",
        description="Search impression and click signals from Google Search Console.",
        table_name="analytics_searchmetric",
        weight_key="ga4_gsc.ranking_weight",
    ),
    SignalDefinition(
        id="click_distance",
        name="Click Distance",
        type="ranking",
        description="Graph-crawl shortest path distance between host and destination.",
        table_name="graph_clickdistance",
        weight_key="click_distance.ranking_weight",
    ),
    SignalDefinition(
        id="silo_affinity",
        name="Silo Affinity",
        type="ranking",
        description="Additive boost for same-silo pairs or penalty for cross-silo.",
        table_name="content_scope (silo_group_id)",
        weight_key="silo.mode",
    ),
    SignalDefinition(
        id="cluster_suppression",
        name="Cluster Suppression",
        type="ranking",
        description="Penalty for near-duplicate pages within the same semantic cluster.",
        table_name="content_contentitem (cluster_id)",
        weight_key="clustering.enabled",
    ),
    SignalDefinition(
        id="slate_diversity",
        name="Slate Diversity (MMR)",
        type="ranking",
        description="Maximal Marginal Relevance to prevent repetitive suggestion slates.",
        table_name="None (Runtime Rerank)",
        cpp_kernel="feedrerank.calculate_mmr_scores_batch",
        weight_key="slate_diversity.enabled",
    ),
    SignalDefinition(
        id="feedback_rerank",
        name="Feedback (Explore/Exploit)",
        type="ranking",
        description="Thompson Sampling based on operator acceptance/rejection history.",
        table_name="suggestions_suggestion (status)",
        weight_key="feedback_rerank.enabled",
    ),

    # --- VALUE MODEL SIGNALS (7) ---
    SignalDefinition(
        id="value_relevance",
        name="Value: Relevance",
        type="value",
        description="Destination topical alignment with the global corpus average.",
        table_name="content_contentitem (embedding)",
        weight_key="value_model.w_relevance",
    ),
    SignalDefinition(
        id="value_traffic",
        name="Value: Traffic",
        type="value",
        description="Historical view counts and session volume from GA4.",
        table_name="analytics_suggestiontelemetrydaily (destination_views)",
        weight_key="value_model.w_traffic",
    ),
    SignalDefinition(
        id="value_freshness",
        name="Value: Freshness",
        type="value",
        description="Link freshness score used as a value-model component.",
        table_name="content_contentitem (link_freshness_score)",
        weight_key="value_model.w_freshness",
    ),
    SignalDefinition(
        id="value_authority",
        name="Value: Authority",
        type="value",
        description="PageRank authority used as a value-model component.",
        table_name="content_contentitem (march_2026_pagerank_score)",
        weight_key="value_model.w_authority",
    ),
    SignalDefinition(
        id="value_engagement",
        name="Value: Engagement",
        type="value",
        description="Average engagement time and interaction rates from GA4.",
        table_name="analytics_suggestiontelemetrydaily (total_engagement_time_seconds)",
        weight_key="value_model.w_engagement",
    ),
    SignalDefinition(
        id="value_cooccurrence",
        name="Value: Co-occurrence",
        type="value",
        description="Session-level page co-viewing patterns (collaborative filtering).",
        table_name="cooccurrence_sessioncooccurrencepair",
        weight_key="value_model.w_cooccurrence",
    ),
    SignalDefinition(
        id="value_penalty",
        name="Value: Penalty",
        type="value",
        description="Blocklist and content-type suppression penalties.",
        table_name="None (Dynamic)",
        weight_key="value_model.w_penalty",
    ),

    # --- FUTURE SIGNALS (BACKLOG) ---
    # These placeholders are documented in FEATURE-REQUESTS.md.
    # Uncomment and adjust metadata as each signal's backend is implemented.

    # SignalDefinition(
    #     id="information_gain",
    #     name="Information Gain (Novelty)",
    #     type="ranking",
    #     description="FR-038: Measure of topical novelty compared to source page.",
    #     table_name="suggestions_suggestion (score_information_gain)",
    #     weight_key="information_gain.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="entity_salience",
    #     name="Entity Salience Match",
    #     type="ranking",
    #     description="FR-039: Alignment with source page salient terms.",
    #     table_name="suggestions_suggestion (score_entity_salience_match)",
    #     weight_key="entity_salience.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="multimedia_boost",
    #     name="Multimedia Richness",
    #     type="value",
    #     description="FR-040: Visual richness (video, image coverage, alt text).",
    #     table_name="content_contentitem (multimedia_metadata)",
    #     weight_key="value_model.w_multimedia",
    # ),
    # SignalDefinition(
    #     id="originality_provenance",
    #     name="Originality Provenance",
    #     type="ranking",
    #     description="FR-041: Bias toward earliest version in lexical clusters.",
    #     table_name="content_contentitem (source_published_at)",
    #     weight_key="originality_provenance.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="fact_density",
    #     name="Fact Density Scoring",
    #     type="ranking",
    #     description="FR-042: Concrete information density per word count.",
    #     table_name="suggestions_suggestion (score_fact_density)",
    #     weight_key="fact_density.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="semantic_drift",
    #     name="Semantic Drift Penalty",
    #     type="ranking",
    #     description="FR-043: Penalty for documents that lose focus over time.",
    #     table_name="suggestions_suggestion (score_semantic_drift_penalty)",
    #     weight_key="semantic_drift.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="search_intensity",
    #     name="Search Intensity Signal",
    #     type="ranking",
    #     description="FR-044: Real-time internal site-search demand.",
    #     table_name="analytics_searchmetric (internal_search_demand)",
    #     weight_key="internal_search.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="anchor_diversity",
    #     name="Anchor Diversity Guard",
    #     type="ranking",
    #     description="FR-045: Exact-match phrase repetition guard.",
    #     table_name="suggestions_suggestion (score_anchor_diversity)",
    #     weight_key="anchor_diversity.ranking_weight",
    # ),
]
