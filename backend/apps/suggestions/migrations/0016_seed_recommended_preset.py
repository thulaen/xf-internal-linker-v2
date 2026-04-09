"""
Migration 0016 — seed the "Recommended" system preset and write its weights
directly to AppSetting so they are live from first install.

Values are derived from the Part 1 research table (SEO-optimised starting point
for an internal linking system on a forum/community site).

After approximately one month of live GSC and GA4 data, the monthly R auto-tune
task (FR-018) will refine these values.  The preset record will always show what
was originally recommended, and the operator can reload it at any time.
"""

from django.db import migrations

# ---------------------------------------------------------------------------
# The researched preset weights (flat key → string value map).
# Any key not present here falls back to the signal's hardcoded default when
# the preset is applied via the API.
# ---------------------------------------------------------------------------
RECOMMENDED_WEIGHTS: dict[str, str] = {
    # ── Core weights (sum = 1.0) ──────────────────────────────────────
    # Reduced w_semantic slightly: forum jargon makes keyword overlap more
    # diagnostic than in general-web search (BEIR hybrid IR research).
    # Increased w_node: same-section links concentrate topical authority
    # (Google guidance + Semrush silo research).
    "w_semantic": "0.40",
    "w_keyword": "0.25",
    "w_node": "0.20",
    "w_quality": "0.15",
    # ── Silo (disabled at cold start — operator must configure silos) ──
    "silo.mode": "disabled",
    "silo.same_silo_boost": "0.05",
    "silo.cross_silo_penalty": "0.05",
    # ── Weighted authority ────────────────────────────────────────────
    # 0.10 instead of 0.20 default: avoids over-privileging PageRank at
    # the expense of relevance signals at cold start.
    "weighted_authority.ranking_weight": "0.10",
    "weighted_authority.position_bias": "0.5",
    "weighted_authority.empty_anchor_factor": "0.6",
    "weighted_authority.bare_url_factor": "0.35",
    "weighted_authority.weak_context_factor": "0.75",
    "weighted_authority.isolated_context_factor": "0.45",
    # ── Rare-term propagation (enabled — safe from day 1) ─────────────
    "rare_term_propagation.enabled": "true",
    "rare_term_propagation.ranking_weight": "0.05",
    "rare_term_propagation.max_document_frequency": "3",
    "rare_term_propagation.minimum_supporting_related_pages": "2",
    # ── Field-aware relevance (enabled — title matches are highly diagnostic) ──
    "field_aware_relevance.ranking_weight": "0.10",
    "field_aware_relevance.title_field_weight": "0.40",
    "field_aware_relevance.body_field_weight": "0.30",
    "field_aware_relevance.scope_field_weight": "0.15",
    "field_aware_relevance.learned_anchor_field_weight": "0.15",
    # ── GA4/GSC (disabled at cold start — no data yet) ────────────────
    # Raise to 0.10–0.15 after 30+ days of GSC/GA4 data.
    "ga4_gsc.ranking_weight": "0.00",
    # ── Click distance (enabled — Botify: crawl depth is a strong signal) ──
    "click_distance.ranking_weight": "0.07",
    "click_distance.k_cd": "4.0",
    "click_distance.b_cd": "0.75",
    "click_distance.b_ud": "0.25",
    # ── Explore/exploit (disabled at cold start — needs feedback history) ──
    "explore_exploit.enabled": "false",
    "explore_exploit.ranking_weight": "0.10",
    "explore_exploit.exploration_rate": "1.0",
    # ── Clustering (enabled — prevents near-duplicate link spam) ──────
    "clustering.enabled": "true",
    "clustering.similarity_threshold": "0.04",
    "clustering.suppression_penalty": "20.0",
    # ── Slate diversity (enabled — prevents 3 links to near-identical pages) ──
    "slate_diversity.enabled": "true",
    "slate_diversity.diversity_lambda": "0.65",
    "slate_diversity.score_window": "0.30",
    "slate_diversity.similarity_cap": "0.90",
    # ── Link freshness (light signal — safe for evergreen forum content) ──
    "link_freshness.ranking_weight": "0.05",
    "link_freshness.recent_window_days": "30",
    "link_freshness.newest_peer_percent": "0.25",
    "link_freshness.min_peer_count": "3",
    "link_freshness.w_recent": "0.35",
    "link_freshness.w_growth": "0.35",
    "link_freshness.w_cohort": "0.20",
    "link_freshness.w_loss": "0.10",
    # ── Phrase matching (enabled — anchor text is a confirmed Google factor) ──
    "phrase_matching.ranking_weight": "0.08",
    "phrase_matching.enable_anchor_expansion": "true",
    "phrase_matching.enable_partial_matching": "true",
    "phrase_matching.context_window_tokens": "8",
    # ── Learned anchor (conservative start — gains value as data grows) ──
    "learned_anchor.ranking_weight": "0.05",
    "learned_anchor.minimum_anchor_sources": "2",
    "learned_anchor.minimum_family_support_share": "0.15",
    "learned_anchor.enable_noise_filter": "true",
}

# Metadata for writing to AppSetting (value_type + category + description).
_SETTING_META: dict[str, dict] = {
    "w_semantic": {
        "value_type": "float",
        "category": "ml",
        "description": "Core semantic similarity weight (cosine, BAAI/bge-m3).",
    },
    "w_keyword": {
        "value_type": "float",
        "category": "ml",
        "description": "Core keyword/Jaccard overlap weight.",
    },
    "w_node": {
        "value_type": "float",
        "category": "ml",
        "description": "Core node-affinity / scope-hierarchy weight.",
    },
    "w_quality": {
        "value_type": "float",
        "category": "ml",
        "description": "Core host-page quality (log-normalized PageRank) weight.",
    },
    "silo.mode": {
        "value_type": "str",
        "category": "ml",
        "description": "Topical silo enforcement mode.",
    },
    "silo.same_silo_boost": {
        "value_type": "float",
        "category": "ml",
        "description": "Score bonus for same-silo candidates in prefer_same_silo mode.",
    },
    "silo.cross_silo_penalty": {
        "value_type": "float",
        "category": "ml",
        "description": "Score penalty for cross-silo candidates in prefer_same_silo mode.",
    },
    "weighted_authority.ranking_weight": {
        "value_type": "float",
        "category": "ml",
        "description": "Ranking weight for the destination PageRank authority signal.",
    },
    "weighted_authority.position_bias": {
        "value_type": "float",
        "category": "ml",
        "description": "How much later links within a page are down-weighted.",
    },
    "weighted_authority.empty_anchor_factor": {
        "value_type": "float",
        "category": "ml",
        "description": "Multiplier for links with no anchor text.",
    },
    "weighted_authority.bare_url_factor": {
        "value_type": "float",
        "category": "ml",
        "description": "Multiplier for naked URL links.",
    },
    "weighted_authority.weak_context_factor": {
        "value_type": "float",
        "category": "ml",
        "description": "Multiplier for links with prose on only one side.",
    },
    "weighted_authority.isolated_context_factor": {
        "value_type": "float",
        "category": "ml",
        "description": "Multiplier for isolated or list-like links.",
    },
    "rare_term_propagation.enabled": {
        "value_type": "bool",
        "category": "ml",
        "description": "Whether FR-010 rare-term propagation profiles are built.",
    },
    "rare_term_propagation.ranking_weight": {
        "value_type": "float",
        "category": "ml",
        "description": "Ranking weight for the FR-010 rare-term propagation signal.",
    },
    "rare_term_propagation.max_document_frequency": {
        "value_type": "int",
        "category": "ml",
        "description": "Max site-wide document frequency for a term to count as rare.",
    },
    "rare_term_propagation.minimum_supporting_related_pages": {
        "value_type": "int",
        "category": "ml",
        "description": "Min related pages supporting a rare term before it activates.",
    },
    "field_aware_relevance.ranking_weight": {
        "value_type": "float",
        "category": "ml",
        "description": "Ranking weight for the FR-011 field-aware relevance signal.",
    },
    "field_aware_relevance.title_field_weight": {
        "value_type": "float",
        "category": "ml",
        "description": "Share of field-aware relevance assigned to title matches.",
    },
    "field_aware_relevance.body_field_weight": {
        "value_type": "float",
        "category": "ml",
        "description": "Share of field-aware relevance assigned to body matches.",
    },
    "field_aware_relevance.scope_field_weight": {
        "value_type": "float",
        "category": "ml",
        "description": "Share of field-aware relevance assigned to scope-label matches.",
    },
    "field_aware_relevance.learned_anchor_field_weight": {
        "value_type": "float",
        "category": "ml",
        "description": "Share of field-aware relevance assigned to learned-anchor vocabulary.",
    },
    "ga4_gsc.ranking_weight": {
        "value_type": "float",
        "category": "ml",
        "description": "Ranking weight for the GA4/GSC content-value signal.",
    },
    "click_distance.ranking_weight": {
        "value_type": "float",
        "category": "ml",
        "description": "Ranking weight for the FR-012 click-distance structural prior.",
    },
    "click_distance.k_cd": {
        "value_type": "float",
        "category": "ml",
        "description": "Depth sensitivity (k) for the click-distance score.",
    },
    "click_distance.b_cd": {
        "value_type": "float",
        "category": "ml",
        "description": "Click-distance bias weight.",
    },
    "click_distance.b_ud": {
        "value_type": "float",
        "category": "ml",
        "description": "URL-depth bias weight.",
    },
    "explore_exploit.enabled": {
        "value_type": "bool",
        "category": "ml",
        "description": "Whether FR-013 explore/exploit feedback reranking is active.",
    },
    "explore_exploit.ranking_weight": {
        "value_type": "float",
        "category": "ml",
        "description": "Multiplier weight for the feedback-driven score component.",
    },
    "explore_exploit.exploration_rate": {
        "value_type": "float",
        "category": "ml",
        "description": "UCB1 exploration rate (k factor).",
    },
    "clustering.enabled": {
        "value_type": "bool",
        "category": "ml",
        "description": "Whether FR-014 near-duplicate clustering and suppression is active.",
    },
    "clustering.similarity_threshold": {
        "value_type": "float",
        "category": "ml",
        "description": "Cosine distance threshold for near-duplicate grouping.",
    },
    "clustering.suppression_penalty": {
        "value_type": "float",
        "category": "ml",
        "description": "Score penalty applied to non-canonical cluster members.",
    },
    "slate_diversity.enabled": {
        "value_type": "bool",
        "category": "ml",
        "description": "Whether FR-015 MMR slate diversity reranking is active.",
    },
    "slate_diversity.diversity_lambda": {
        "value_type": "float",
        "category": "ml",
        "description": "MMR lambda: 1.0 = pure relevance, 0.0 = pure diversity.",
    },
    "slate_diversity.score_window": {
        "value_type": "float",
        "category": "ml",
        "description": "Max score gap from top candidate for MMR eligibility.",
    },
    "slate_diversity.similarity_cap": {
        "value_type": "float",
        "category": "ml",
        "description": "Cosine similarity above which two destinations are flagged as redundant.",
    },
    "link_freshness.ranking_weight": {
        "value_type": "float",
        "category": "link_freshness",
        "description": "Ranking weight for the FR-007 link freshness signal.",
    },
    "link_freshness.recent_window_days": {
        "value_type": "int",
        "category": "link_freshness",
        "description": "Day window used to measure recent inbound link growth.",
    },
    "link_freshness.newest_peer_percent": {
        "value_type": "float",
        "category": "link_freshness",
        "description": "Share of newest inbound peers used for cohort freshness.",
    },
    "link_freshness.min_peer_count": {
        "value_type": "int",
        "category": "link_freshness",
        "description": "Min inbound peer rows before link freshness activates.",
    },
    "link_freshness.w_recent": {
        "value_type": "float",
        "category": "link_freshness",
        "description": "Weight for the recent-new-links component.",
    },
    "link_freshness.w_growth": {
        "value_type": "float",
        "category": "link_freshness",
        "description": "Weight for the recent-vs-previous growth delta component.",
    },
    "link_freshness.w_cohort": {
        "value_type": "float",
        "category": "link_freshness",
        "description": "Weight for the newest-cohort freshness component.",
    },
    "link_freshness.w_loss": {
        "value_type": "float",
        "category": "link_freshness",
        "description": "Weight for recent inbound-link disappearance pressure.",
    },
    "phrase_matching.ranking_weight": {
        "value_type": "float",
        "category": "anchor",
        "description": "Ranking weight for the FR-008 phrase-match signal.",
    },
    "phrase_matching.enable_anchor_expansion": {
        "value_type": "bool",
        "category": "anchor",
        "description": "Whether anchor extraction expands beyond the title fallback.",
    },
    "phrase_matching.enable_partial_matching": {
        "value_type": "bool",
        "category": "anchor",
        "description": "Whether bounded partial phrase matches are allowed.",
    },
    "phrase_matching.context_window_tokens": {
        "value_type": "int",
        "category": "anchor",
        "description": "Token window for FR-008 local corroboration.",
    },
    "learned_anchor.ranking_weight": {
        "value_type": "float",
        "category": "anchor",
        "description": "Ranking weight for the FR-009 learned-anchor corroboration signal.",
    },
    "learned_anchor.minimum_anchor_sources": {
        "value_type": "int",
        "category": "anchor",
        "description": "Min distinct source pages before a learned anchor is trusted.",
    },
    "learned_anchor.minimum_family_support_share": {
        "value_type": "float",
        "category": "anchor",
        "description": "Min family support share for a learned anchor to activate.",
    },
    "learned_anchor.enable_noise_filter": {
        "value_type": "bool",
        "category": "anchor",
        "description": "Whether generic anchors like 'click here' are filtered out.",
    },
}


def seed_recommended_preset(apps, schema_editor):
    WeightPreset = apps.get_model("suggestions", "WeightPreset")
    AppSetting = apps.get_model("core", "AppSetting")

    # 1. Create (or update) the system preset record.
    preset, _ = WeightPreset.objects.update_or_create(
        name="Recommended",
        defaults={
            "is_system": True,
            "weights": RECOMMENDED_WEIGHTS,
        },
    )

    # 2. Write every key from RECOMMENDED_WEIGHTS into AppSetting.
    #    Keys absent from RECOMMENDED_WEIGHTS fall back to the signal's
    #    hardcoded default (handled by the pipeline code — nothing to do here).
    for key, value in RECOMMENDED_WEIGHTS.items():
        meta = _SETTING_META.get(
            key, {"value_type": "str", "category": "ml", "description": key}
        )
        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "value_type": meta["value_type"],
                "category": meta["category"],
                "description": meta.get("description", key),
                "is_secret": False,
            },
        )


def unseed_recommended_preset(apps, schema_editor):
    # Reverse: remove the preset record only.
    # AppSetting values intentionally left in place — removing them would
    # reset the pipeline to code defaults unexpectedly on a reverse migration.
    WeightPreset = apps.get_model("suggestions", "WeightPreset")
    WeightPreset.objects.filter(name="Recommended", is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0015_weight_preset_and_history"),
        ("core", "0003_alter_appsetting_category"),
    ]

    operations = [
        migrations.RunPython(
            seed_recommended_preset, reverse_code=unseed_recommended_preset
        ),
    ]
