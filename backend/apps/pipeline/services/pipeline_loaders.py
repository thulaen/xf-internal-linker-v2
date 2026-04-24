"""Pipeline settings loaders.

Extracted from pipeline.py to satisfy file-length limits.
All ``_load_*_settings``, ``_get_*`` config helpers, and the settings
orchestrator live here.
"""

from __future__ import annotations

import logging
from typing import Any

from .feedback_rerank import FeedbackRerankSettings
from .slate_diversity import SlateDiversitySettings
from .anchor_diversity import AnchorDiversitySettings
from .field_aware_relevance import FieldAwareRelevanceSettings
from .learned_anchor import LearnedAnchorSettings
from .keyword_stuffing import KeywordStuffingSettings
from .link_farm import LinkFarmSettings
from .ranker import (
    SiloSettings,
    ClusteringSettings,
)
from .phrase_matching import PhraseMatchingSettings
from .rare_term_propagation import RareTermPropagationSettings
from .dangling_authority_redistribution import DARBSettings
from .katz_marginal_info import KMIGSettings
from .articulation_point_boost import TAPBSettings
from .kcore_integration import KCIBSettings
from .bridge_edge_redundancy import BERPSettings
from .host_topic_entropy import HGTESettings
from .search_query_alignment import RSQVASettings
from .fr099_fr105_signals import FR099FR105Settings
from apps.suggestions.recommended_weights import (
    recommended_bool,
    recommended_float,
    recommended_int,
    recommended_str,
)

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    "w_semantic": recommended_float("w_semantic"),
    "w_keyword": recommended_float("w_keyword"),
    "w_node": recommended_float("w_node"),
    "w_quality": recommended_float("w_quality"),
}


# ---------------------------------------------------------------------------
# Settings orchestrator
# ---------------------------------------------------------------------------


def _load_all_pipeline_settings() -> dict[str, Any]:
    """Load every ranking setting into a single dict."""
    return {
        "weights": _load_weights(),
        "silo": _load_silo_settings(),
        "weighted_authority": _load_weighted_authority_settings(),
        "link_freshness": _load_link_freshness_settings(),
        "phrase_matching": _load_phrase_matching_settings(),
        "learned_anchor": _load_learned_anchor_settings(),
        "rare_term": _load_rare_term_propagation_settings(),
        "field_aware": _load_field_aware_relevance_settings(),
        "ga4_gsc": _load_ga4_gsc_settings(),
        "click_distance": _load_click_distance_settings(),
        "anchor_diversity": _load_anchor_diversity_settings(),
        "keyword_stuffing": _load_keyword_stuffing_settings(),
        "link_farm": _load_link_farm_settings(),
        "feedback_rerank": _load_feedback_rerank_settings(),
        "clustering": _load_clustering_settings(),
        "slate_diversity": _load_slate_diversity_settings(),
        "fr099_fr105": _load_fr099_fr105_settings(),
        "max_host_reuse": _get_max_host_reuse(),
    }


# ---------------------------------------------------------------------------
# Weights and settings loaders
# ---------------------------------------------------------------------------


def _load_weights() -> dict[str, float]:
    try:
        from apps.core.models import AppSetting

        qs = AppSetting.objects.filter(
            key__in=["w_semantic", "w_keyword", "w_node", "w_quality"]
        ).values_list("key", "value")
        overrides = {k: float(v) for k, v in qs}
        return {**DEFAULT_WEIGHTS, **overrides}
    except Exception:
        logger.exception("Failed to load pipeline weights; using defaults.")
        return dict(DEFAULT_WEIGHTS)


def _get_max_host_reuse() -> int:
    try:
        from apps.core.models import AppSetting

        setting = AppSetting.objects.filter(key="max_host_reuse").first()
        if setting:
            return int(setting.value)
    except Exception:
        logger.exception("Failed to load max host reuse; using default.")
    return 3


def _get_max_existing_links_per_host() -> int:
    """Maximum number of existing outgoing body links a host page may already
    have before the pipeline stops adding new suggestions to it.

    Configurable via AppSetting key ``spam_guards.max_existing_links_per_host``.
    Default: 2.
    """
    try:
        from apps.core.models import AppSetting

        setting = AppSetting.objects.filter(
            key="spam_guards.max_existing_links_per_host"
        ).first()
        if setting:
            return int(setting.value)
    except Exception:
        logger.exception(
            "Failed to load spam_guards.max_existing_links_per_host; using default."
        )
    return 2


def _get_max_anchor_words() -> int:
    """Maximum number of words allowed in suggested anchor text.

    Configurable via AppSetting key ``spam_guards.max_anchor_words``.
    Default: 4.
    """
    try:
        from apps.core.models import AppSetting

        setting = AppSetting.objects.filter(key="spam_guards.max_anchor_words").first()
        if setting:
            return int(setting.value)
    except Exception:
        logger.exception("Failed to load spam_guards.max_anchor_words; using default.")
    return 4


def _get_paragraph_window() -> int:
    """Sentence-position window used to detect paragraph-level link clustering.

    Configurable via AppSetting key ``spam_guards.paragraph_window``.
    Default: 3.
    """
    try:
        from apps.core.models import AppSetting

        setting = AppSetting.objects.filter(key="spam_guards.paragraph_window").first()
        if setting:
            return int(setting.value)
    except Exception:
        logger.exception("Failed to load spam_guards.paragraph_window; using default.")
    return 3


def _load_silo_settings() -> SiloSettings:
    try:
        from apps.core.views import get_silo_settings

        config = get_silo_settings()
        return SiloSettings(
            mode=str(config.get("mode", recommended_str("silo.mode"))),
            same_silo_boost=float(
                config.get("same_silo_boost", recommended_float("silo.same_silo_boost"))
            ),
            cross_silo_penalty=float(
                config.get(
                    "cross_silo_penalty", recommended_float("silo.cross_silo_penalty")
                )
            ),
        )
    except Exception:
        logger.exception("Failed to load silo settings; using defaults.")
        return SiloSettings()


def _load_weighted_authority_settings() -> dict[str, float]:
    try:
        from apps.core.views import get_weighted_authority_settings

        config = get_weighted_authority_settings()
        return {
            "ranking_weight": float(
                config.get(
                    "ranking_weight",
                    recommended_float("weighted_authority.ranking_weight"),
                )
            ),
        }
    except Exception:
        logger.exception("Failed to load weighted authority settings; using defaults.")
        return {
            "ranking_weight": recommended_float("weighted_authority.ranking_weight"),
        }


def _load_link_freshness_settings() -> dict[str, float]:
    try:
        from apps.core.views import get_link_freshness_settings

        config = get_link_freshness_settings()
        return {
            "ranking_weight": float(
                config.get(
                    "ranking_weight", recommended_float("link_freshness.ranking_weight")
                )
            ),
        }
    except Exception:
        logger.exception("Failed to load link freshness settings; using defaults.")
        return {
            "ranking_weight": recommended_float("link_freshness.ranking_weight"),
        }


def _load_phrase_matching_settings() -> PhraseMatchingSettings:
    try:
        from apps.core.views import get_phrase_matching_settings

        config = get_phrase_matching_settings()
        return PhraseMatchingSettings(
            ranking_weight=float(
                config.get(
                    "ranking_weight",
                    recommended_float("phrase_matching.ranking_weight"),
                )
            ),
            enable_anchor_expansion=bool(config.get("enable_anchor_expansion", True)),
            enable_partial_matching=bool(config.get("enable_partial_matching", True)),
            context_window_tokens=int(
                config.get(
                    "context_window_tokens",
                    recommended_float("phrase_matching.context_window_tokens"),
                )
            ),
        )
    except Exception:
        logger.exception("Failed to load phrase matching settings; using defaults.")
        return PhraseMatchingSettings()


def _load_learned_anchor_settings() -> LearnedAnchorSettings:
    try:
        from apps.core.views import get_learned_anchor_settings

        config = get_learned_anchor_settings()
        return LearnedAnchorSettings(
            ranking_weight=float(
                config.get(
                    "ranking_weight", recommended_float("learned_anchor.ranking_weight")
                )
            ),
            minimum_anchor_sources=int(
                config.get(
                    "minimum_anchor_sources",
                    recommended_float("learned_anchor.minimum_anchor_sources"),
                )
            ),
            minimum_family_support_share=float(
                config.get(
                    "minimum_family_support_share",
                    recommended_float("learned_anchor.minimum_family_support_share"),
                )
            ),
            enable_noise_filter=bool(config.get("enable_noise_filter", True)),
        )
    except Exception:
        logger.exception("Failed to load learned anchor settings; using defaults.")
        return LearnedAnchorSettings()


def _load_rare_term_propagation_settings() -> RareTermPropagationSettings:
    try:
        from apps.core.views import get_rare_term_propagation_settings

        config = get_rare_term_propagation_settings()
        return RareTermPropagationSettings(
            enabled=bool(config.get("enabled", True)),
            ranking_weight=float(
                config.get(
                    "ranking_weight",
                    recommended_float("rare_term_propagation.ranking_weight"),
                )
            ),
            max_document_frequency=int(
                config.get(
                    "max_document_frequency",
                    recommended_float("rare_term_propagation.max_document_frequency"),
                )
            ),
            minimum_supporting_related_pages=int(
                config.get(
                    "minimum_supporting_related_pages",
                    recommended_float(
                        "rare_term_propagation.minimum_supporting_related_pages"
                    ),
                )
            ),
        )
    except Exception:
        logger.exception(
            "Failed to load rare-term propagation settings; using defaults."
        )
        return RareTermPropagationSettings()


def _load_field_aware_relevance_settings() -> FieldAwareRelevanceSettings:
    try:
        from apps.core.views import get_field_aware_relevance_settings

        config = get_field_aware_relevance_settings()
        return FieldAwareRelevanceSettings(
            ranking_weight=float(
                config.get(
                    "ranking_weight",
                    recommended_float("field_aware_relevance.ranking_weight"),
                )
            ),
            title_field_weight=float(
                config.get(
                    "title_field_weight",
                    recommended_float("field_aware_relevance.title_field_weight"),
                )
            ),
            body_field_weight=float(
                config.get(
                    "body_field_weight",
                    recommended_float("field_aware_relevance.body_field_weight"),
                )
            ),
            scope_field_weight=float(
                config.get(
                    "scope_field_weight",
                    recommended_float("field_aware_relevance.scope_field_weight"),
                )
            ),
            learned_anchor_field_weight=float(
                config.get(
                    "learned_anchor_field_weight",
                    recommended_float(
                        "field_aware_relevance.learned_anchor_field_weight"
                    ),
                )
            ),
        )
    except Exception:
        logger.exception(
            "Failed to load field-aware relevance settings; using defaults."
        )
        return FieldAwareRelevanceSettings()


def _load_ga4_gsc_settings() -> dict[str, float]:
    try:
        from apps.core.views import get_ga4_gsc_settings

        config = get_ga4_gsc_settings()
        return {
            "ranking_weight": float(
                config.get(
                    "ranking_weight", recommended_float("ga4_gsc.ranking_weight")
                )
            ),
        }
    except Exception:
        logger.exception("Failed to load GA4/GSC settings; using defaults.")
        return {
            "ranking_weight": recommended_float("ga4_gsc.ranking_weight"),
        }


def _load_click_distance_settings() -> dict[str, float]:
    try:
        from apps.core.views import get_click_distance_settings

        config = get_click_distance_settings()
        return {
            "ranking_weight": float(
                config.get(
                    "ranking_weight", recommended_float("click_distance.ranking_weight")
                )
            ),
        }
    except Exception:
        logger.exception("Failed to load click-distance settings; using defaults.")
        return {
            "ranking_weight": recommended_float("click_distance.ranking_weight"),
        }


def _load_feedback_rerank_settings() -> FeedbackRerankSettings:
    """Load feedback-driven explore/exploit settings from the DB."""
    try:
        from apps.core.views import get_feedback_rerank_settings

        raw = get_feedback_rerank_settings()
        return FeedbackRerankSettings(
            enabled=raw["enabled"],
            ranking_weight=raw["ranking_weight"],
            exploration_rate=raw["exploration_rate"],
        )
    except Exception:
        logger.exception("Failed to load feedback rerank settings; using defaults.")
        return FeedbackRerankSettings()


def _load_anchor_diversity_settings() -> AnchorDiversitySettings:
    try:
        from apps.core.views_antispam import get_anchor_diversity_settings

        raw = get_anchor_diversity_settings()
        return AnchorDiversitySettings(
            enabled=bool(raw["enabled"]),
            ranking_weight=float(raw["ranking_weight"]),
            min_history_count=int(raw["min_history_count"]),
            max_exact_match_share=float(raw["max_exact_match_share"]),
            max_exact_match_count=int(raw["max_exact_match_count"]),
            hard_cap_enabled=bool(raw["hard_cap_enabled"]),
        )
    except Exception:
        logger.exception("Failed to load anchor diversity settings; using defaults.")
        return AnchorDiversitySettings()


def _load_keyword_stuffing_settings() -> KeywordStuffingSettings:
    try:
        from apps.core.views_antispam import get_keyword_stuffing_settings

        raw = get_keyword_stuffing_settings()
        return KeywordStuffingSettings(
            enabled=bool(raw["enabled"]),
            ranking_weight=float(raw["ranking_weight"]),
            alpha=float(raw["alpha"]),
            tau=float(raw["tau"]),
            dirichlet_mu=int(raw["dirichlet_mu"]),
            top_k_stuff_terms=int(raw["top_k_stuff_terms"]),
        )
    except Exception:
        logger.exception("Failed to load keyword stuffing settings; using defaults.")
        return KeywordStuffingSettings()


def _load_link_farm_settings() -> LinkFarmSettings:
    try:
        from apps.core.views_antispam import get_link_farm_settings

        raw = get_link_farm_settings()
        return LinkFarmSettings(
            enabled=bool(raw["enabled"]),
            ranking_weight=float(raw["ranking_weight"]),
            min_scc_size=int(raw["min_scc_size"]),
            density_threshold=float(raw["density_threshold"]),
            lambda_value=float(raw["lambda"]),
        )
    except Exception:
        logger.exception("Failed to load link-farm settings; using defaults.")
        return LinkFarmSettings()


def _load_clustering_settings() -> ClusteringSettings:
    """Load near-duplicate clustering settings from the DB."""
    try:
        from apps.core.views import get_clustering_settings

        raw = get_clustering_settings()
        return ClusteringSettings(
            enabled=raw["enabled"],
            similarity_threshold=raw["similarity_threshold"],
            suppression_penalty=raw["suppression_penalty"],
        )
    except Exception:
        logger.exception("Failed to load clustering settings; using defaults.")
        return ClusteringSettings()


def _load_slate_diversity_settings() -> SlateDiversitySettings:
    """Load FR-15 slate diversity settings from the DB."""
    try:
        from apps.core.views import get_slate_diversity_settings

        raw = get_slate_diversity_settings()
        return SlateDiversitySettings(
            enabled=raw["enabled"],
            diversity_lambda=raw["diversity_lambda"],
            score_window=raw["score_window"],
            similarity_cap=raw["similarity_cap"],
        )
    except Exception:
        logger.exception("Failed to load slate diversity settings; using defaults.")
        return SlateDiversitySettings()


def _load_fr099_fr105_settings() -> FR099FR105Settings:
    """Load FR-099 through FR-105 graph-topology ranking-signal settings.

    Reads the 19 keys seeded in recommended_weights.py (`darb.*`, `kmig.*`,
    `tapb.*`, `kcib.*`, `berp.*`, `hgte.*`, `rsqva.*`) from AppSetting
    overrides if present, else falls back to the Recommended preset defaults.

    See docs/specs/fr099-*.md through docs/specs/fr105-*.md for baseline
    citations. See docs/RANKING-GATES.md Gate A for the implementation gate.
    """
    def _get(key: str, fallback_str: str) -> str:
        """Read AppSetting override for key, else use the Recommended default."""
        try:
            from apps.core.models import AppSetting

            setting = AppSetting.objects.filter(key=key).first()
            if setting is not None:
                return setting.value
        except Exception:
            logger.exception("Failed to read AppSetting %s; using preset.", key)
        return fallback_str

    def _bool(key: str) -> bool:
        return _get(key, "true" if recommended_bool(key) else "false").strip().lower() == "true"

    def _float(key: str) -> float:
        return float(_get(key, str(recommended_float(key))))

    def _int(key: str) -> int:
        return int(float(_get(key, str(recommended_int(key)))))

    try:
        return FR099FR105Settings(
            darb=DARBSettings(
                enabled=_bool("darb.enabled"),
                ranking_weight=_float("darb.ranking_weight"),
                out_degree_saturation=_int("darb.out_degree_saturation"),
                min_host_value=_float("darb.min_host_value"),
            ),
            kmig=KMIGSettings(
                enabled=_bool("kmig.enabled"),
                ranking_weight=_float("kmig.ranking_weight"),
                attenuation=_float("kmig.attenuation"),
                max_hops=_int("kmig.max_hops"),
            ),
            tapb=TAPBSettings(
                enabled=_bool("tapb.enabled"),
                ranking_weight=_float("tapb.ranking_weight"),
                apply_to_articulation_node_only=_bool("tapb.apply_to_articulation_node_only"),
            ),
            kcib=KCIBSettings(
                enabled=_bool("kcib.enabled"),
                ranking_weight=_float("kcib.ranking_weight"),
                min_kcore_spread=_int("kcib.min_kcore_spread"),
            ),
            berp=BERPSettings(
                enabled=_bool("berp.enabled"),
                ranking_weight=_float("berp.ranking_weight"),
                min_component_size=_int("berp.min_component_size"),
            ),
            hgte=HGTESettings(
                enabled=_bool("hgte.enabled"),
                ranking_weight=_float("hgte.ranking_weight"),
                min_host_out_degree=_int("hgte.min_host_out_degree"),
            ),
            rsqva=RSQVASettings(
                enabled=_bool("rsqva.enabled"),
                ranking_weight=_float("rsqva.ranking_weight"),
                min_queries_per_page=_int("rsqva.min_queries_per_page"),
                min_query_clicks=_int("rsqva.min_query_clicks"),
                max_vocab_size=_int("rsqva.max_vocab_size"),
            ),
        )
    except Exception:
        logger.exception(
            "Failed to load FR-099 through FR-105 settings; using dataclass defaults."
        )
        return FR099FR105Settings()
