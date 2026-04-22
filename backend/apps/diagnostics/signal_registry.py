"""Registry of every scoring and value signal surfaced to operators.

The registry is the single source of truth that ties a shipped ranking or
value signal to its academic source, spec file, fallback behaviour, and
operator-visible diagnostic surfaces. Every field on
:class:`SignalDefinition` is required by ``docs/BUSINESS-LOGIC-CHECKLIST.md``
(Sections 1, 2, 3, and 6) for a signal to be considered fully governed.

Forward-thinking contract — new fields are optional with safe defaults so
adding a field never breaks existing consumers. Signals marked
``status="active"`` must fill the governance fields;
``validate_signal_contract()`` enforces that at import time and via the
``apps.diagnostics.tests_signal_contract`` test, so CI catches drift the
moment a new signal is added.

Phase SEQ note — If you break a signal out of the inline pipeline into
its own Celery task, the function (or its ``@shared_task(name=...)``)
MUST be prefixed ``compute_signal_`` AND wear
``@with_signal_lock()`` from ``apps.pipeline.decorators``. The CI test
``apps.pipeline.test_signal_lock_coverage`` enforces this at merge
time — missing the decorator causes a fleet-wide throughput hit
because signals would then fight for the same GPU/CPU slot in
parallel. See ``docs/PERFORMANCE.md §4`` and the Phase SEQ section of
the master plan.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SignalType = Literal["ranking", "value"]
SignalStatus = Literal["active", "pending", "deprecated"]
SourceKind = Literal["paper", "patent", "rfc", "heuristic", "internal"]
ArchitectureLane = Literal["cpp_first", "python_only", "python_fallback"]
DiagnosticSurface = Literal[
    "suggestion_detail",
    "weight_diagnostics",
    "system_health",
    "mission_critical",
    "settings",
    "review_filter",
]

# Minimum SuggestionPresentation rows required before feedback reranking
# leaves the neutral prior (BLC §6.4 ranking-engine floor for the
# feedback subsystem).
_FEEDBACK_MIN_PRESENTATIONS = 100


@dataclass(frozen=True)
class SignalDefinition:
    """Machine-readable contract for one ranking or value signal.

    The first seven fields are the historical contract (kept stable for
    existing consumers). Everything below ``weight_key`` is the governance
    contract added for forward-thinking resilience — every field is
    optional with a safe default so new fields can be added without
    breaking existing ``SIGNALS`` entries or external readers.

    For any signal with ``status="active"``, ``validate_signal_contract()``
    requires: ``fr_id``, ``spec_path`` (if set, must point at a real file),
    ``academic_source``, ``source_kind``, ``neutral_value``, and at least
    one entry in ``diagnostic_surfaces``. Those are the fields an operator
    or reviewer needs to answer the four questions in Business Logic
    Checklist §3 without reading logs.
    """

    id: str
    name: str
    type: SignalType
    description: str
    table_name: str
    cpp_kernel: str | None = None
    weight_key: str | None = None

    # ── Governance contract (Business Logic Checklist §1, §2, §3, §6) ──
    status: SignalStatus = "active"
    fr_id: str | None = None
    spec_path: str | None = None
    academic_source: str | None = None
    source_kind: SourceKind | None = None
    architecture_lane: ArchitectureLane = "python_only"
    neutral_value: float | None = None
    min_data_threshold: str | None = None
    diagnostic_surfaces: tuple[DiagnosticSurface, ...] = field(default_factory=tuple)
    benchmark_module: str | None = None
    autotune_included: bool = False
    default_enabled: bool = True
    added_in_phase: str | None = None


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
        fr_id=None,
        spec_path=None,
        academic_source="Chen et al. 2024 - BGE-M3 multilingual embeddings; cosine similarity (Salton 1975)",
        source_kind="paper",
        architecture_lane="cpp_first",
        neutral_value=0.0,
        min_data_threshold=">=10 ContentItem rows with embeddings",
        diagnostic_surfaces=(
            "suggestion_detail",
            "weight_diagnostics",
            "mission_critical",
        ),
        benchmark_module="backend/benchmarks/test_bench_embeddings.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 2",
    ),
    SignalDefinition(
        id="keyword_jaccard",
        name="Keyword Jaccard",
        type="ranking",
        description="Overlapping token similarity ratio after stopword removal.",
        table_name="content_sentence (tokens), content_contentitem (tokens)",
        cpp_kernel="texttok.tokenize_text_batch",
        weight_key="w_keyword",
        fr_id=None,
        spec_path=None,
        academic_source="Jaccard 1912 - The distribution of the flora in the alpine zone",
        source_kind="paper",
        architecture_lane="cpp_first",
        neutral_value=0.0,
        min_data_threshold=">=1 tokenised sentence on host and destination",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics"),
        benchmark_module="backend/benchmarks/test_bench_text.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 2",
    ),
    SignalDefinition(
        id="node_proximity",
        name="Node Proximity (Affinity)",
        type="ranking",
        description="Scope tree distance (same category, parent, or grandparent).",
        table_name="content_scope",
        weight_key="w_node",
        fr_id="FR-005",
        spec_path=None,
        academic_source="Internal scope-tree heuristic derived from forum taxonomy depth",
        source_kind="internal",
        architecture_lane="python_only",
        neutral_value=0.0,
        min_data_threshold=">=2 Scope rows on distinct depths",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics"),
        benchmark_module="backend/benchmarks/test_bench_scoring.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 7",
    ),
    SignalDefinition(
        id="post_quality",
        name="Post Quality (Host Auth)",
        type="ranking",
        description="Weighted PageRank of the host page providing the link.",
        table_name="content_contentitem (march_2026_pagerank_score)",
        cpp_kernel="pagerank.pagerank_step",
        weight_key="w_quality",
        fr_id="FR-006",
        spec_path="docs/specs/fr006-weighted-link-graph.md",
        academic_source="Page et al. 1999 - The PageRank Citation Ranking (Stanford); weighted graph variant per FR-006 spec",
        source_kind="paper",
        architecture_lane="cpp_first",
        neutral_value=0.15,
        min_data_threshold=">=1 ExistingLink edge per host; >=10 ContentItem rows for stable scores",
        diagnostic_surfaces=(
            "suggestion_detail",
            "weight_diagnostics",
            "mission_critical",
        ),
        benchmark_module="backend/benchmarks/test_bench_graph.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 9",
    ),
    SignalDefinition(
        id="weighted_authority",
        name="Weighted Authority (Dest Auth)",
        type="ranking",
        description="Weighted PageRank of the destination page receiving the link.",
        table_name="content_contentitem (march_2026_pagerank_score)",
        cpp_kernel="pagerank.pagerank_step",
        weight_key="weighted_authority.ranking_weight",
        fr_id="FR-006",
        spec_path="docs/specs/fr006-weighted-link-graph.md",
        academic_source="Page et al. 1999 - The PageRank Citation Ranking (Stanford); weighted graph variant per FR-006 spec",
        source_kind="paper",
        architecture_lane="cpp_first",
        neutral_value=0.15,
        min_data_threshold=">=1 ExistingLink edge into destination; >=10 ContentItem rows for stable scores",
        diagnostic_surfaces=(
            "suggestion_detail",
            "weight_diagnostics",
            "mission_critical",
        ),
        benchmark_module="backend/benchmarks/test_bench_graph.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 9",
    ),
    SignalDefinition(
        id="link_freshness",
        name="Link Freshness (Velocity)",
        type="ranking",
        description="Decay-adjusted score based on time since last update or reply.",
        table_name="content_contentitem (link_freshness_score)",
        weight_key="link_freshness.ranking_weight",
        fr_id="FR-007",
        spec_path="docs/specs/fr007-link-freshness-authority.md",
        academic_source="Patent US8407231B2 - freshness decay claim; exponential decay over days since last seen",
        source_kind="patent",
        architecture_lane="python_only",
        neutral_value=0.5,
        min_data_threshold=">=14 days of LinkFreshnessEdge history",
        diagnostic_surfaces=(
            "suggestion_detail",
            "weight_diagnostics",
            "system_health",
        ),
        benchmark_module="backend/benchmarks/test_bench_scoring.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 10",
    ),
    SignalDefinition(
        id="phrase_match",
        name="Phrase Match",
        type="ranking",
        description="Detection of destination title fragments within host sentences.",
        table_name="content_contentitem (title)",
        cpp_kernel="phrasematch.longest_contiguous_overlap",
        weight_key="phrase_matching.ranking_weight",
        fr_id="FR-008",
        spec_path="docs/specs/fr008-phrase-based-matching-anchor-expansion.md",
        academic_source="Patent US7536408B2 - phrase-based indexing; longest contiguous overlap heuristic",
        source_kind="patent",
        architecture_lane="cpp_first",
        neutral_value=0.0,
        min_data_threshold=">=1 tokenised title and >=1 host sentence",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics"),
        benchmark_module="backend/benchmarks/test_bench_text.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 11",
    ),
    SignalDefinition(
        id="learned_anchor",
        name="Learned Anchor",
        type="ranking",
        description="Corroboration against existing human-created anchor text.",
        table_name="graph_existinglink (anchor_text)",
        weight_key="learned_anchor.ranking_weight",
        fr_id="FR-009",
        spec_path="docs/specs/fr009-learned-anchor-vocabulary-corroboration.md",
        academic_source="Brin & Page 1998 - anchor-text as external evidence; corroboration heuristic from FR-009 spec",
        source_kind="paper",
        architecture_lane="python_only",
        neutral_value=0.5,
        min_data_threshold=">=1 inbound ExistingLink with non-empty anchor_text for destination",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics"),
        benchmark_module="backend/benchmarks/test_bench_text.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 12",
    ),
    SignalDefinition(
        id="rare_term_propagation",
        name="Rare-Term Propagation",
        type="ranking",
        description="Keyword boost for low-frequency relevant terms across silos.",
        table_name="content_contentitem (tokens)",
        cpp_kernel="rareterm.evaluate_rare_terms",
        weight_key="rare_term_propagation.ranking_weight",
        fr_id="FR-010",
        spec_path="docs/specs/fr010-rare-term-propagation-across-related-pages.md",
        academic_source="Sparck Jones 1972 - IDF weighting; rare-term propagation heuristic per FR-010 spec",
        source_kind="paper",
        architecture_lane="cpp_first",
        neutral_value=0.0,
        min_data_threshold=">=20 ContentItem rows for stable DF estimates",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics"),
        benchmark_module="backend/benchmarks/test_bench_text.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 13",
    ),
    SignalDefinition(
        id="field_aware_relevance",
        name="Field-Aware Relevance",
        type="ranking",
        description="Separate weights for title, body, and scope-field matches.",
        table_name="content_contentitem, content_scope",
        cpp_kernel="fieldrel.score_field_tokens",
        weight_key="field_aware_relevance.ranking_weight",
        fr_id="FR-011",
        spec_path="docs/specs/fr011-field-aware-relevance-scoring.md",
        academic_source="Robertson et al. 2004 - BM25F: fielded extension of BM25",
        source_kind="paper",
        architecture_lane="cpp_first",
        neutral_value=0.0,
        min_data_threshold=">=1 ContentItem row with non-empty title and body tokens",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics"),
        benchmark_module="backend/benchmarks/test_bench_text.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 14",
    ),
    SignalDefinition(
        id="search_demand",
        name="GA4/GSC Search Demand",
        type="ranking",
        description="Search impression and click signals from Google Search Console.",
        table_name="analytics_searchmetric",
        weight_key="ga4_gsc.ranking_weight",
        fr_id="FR-017",
        spec_path="docs/specs/fr017-gsc-search-outcome-attribution.md",
        academic_source="GSC Search Analytics API (Google Search Central documentation)",
        source_kind="internal",
        architecture_lane="python_only",
        neutral_value=0.0,
        min_data_threshold=">=7 days of SearchMetric rows for target page",
        diagnostic_surfaces=(
            "suggestion_detail",
            "weight_diagnostics",
            "system_health",
        ),
        benchmark_module=None,
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 20",
    ),
    SignalDefinition(
        id="click_distance",
        name="Click Distance",
        type="ranking",
        description="Graph-crawl shortest path distance between host and destination.",
        table_name="graph_clickdistance",
        weight_key="click_distance.ranking_weight",
        fr_id="FR-012",
        spec_path="docs/specs/fr012-click-distance-structural-prior.md",
        academic_source="Boldi et al. 2004 - click-distance as structural prior; BFS shortest-path on internal link graph",
        source_kind="paper",
        architecture_lane="python_only",
        neutral_value=0.5,
        min_data_threshold=">=1 reachable path between host and destination in ExistingLink graph",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics"),
        benchmark_module="backend/benchmarks/test_bench_graph.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 15",
    ),
    SignalDefinition(
        id="silo_affinity",
        name="Silo Affinity",
        type="ranking",
        description="Additive boost for same-silo pairs or penalty for cross-silo.",
        table_name="content_scope (silo_group_id)",
        weight_key="silo.mode",
        fr_id="FR-005",
        spec_path=None,
        academic_source="Topical clustering / site siloing per internal forum taxonomy; operator-defined silo groups",
        source_kind="internal",
        architecture_lane="python_only",
        neutral_value=0.0,
        min_data_threshold=">=1 SiloGroup with >=2 Scope members",
        diagnostic_surfaces=(
            "suggestion_detail",
            "weight_diagnostics",
            "settings",
            "review_filter",
        ),
        benchmark_module=None,
        autotune_included=False,
        default_enabled=True,
        added_in_phase="Phase 7",
    ),
    SignalDefinition(
        id="cluster_suppression",
        name="Cluster Suppression",
        type="ranking",
        description="Penalty for near-duplicate pages within the same semantic cluster.",
        table_name="content_contentitem (cluster_id)",
        weight_key="clustering.enabled",
        fr_id="FR-014",
        spec_path="docs/specs/fr014-near-duplicate-destination-clustering.md",
        academic_source="Broder 1997 - syntactic clustering; MinHash/SimHash near-duplicate detection",
        source_kind="paper",
        architecture_lane="python_only",
        neutral_value=1.0,
        min_data_threshold=">=1 ContentCluster with >=2 member ContentItem rows",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics"),
        benchmark_module=None,
        autotune_included=False,
        default_enabled=True,
        added_in_phase="Phase 17",
    ),
    SignalDefinition(
        id="anchor_diversity",
        name="Anchor Diversity",
        type="ranking",
        description="Penalty for over-reusing the same exact anchor text for one destination.",
        table_name="suggestions_suggestion (score_anchor_diversity)",
        weight_key="anchor_diversity.ranking_weight",
        fr_id="FR-045",
        spec_path="docs/specs/fr045-anchor-diversity-exact-match-reuse-guard.md",
        academic_source="Patent US20110238644A1 - anchor text duplicate-weight reduction; Google Search Central guidance",
        source_kind="patent",
        architecture_lane="python_only",
        neutral_value=1.0,
        min_data_threshold=">=2 Suggestion rows targeting the same destination",
        diagnostic_surfaces=(
            "suggestion_detail",
            "weight_diagnostics",
            "mission_critical",
            "settings",
        ),
        benchmark_module=None,
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 37",
    ),
    SignalDefinition(
        id="keyword_stuffing",
        name="Keyword Stuffing",
        type="ranking",
        description="Penalty for destination pages whose term distribution diverges sharply from the site baseline.",
        table_name="suggestions_suggestion (score_keyword_stuffing)",
        weight_key="keyword_stuffing.ranking_weight",
        fr_id="FR-198",
        spec_path="docs/specs/fr198-keyword-stuffing-detector.md",
        academic_source="Kullback-Leibler divergence on term distributions; Google Panda-style term-density penalty",
        source_kind="paper",
        architecture_lane="python_only",
        neutral_value=1.0,
        min_data_threshold=">=20 ContentItem rows for stable site-baseline term distribution",
        diagnostic_surfaces=(
            "suggestion_detail",
            "weight_diagnostics",
            "mission_critical",
            "settings",
        ),
        benchmark_module=None,
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 37",
    ),
    SignalDefinition(
        id="link_farm",
        name="Link Farm Ring",
        type="ranking",
        description="Penalty for destinations inside dense reciprocal link rings on the internal graph.",
        table_name="suggestions_suggestion (score_link_farm)",
        weight_key="link_farm.ranking_weight",
        fr_id="FR-197",
        spec_path="docs/specs/fr197-link-farm-ring-detector.md",
        academic_source="Gyongyi & Garcia-Molina 2005 - Link Spam Alliances; reciprocal-density detection per FR-197 spec",
        source_kind="paper",
        architecture_lane="python_only",
        neutral_value=1.0,
        min_data_threshold=">=1 ExistingLink edge into destination; graph must have >=10 reciprocal pairs to surface rings",
        diagnostic_surfaces=(
            "suggestion_detail",
            "weight_diagnostics",
            "mission_critical",
            "settings",
        ),
        benchmark_module=None,
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 37",
    ),
    SignalDefinition(
        id="slate_diversity",
        name="Slate Diversity (MMR)",
        type="ranking",
        description="Maximal Marginal Relevance to prevent repetitive suggestion slates.",
        table_name="None (Runtime Rerank)",
        cpp_kernel="feedrerank.calculate_mmr_scores_batch",
        weight_key="slate_diversity.enabled",
        fr_id="FR-015",
        spec_path="docs/specs/fr015-final-slate-diversity-reranking.md",
        academic_source="Carbonell & Goldstein 1998 - MMR, SIGIR; Patent US20070294225A1",
        source_kind="paper",
        architecture_lane="cpp_first",
        neutral_value=1.0,
        min_data_threshold=">=2 scored candidates in the slate",
        diagnostic_surfaces=(
            "suggestion_detail",
            "weight_diagnostics",
            "mission_critical",
        ),
        benchmark_module="backend/benchmarks/test_bench_feedback_rerank.py",
        autotune_included=False,
        default_enabled=True,
        added_in_phase="Phase 18",
    ),
    SignalDefinition(
        id="feedback_rerank",
        name="Feedback (Explore/Exploit)",
        type="ranking",
        description="Thompson Sampling based on operator acceptance/rejection history.",
        table_name="suggestions_suggestion (status)",
        weight_key="feedback_rerank.enabled",
        fr_id="FR-013",
        spec_path="docs/specs/fr013-feedback-driven-explore-exploit-reranking.md",
        academic_source="Thompson 1933 - On the likelihood that one unknown probability exceeds another; Patent US10102292B2",
        source_kind="paper",
        architecture_lane="python_fallback",
        neutral_value=1.0,
        min_data_threshold=f">={_FEEDBACK_MIN_PRESENTATIONS} SuggestionPresentation rows (any age)",
        diagnostic_surfaces=(
            "suggestion_detail",
            "weight_diagnostics",
            "system_health",
        ),
        benchmark_module="backend/benchmarks/test_bench_feedback_rerank.py",
        autotune_included=False,
        default_enabled=True,
        added_in_phase="Phase 16",
    ),
    # --- VALUE MODEL SIGNALS (7) ---
    SignalDefinition(
        id="value_relevance",
        name="Value: Relevance",
        type="value",
        description="Destination topical alignment with the global corpus average.",
        table_name="content_contentitem (embedding)",
        weight_key="value_model.w_relevance",
        fr_id="FR-018",
        spec_path="docs/specs/fr018-auto-tuned-ranking-weights.md",
        academic_source="Centroid similarity in dense embedding space (Chen et al. 2024 BGE-M3)",
        source_kind="paper",
        architecture_lane="cpp_first",
        neutral_value=0.5,
        min_data_threshold=">=20 ContentItem rows with embeddings for stable centroid",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics"),
        benchmark_module="backend/benchmarks/test_bench_embeddings.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 21",
    ),
    SignalDefinition(
        id="value_traffic",
        name="Value: Traffic",
        type="value",
        description="Historical view counts and session volume from GA4.",
        table_name="analytics_suggestiontelemetrydaily (destination_views)",
        weight_key="value_model.w_traffic",
        fr_id="FR-016",
        spec_path="docs/specs/fr016-ga4-suggestion-attribution-user-behavior-telemetry.md",
        academic_source="GA4 Reporting API (Google Analytics documentation)",
        source_kind="internal",
        architecture_lane="python_only",
        neutral_value=0.0,
        min_data_threshold=">=14 days of SuggestionTelemetryDaily rows",
        diagnostic_surfaces=(
            "suggestion_detail",
            "weight_diagnostics",
            "system_health",
        ),
        benchmark_module=None,
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 19",
    ),
    SignalDefinition(
        id="value_freshness",
        name="Value: Freshness",
        type="value",
        description="Link freshness score used as a value-model component.",
        table_name="content_contentitem (link_freshness_score)",
        weight_key="value_model.w_freshness",
        fr_id="FR-007",
        spec_path="docs/specs/fr007-link-freshness-authority.md",
        academic_source="Reuses the FR-007 link_freshness decay signal as a value-model component",
        source_kind="patent",
        architecture_lane="python_only",
        neutral_value=0.5,
        min_data_threshold=">=14 days of LinkFreshnessEdge history",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics"),
        benchmark_module="backend/benchmarks/test_bench_scoring.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 21",
    ),
    SignalDefinition(
        id="value_authority",
        name="Value: Authority",
        type="value",
        description="PageRank authority used as a value-model component.",
        table_name="content_contentitem (march_2026_pagerank_score)",
        weight_key="value_model.w_authority",
        fr_id="FR-006",
        spec_path="docs/specs/fr006-weighted-link-graph.md",
        academic_source="Reuses the FR-006 weighted PageRank authority signal as a value-model component",
        source_kind="paper",
        architecture_lane="cpp_first",
        neutral_value=0.15,
        min_data_threshold=">=10 ContentItem rows for stable PageRank",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics"),
        benchmark_module="backend/benchmarks/test_bench_graph.py",
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 21",
    ),
    SignalDefinition(
        id="value_engagement",
        name="Value: Engagement",
        type="value",
        description="Average engagement time and interaction rates from GA4.",
        table_name="analytics_suggestiontelemetrydaily (total_engagement_time_seconds)",
        weight_key="value_model.w_engagement",
        fr_id="FR-024",
        spec_path="docs/specs/fr024-tiktok-read-through-rate-engagement-signal.md",
        academic_source="TikTok-style read-through rate / GA4 engagement_time; per FR-024 spec",
        source_kind="patent",
        architecture_lane="python_only",
        neutral_value=0.0,
        min_data_threshold=">=14 days of SuggestionTelemetryDaily rows with engagement_time",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics"),
        benchmark_module=None,
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 27",
    ),
    SignalDefinition(
        id="value_cooccurrence",
        name="Value: Co-occurrence",
        type="value",
        description="Session-level page co-viewing patterns (collaborative filtering).",
        table_name="cooccurrence_sessioncooccurrencepair",
        weight_key="value_model.w_cooccurrence",
        fr_id="FR-025",
        spec_path="docs/specs/fr025-session-cooccurrence-collaborative-filtering-behavioral-hubs.md",
        academic_source="Patent US6266649 - Amazon Item-to-Item Collaborative Filtering; session co-viewing",
        source_kind="patent",
        architecture_lane="python_only",
        neutral_value=0.0,
        min_data_threshold=">=50 ContentCooccurrence pairs",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics"),
        benchmark_module=None,
        autotune_included=True,
        default_enabled=True,
        added_in_phase="Phase 28",
    ),
    SignalDefinition(
        id="value_penalty",
        name="Value: Penalty",
        type="value",
        description="Blocklist and content-type suppression penalties.",
        table_name="None (Dynamic)",
        weight_key="value_model.w_penalty",
        fr_id=None,
        spec_path=None,
        academic_source="Operator-defined blocklist and content-type suppression rules (internal governance)",
        source_kind="internal",
        architecture_lane="python_only",
        neutral_value=1.0,
        min_data_threshold="None (dynamic; evaluates per-candidate at runtime)",
        diagnostic_surfaces=("suggestion_detail", "weight_diagnostics", "settings"),
        benchmark_module=None,
        autotune_included=False,
        default_enabled=True,
        added_in_phase="Phase 21",
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
    # --- PATENT-BACKED RANKING SIGNALS (FR-051 to FR-059) ---
    # SignalDefinition(
    #     id="reference_context",
    #     name="Reference Context Scoring",
    #     type="ranking",
    #     description="FR-051: IDF-weighted ±5-token window overlap at insertion point.",
    #     table_name="None (Runtime)",
    #     cpp_kernel="refcontext.ref_context_score",
    #     weight_key="reference_context.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="readability_match",
    #     name="Readability Level Match",
    #     type="ranking",
    #     description="FR-052: Flesch-Kincaid grade level penalty for source/dest mismatch.",
    #     table_name="content_contentitem (readability_grade)",
    #     weight_key="readability_match.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="passage_relevance",
    #     name="Passage-Level Relevance",
    #     type="ranking",
    #     description="FR-053: Best-passage cosine similarity across 5 chunks per page.",
    #     table_name="passage_embeddings",
    #     cpp_kernel="passagesim.passage_max_sim",
    #     weight_key="passage_relevance.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="boilerplate_ratio",
    #     name="Boilerplate-to-Content Ratio",
    #     type="ranking",
    #     description="FR-054: Penalises destinations with >80% template chrome.",
    #     table_name="content_contentitem (content_ratio)",
    #     weight_key="boilerplate_ratio.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="reasonable_surfer",
    #     name="Reasonable Surfer Click Probability",
    #     type="ranking",
    #     description="FR-055: Zone/position/emphasis-weighted link placement scoring.",
    #     table_name="None (Runtime)",
    #     weight_key="reasonable_surfer.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="long_click_ratio",
    #     name="Long-Click Satisfaction",
    #     type="ranking",
    #     description="FR-056: Ratio of 30s+ sessions to <10s bounces on destination.",
    #     table_name="analytics_suggestiontelemetrydaily",
    #     weight_key="long_click_ratio.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="content_update",
    #     name="Content-Update Magnitude",
    #     type="ranking",
    #     description="FR-057: Token symmetric-difference ratio between crawls.",
    #     table_name="content_contentitem (content_update_magnitude)",
    #     weight_key="content_update.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="ngram_quality",
    #     name="N-gram Writing Quality",
    #     type="ranking",
    #     description="FR-058: Inverse perplexity from Kneser-Ney n-gram LM.",
    #     table_name="content_contentitem (ngram_quality_score)",
    #     cpp_kernel="ngramqual.ngram_score",
    #     weight_key="ngram_quality.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="topic_purity",
    #     name="Topic Purity Score",
    #     type="ranking",
    #     description="FR-059: Fraction of on-topic sentences per section.",
    #     table_name="content_contentitem (topic_purity_score)",
    #     weight_key="topic_purity.ranking_weight",
    # ),
    # --- STATISTICAL MODELS (FR-060 to FR-065) ---
    # SignalDefinition(
    #     id="listnet",
    #     name="ListNet Listwise Ranker",
    #     type="ranking",
    #     description="FR-060: LightGBM rank:ndcg model replacing composite scorer.",
    #     table_name="None (Model File)",
    #     weight_key="listnet.enabled",
    # ),
    # SignalDefinition(
    #     id="rankboost",
    #     name="RankBoost Weight Tuner",
    #     type="ranking",
    #     description="FR-061: AdaBoost pairwise weight optimiser (weights-only mode).",
    #     table_name="None (Model File)",
    #     weight_key="rankboost.enabled",
    # ),
    # SignalDefinition(
    #     id="pts_mf",
    #     name="PTS-MF Collaborative Filter",
    #     type="ranking",
    #     description="FR-062: Particle Thompson Sampling + Matrix Factorisation.",
    #     table_name="None (Model File)",
    #     weight_key="pts_mf.enabled",
    # ),
    # SignalDefinition(
    #     id="mhr",
    #     name="Multi-Hyperplane Ranker",
    #     type="ranking",
    #     description="FR-063: 6-pair SVM ensemble with BordaCount aggregation.",
    #     table_name="None (Model File)",
    #     weight_key="mhr.enabled",
    # ),
    # SignalDefinition(
    #     id="spectral_rc",
    #     name="Spectral Relational Clustering",
    #     type="ranking",
    #     description="FR-064: Joint Laplacian eigen decomposition for topic clusters.",
    #     table_name="content_contentitem (spectral_cluster_id)",
    #     weight_key="spectral_rc.enabled",
    # ),
    # SignalDefinition(
    #     id="isotonic_calibration",
    #     name="Isotonic Score Calibration",
    #     type="ranking",
    #     description="FR-065: PAV monotonic calibration layer on composite scores.",
    #     table_name="None (Model File)",
    #     weight_key="isotonic_calibration.enabled",
    # ),
    # --- C++ META-ALGORITHMS (FR-066 to FR-068) ---
    # SignalDefinition(
    #     id="smoothrank",
    #     name="SmoothRank Direct NDCG",
    #     type="ranking",
    #     description="FR-066: Differentiable NDCG via sigmoid position smoothing.",
    #     table_name="None (Model File)",
    #     cpp_kernel="smoothrank.smoothrank_step",
    #     weight_key="smoothrank.enabled",
    # ),
    # SignalDefinition(
    #     id="rank_aggregation",
    #     name="Markov Chain Rank Aggregation",
    #     type="ranking",
    #     description="FR-067: SDP-optimised Markov chain stationary rank combiner.",
    #     table_name="None (Runtime)",
    #     cpp_kernel="rankagg.power_iter",
    #     weight_key="rank_aggregation.enabled",
    # ),
    # SignalDefinition(
    #     id="cascade_rerank",
    #     name="Cascade Telescoping Re-Ranker",
    #     type="ranking",
    #     description="FR-068: 3-stage cascade narrowing all→200→50→10 candidates.",
    #     table_name="None (Runtime)",
    #     cpp_kernel="cascade.stage_score",
    #     weight_key="cascade_rerank.enabled",
    # ),
    # --- SOCIAL MEDIA & TECH PATENT SIGNALS (FR-069 to FR-090) ---
    # SignalDefinition(
    #     id="viral_depth",
    #     name="Viral Propagation Depth",
    #     type="ranking",
    #     description="FR-069: Max sharing-hop depth from Meta patent US10152544B1.",
    #     table_name="content_contentitem (viral_depth_score)",
    #     weight_key="viral_depth.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="viral_recipient",
    #     name="Viral Recipient Authority",
    #     type="ranking",
    #     description="FR-070: Recipient influence scoring from YouTube patent.",
    #     table_name="content_contentitem (viral_recipient_score)",
    #     weight_key="viral_recipient.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="sentiment_score",
    #     name="Document Sentiment Score",
    #     type="ranking",
    #     description="FR-071: VADER compound polarity mapped to [0,1].",
    #     table_name="content_contentitem (sentiment_score)",
    #     weight_key="sentiment_score.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="trending_velocity",
    #     name="Trending Content Velocity",
    #     type="ranking",
    #     description="FR-072: 6-hour engagement acceleration from CrowdTangle patent.",
    #     table_name="content_contentitem (trending_velocity_score)",
    #     weight_key="trending_velocity.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="professional_proximity",
    #     name="Professional Graph Proximity",
    #     type="ranking",
    #     description="FR-073: Jaccard of GA4 user-ID sets from LinkedIn patent.",
    #     table_name="content_contentitem (professional_proximity_score)",
    #     weight_key="professional_proximity.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="influence_score",
    #     name="Social Influence Score",
    #     type="ranking",
    #     description="FR-074: Social reshare-graph PageRank (not link-graph).",
    #     table_name="content_contentitem (influence_score)",
    #     weight_key="influence_score.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="watch_completion",
    #     name="Watch-Time Completion Rate",
    #     type="ranking",
    #     description="FR-075: Video completion ratio from YouTube patent.",
    #     table_name="content_contentitem (watch_completion_score)",
    #     weight_key="watch_completion.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="dwell_profile_match",
    #     name="Dwell-Time Profile Match",
    #     type="ranking",
    #     description="FR-076: Audience attention-span matching.",
    #     table_name="content_contentitem (dwell_profile_match_score)",
    #     weight_key="dwell_profile_match.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="geo_concentration",
    #     name="Geographic Engagement Concentration",
    #     type="ranking",
    #     description="FR-077: Herfindahl index of country engagement shares.",
    #     table_name="content_contentitem (geo_concentration_score)",
    #     weight_key="geo_concentration.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="upvote_velocity",
    #     name="Community Upvote Velocity",
    #     type="ranking",
    #     description="FR-078: First-hour upvote rate from Reddit patent.",
    #     table_name="content_contentitem (upvote_velocity_score)",
    #     weight_key="upvote_velocity.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="spam_filter",
    #     name="Spam Interaction Filter",
    #     type="ranking",
    #     description="FR-079: Bot/spam engagement ratio penalty.",
    #     table_name="content_contentitem (spam_filter_score)",
    #     weight_key="spam_filter.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="freshness_decay_rate",
    #     name="Freshness Decay Rate",
    #     type="ranking",
    #     description="FR-080: Exponential engagement decay rate (evergreen scoring).",
    #     table_name="content_contentitem (freshness_decay_rate_score)",
    #     weight_key="freshness_decay_rate.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="sentiment_alignment",
    #     name="Contextual Sentiment Alignment",
    #     type="ranking",
    #     description="FR-081: Source/dest tonal consistency scoring.",
    #     table_name="None (Runtime)",
    #     weight_key="sentiment_alignment.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="structural_dup",
    #     name="Structural Duplicate Detection",
    #     type="ranking",
    #     description="FR-082: SimHash template-farm detection penalty.",
    #     table_name="content_contentitem (structural_dup_score)",
    #     weight_key="structural_dup.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="anomaly_filter",
    #     name="Anomalous Interaction Filter",
    #     type="ranking",
    #     description="FR-083: Engagement burst z-score anomaly detection.",
    #     table_name="content_contentitem (anomaly_filter_score)",
    #     weight_key="anomaly_filter.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="hashtag_cooccurrence",
    #     name="Hashtag Co-occurrence Strength",
    #     type="ranking",
    #     description="FR-084: PMI between topic tags from Snap patent.",
    #     table_name="content_contentitem (hashtag_cooccurrence_score)",
    #     weight_key="hashtag_cooccurrence.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="format_preference",
    #     name="Content Format Preference",
    #     type="ranking",
    #     description="FR-085: Format affinity scoring (text/image/video) from Snap patent.",
    #     table_name="content_contentitem (format_preference_score)",
    #     weight_key="format_preference.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="retweet_authority",
    #     name="Retweet Graph Authority",
    #     type="ranking",
    #     description="FR-086: Reshare-graph PageRank from Twitter patent.",
    #     table_name="content_contentitem (retweet_authority_score)",
    #     weight_key="retweet_authority.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="reply_depth",
    #     name="Reply Thread Depth",
    #     type="ranking",
    #     description="FR-087: Average comment thread depth from Twitter patent.",
    #     table_name="content_contentitem (reply_depth_score)",
    #     weight_key="reply_depth.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="bookmark_rate",
    #     name="Save/Bookmark Rate",
    #     type="ranking",
    #     description="FR-088: Intent-to-return scoring from Pinterest patent.",
    #     table_name="content_contentitem (bookmark_rate_score)",
    #     weight_key="bookmark_rate.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="visual_consistency",
    #     name="Visual-Topic Consistency",
    #     type="ranking",
    #     description="FR-089: Image-text coherence via CLIP-lite from Pinterest patent.",
    #     table_name="content_contentitem (visual_consistency_score)",
    #     weight_key="visual_consistency.ranking_weight",
    # ),
    # SignalDefinition(
    #     id="cross_platform_engagement",
    #     name="Cross-Platform Engagement",
    #     type="ranking",
    #     description="FR-090: Multi-platform simultaneous spike detection.",
    #     table_name="content_contentitem (cross_platform_score)",
    #     weight_key="cross_platform_engagement.ranking_weight",
    # ),
    # --- OPERATIONAL FEATURES (FR-092 to FR-096) ---
    # SignalDefinition(
    #     id="graph_walk_refresh",
    #     name="Twice-Monthly Graph Walk Refresh",
    #     type="ranking",
    #     description="FR-092: Graph walks on 1st/15th instead of nightly.",
    #     table_name="suggestions_suggestion (graph_walk_diagnostics)",
    #     weight_key="graph_walk_refresh.enabled",
    # ),
    # SignalDefinition(
    #     id="retention_tier1",
    #     name="Extended Nightly Retention",
    #     type="ranking",
    #     description="FR-093: Prune Celery results, alerts, sync jobs nightly.",
    #     table_name="django_celery_results_taskresult, notifications_operatoralert",
    #     weight_key="retention_tier1.enabled",
    # ),
    # SignalDefinition(
    #     id="retention_tier2",
    #     name="Weekly Analytics Pruning",
    #     type="ranking",
    #     description="FR-094: Prune GSC/telemetry/keyword impact weekly.",
    #     table_name="analytics_gscdailyperformance, analytics_suggestiontelemetrydaily",
    #     weight_key="retention_tier2.enabled",
    # ),
    # SignalDefinition(
    #     id="quarterly_maintenance",
    #     name="Quarterly Database Maintenance",
    #     type="ranking",
    #     description="FR-095: VACUUM FULL, REINDEX, entity rebuild quarterly.",
    #     table_name="suggestions_suggestion, content_contentitem",
    #     weight_key="quarterly_maintenance.enabled",
    # ),
    # SignalDefinition(
    #     id="monthly_safe_prune",
    #     name="Monthly Safe Prune",
    #     type="ranking",
    #     description="FR-096: Prune BrokenLink, ImpactReport, old diagnostics JSON.",
    #     table_name="graph_brokenlink, analytics_impactreport",
    #     weight_key="monthly_safe_prune.enabled",
    # ),
]


# ──────────────────────────────────────────────────────────────────────────
# Governance contract enforcement
# ──────────────────────────────────────────────────────────────────────────
#
# `validate_signal_contract()` is a pure function that returns a list of
# plain-English violations. It is NOT called at import time — a strict
# import-time check could break the Docker backend boot over a single
# missing citation, which is a worse failure mode than "signals visible
# but partially governed".
#
# The contract is enforced two ways instead:
#   1. `apps.diagnostics.tests.SignalContractTests` asserts the list is
#      empty on every test run, so CI catches drift the moment a new
#      signal is added.
#   2. `WeightDiagnosticsView` exposes `contract_violations` in its
#      response so operators can see partial-governance state without
#      reading logs (Business Logic Checklist §3 — "reviewer-visible").

_REQUIRED_ACTIVE_FIELDS: tuple[str, ...] = (
    "academic_source",
    "source_kind",
    "neutral_value",
    "diagnostic_surfaces",
)

# Candidate directories that spec files and benchmark modules might live
# under. We resolve spec paths against each candidate root in order so
# the validator works identically on the host (repo root) and inside
# Docker (``/repo`` bind-mount, ``/app`` backend mount, or the layout
# a future deployment might use). Walking upward from ``__file__`` until
# we find the ``AI-CONTEXT.md`` marker is the robust fallback — that
# file is mandatory at the repo root per CLAUDE.md.


def _iter_candidate_roots() -> list[Path]:
    """Return the list of plausible repo-root directories to check.

    Keeps the validator path-check portable across host + Docker layouts.
    """

    candidates: list[Path] = []
    here = Path(__file__).resolve()

    # Walk upward looking for the AI-CONTEXT.md marker (authoritative).
    for parent in here.parents:
        if (parent / "AI-CONTEXT.md").is_file():
            candidates.append(parent)
            break

    # Well-known Docker bind-mount path — present when the host repo is
    # mounted at /repo for AI agents.
    repo_mount = Path("/repo")
    if repo_mount.is_dir() and repo_mount not in candidates:
        candidates.append(repo_mount)

    return candidates


def _resolve_under_any_root(relative_path: str) -> Path | None:
    """Return the first existing file for ``relative_path`` across candidate roots."""

    for root in _iter_candidate_roots():
        candidate = root / relative_path
        if candidate.is_file():
            return candidate
    return None


def validate_signal_contract(
    signals: list[SignalDefinition] | None = None,
) -> list[str]:
    """Return a list of plain-English governance violations.

    An empty list means every ``status="active"`` signal is fully governed
    per Business Logic Checklist §1, §3, and §6.

    Checks performed:

    - No two signals share the same ``id``.
    - Every active signal has ``academic_source``, ``source_kind``,
      ``neutral_value``, and at least one entry in
      ``diagnostic_surfaces``.
    - If ``spec_path`` is set it points at a real file in the repo.
    - If ``benchmark_module`` is set it points at a real file in the
      repo. Hot-path (``architecture_lane="cpp_first"``) active signals
      must have a ``benchmark_module`` set — Code Quality Mandate says
      "no feature is done if its hot path has no benchmark coverage."
    """

    source: list[SignalDefinition] = signals if signals is not None else SIGNALS
    violations: list[str] = []

    seen_ids: set[str] = set()
    for sig in source:
        if sig.id in seen_ids:
            violations.append(f"Duplicate signal id '{sig.id}'.")
        seen_ids.add(sig.id)

        if sig.status != "active":
            continue

        for attr in _REQUIRED_ACTIVE_FIELDS:
            value = getattr(sig, attr)
            if value is None or value == "" or value == ():
                violations.append(
                    f"Signal '{sig.id}' is active but field '{attr}' is unset."
                )

        if sig.spec_path and _resolve_under_any_root(sig.spec_path) is None:
            violations.append(
                f"Signal '{sig.id}' spec_path '{sig.spec_path}' "
                "does not resolve to a file under any candidate repo root."
            )

        if (
            sig.benchmark_module
            and _resolve_under_any_root(sig.benchmark_module) is None
        ):
            violations.append(
                f"Signal '{sig.id}' benchmark_module "
                f"'{sig.benchmark_module}' does not resolve to a file."
            )

        if sig.architecture_lane == "cpp_first" and not sig.benchmark_module:
            violations.append(
                f"Signal '{sig.id}' is cpp_first but has no benchmark_module "
                "(Code Quality Mandate requires 3-input-size benchmarks for "
                "every hot path)."
            )

    return violations


def get_signal(signal_id: str) -> SignalDefinition | None:
    """Return the signal with the given id, or ``None`` if not registered."""

    for sig in SIGNALS:
        if sig.id == signal_id:
            return sig
    return None


def signals_by_status(status: SignalStatus) -> list[SignalDefinition]:
    """Return every signal currently at the given governance status."""

    return [s for s in SIGNALS if s.status == status]
