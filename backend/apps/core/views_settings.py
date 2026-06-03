"""
Settings-view layer extracted from ``apps/core/views.py``.

Why this file exists
--------------------
``apps/core/views.py`` was the historical home of every view in the core
app and grew well past the 1500-line cap that ``CLAUDE.md`` (Code Quality
Mandate) targets. To bring the file back under control the per-feature
**settings** view classes — appearance, silos, weighted authority, link
freshness, phrase matching, learned anchor, rare term propagation,
field-aware relevance, GA4/GSC, WordPress, XenForo, webhooks, and the
site-asset upload base/leaf classes — moved here.

Behaviour preserved exactly
---------------------------
This is a pure mechanical refactor. No request shape, validation rule,
or response payload changed. The original ``apps.core.views`` module
re-exports every class and helper defined in this file at the end of
``views.py`` so existing importers (``apps/api/urls.py``,
``apps/core/urls.py``, ``apps/core/tests_dashboard_helpers.py``,
``apps/suggestions/views.py``, etc.) keep working unchanged via the
``from apps.core.views import …`` path they already use.

Read-side helpers (``get_silo_settings`` etc.), validators
(``_validate_*``), and shared coercion helpers (``_coerce_*_strict``,
``_get_app_setting_value``, ``_sync_wordpress_periodic_task``) stay in
``views.py`` because they are reused by other view families that did
not move out. This file imports the ones it needs from ``.views``.
"""

from __future__ import annotations

import json
import logging
import uuid

from django.conf import settings as django_settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.throttles import WeightRecalcThrottle as _WeightRecalcThrottle

# Appearance / asset constants live in views.py because they describe the
# /api/settings/appearance/ surface, not the shared settings flow.
from .views import (
    DEFAULT_APPEARANCE,
    _ASSET_MAX_BYTES,
    _FAVICON_ALLOWED,
    _LOGO_ALLOWED,
)
# Settings helpers + per-feature validators / accessors live in
# ``apps/core/services/settings_helpers.py`` — moved out of views.py on
# 2026-05-10 (slice 5) so that file could drop below the 1500-line cap.
from .services.settings_helpers import (
    _get_app_setting_value,
    _sync_wordpress_periodic_task,
    _validate_field_aware_relevance_settings,
    _validate_ga4_gsc_settings,
    _validate_learned_anchor_settings,
    _validate_link_freshness_settings,
    _validate_phrase_matching_settings,
    _validate_rare_term_propagation_settings,
    _validate_silo_settings,
    _validate_weighted_authority_settings,
    _validate_wordpress_settings,
    get_field_aware_relevance_settings,
    get_ga4_gsc_settings,
    get_learned_anchor_settings,
    get_link_freshness_settings,
    get_phrase_matching_settings,
    get_rare_term_propagation_settings,
    get_silo_settings,
    get_weighted_authority_settings,
    get_wordpress_settings,
)

logger = logging.getLogger(__name__)


class AppearanceSettingsView(APIView):
    """
    GET  /api/settings/appearance/ — returns current appearance config (or defaults)
    PUT  /api/settings/appearance/ — merge-updates the config, returns updated config
    """

    permission_classes = [IsAuthenticated]

    def _get_config(self) -> dict:
        from apps.core.models import AppSetting

        # AutoIssue #20375: route the stored blob through the guarded
        # get_json helper so a corrupt value degrades to {} (and then to the
        # defaults below) instead of raising an uncaught JSONDecodeError (500).
        stored = AppSetting.get_json("appearance.config", {})
        if not isinstance(stored, dict):
            stored = {}
        # Merge stored values over defaults.  Keys that are not in
        # DEFAULT_APPEARANCE are silently dropped — this cleans up legacy
        # keys such as "theme" that were removed from the schema.
        result = dict(DEFAULT_APPEARANCE)
        for k in DEFAULT_APPEARANCE:
            if k in stored:
                result[k] = stored[k]
        return result

    def get(self, request):
        return Response(self._get_config())

    def put(self, request):
        from apps.core.models import AppSetting

        current = self._get_config()
        # Shallow merge — client sends only the keys it wants to change
        for k, v in request.data.items():
            if k in DEFAULT_APPEARANCE:
                current[k] = v
        AppSetting.objects.update_or_create(
            key="appearance.config",
            defaults={
                "value": json.dumps(current),
                "value_type": "json",
                "category": "appearance",
                "description": "Theme customizer appearance configuration (managed by UI).",
                "is_secret": False,
            },
        )
        return Response(current)


class SiloSettingsView(APIView):
    """
    GET  /api/settings/silos/ - returns persisted silo-ranking configuration
    PUT  /api/settings/silos/ - validates and persists silo-ranking configuration
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_silo_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_silo_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "silo.mode": {
                "value": validated["mode"],
                "value_type": "str",
                "description": "Topical silo enforcement mode for the suggestion pipeline.",
            },
            "silo.same_silo_boost": {
                "value": str(validated["same_silo_boost"]),
                "value_type": "float",
                "description": "Score bonus applied to same-silo candidates in prefer_same_silo mode.",
            },
            "silo.cross_silo_penalty": {
                "value": str(validated["cross_silo_penalty"]),
                "value_type": "float",
                "description": "Score penalty applied to cross-silo candidates in prefer_same_silo mode.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class WeightedAuthoritySettingsView(APIView):
    """
    GET  /api/settings/weighted-authority/ - returns March 2026 PageRank settings
    PUT  /api/settings/weighted-authority/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_weighted_authority_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_weighted_authority_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "weighted_authority.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "description": "Ranking weight applied to the normalized March 2026 PageRank signal.",
            },
            "weighted_authority.position_bias": {
                "value": str(validated["position_bias"]),
                "description": "How much later links are down-weighted within a source page.",
            },
            "weighted_authority.empty_anchor_factor": {
                "value": str(validated["empty_anchor_factor"]),
                "description": "Multiplier applied when a non-bare link has blank anchor text.",
            },
            "weighted_authority.bare_url_factor": {
                "value": str(validated["bare_url_factor"]),
                "description": "Multiplier applied to naked URL links.",
            },
            "weighted_authority.weak_context_factor": {
                "value": str(validated["weak_context_factor"]),
                "description": "Multiplier applied to links with prose on only one side.",
            },
            "weighted_authority.isolated_context_factor": {
                "value": str(validated["isolated_context_factor"]),
                "description": "Multiplier applied to isolated or list-like links.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": "float",
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class WeightedAuthorityRecalculateView(APIView):
    """POST /api/settings/weighted-authority/recalculate/ - recalculate March 2026 PageRank."""

    throttle_classes = [_WeightRecalcThrottle]

    def post(self, request):
        from apps.pipeline.tasks import recalculate_weighted_authority

        job_id = str(uuid.uuid4())
        recalculate_weighted_authority.delay(job_id=job_id)
        return Response({"job_id": job_id}, status=202)


def _build_link_freshness_rows(validated: dict) -> dict[str, dict[str, str]]:
    """Pure function — turn a validated Link Freshness dict into AppSetting rows.

    Each entry maps an AppSetting key to ``{value, value_type, description}``
    — the caller wraps with the shared category + is_secret. Mirrors the
    value-model / WordPress / GA4-GSC row-builder pattern (DRY).
    """
    return {
        "link_freshness.ranking_weight": {
            "value": str(validated["ranking_weight"]),
            "value_type": "float",
            "description": "Ranking weight applied to the centered Link Freshness component.",
        },
        "link_freshness.recent_window_days": {
            "value": str(validated["recent_window_days"]),
            "value_type": "int",
            "description": "Day window used to compare recent link growth vs. the prior window.",
        },
        "link_freshness.newest_peer_percent": {
            "value": str(validated["newest_peer_percent"]),
            "value_type": "float",
            "description": "Share of newest inbound peers used for cohort freshness.",
        },
        "link_freshness.min_peer_count": {
            "value": str(validated["min_peer_count"]),
            "value_type": "int",
            "description": "Minimum inbound peer history rows required before Link Freshness stops being neutral.",
        },
        "link_freshness.w_recent": {
            "value": str(validated["w_recent"]),
            "value_type": "float",
            "description": "Weight for the recent-new-links share component.",
        },
        "link_freshness.w_growth": {
            "value": str(validated["w_growth"]),
            "value_type": "float",
            "description": "Weight for the recent-vs-previous growth delta component.",
        },
        "link_freshness.w_cohort": {
            "value": str(validated["w_cohort"]),
            "value_type": "float",
            "description": "Weight for the newest-cohort freshness component.",
        },
        "link_freshness.w_loss": {
            "value": str(validated["w_loss"]),
            "value_type": "float",
            "description": "Weight for recent inbound-link disappearance pressure.",
        },
    }


class LinkFreshnessSettingsView(APIView):
    """
    GET  /api/settings/link-freshness/ - returns Link Freshness settings
    PUT  /api/settings/link-freshness/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_link_freshness_settings())

    def put(self, request):
        """Persist a validated Link Freshness settings payload.

        Refactored 2026-05-04: was 63 lines. Same per-feature row-builder
        pattern used by value-model + WordPress + GA4-GSC settings.
        """
        from apps.core.models import AppSetting

        try:
            validated = _validate_link_freshness_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        for key, row in _build_link_freshness_rows(validated).items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "link_freshness",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class LinkFreshnessRecalculateView(APIView):
    """POST /api/settings/link-freshness/recalculate/ - recalculate Link Freshness."""

    throttle_classes = [_WeightRecalcThrottle]

    def post(self, request):
        from apps.pipeline.tasks import recalculate_link_freshness

        job_id = str(uuid.uuid4())
        recalculate_link_freshness.delay(job_id=job_id)
        return Response({"job_id": job_id}, status=202)


class PhraseMatchingSettingsView(APIView):
    """
    GET  /api/settings/phrase-matching/ - returns FR-008 phrase-matching settings
    PUT  /api/settings/phrase-matching/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_phrase_matching_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_phrase_matching_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "phrase_matching.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "value_type": "float",
                "description": "Ranking weight applied to the centered FR-008 phrase relevance component.",
            },
            "phrase_matching.enable_anchor_expansion": {
                "value": "true" if validated["enable_anchor_expansion"] else "false",
                "value_type": "bool",
                "description": "Whether anchor extraction can expand beyond the current exact title fallback.",
            },
            "phrase_matching.enable_partial_matching": {
                "value": "true" if validated["enable_partial_matching"] else "false",
                "value_type": "bool",
                "description": "Whether bounded partial phrase matches are allowed when local context supports them.",
            },
            "phrase_matching.context_window_tokens": {
                "value": str(validated["context_window_tokens"]),
                "value_type": "int",
                "description": "Same-sentence token window used for FR-008 local corroboration.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "anchor",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class LearnedAnchorSettingsView(APIView):
    """
    GET  /api/settings/learned-anchor/ - returns FR-009 learned-anchor settings
    PUT  /api/settings/learned-anchor/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_learned_anchor_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_learned_anchor_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "learned_anchor.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "value_type": "float",
                "description": "Ranking weight applied to the positive-only FR-009 learned-anchor corroboration component.",
            },
            "learned_anchor.minimum_anchor_sources": {
                "value": str(validated["minimum_anchor_sources"]),
                "value_type": "int",
                "description": "Minimum usable inbound anchor sources required before learned anchors stop being neutral.",
            },
            "learned_anchor.minimum_family_support_share": {
                "value": str(validated["minimum_family_support_share"]),
                "value_type": "float",
                "description": "Minimum support share a learned anchor family needs before it can corroborate the chosen anchor.",
            },
            "learned_anchor.enable_noise_filter": {
                "value": "true" if validated["enable_noise_filter"] else "false",
                "value_type": "bool",
                "description": "Whether generic live anchor text like click here is filtered out before learned-anchor grouping.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "anchor",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class RareTermPropagationSettingsView(APIView):
    """
    GET  /api/settings/rare-term-propagation/ - returns FR-010 rare-term settings
    PUT  /api/settings/rare-term-propagation/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_rare_term_propagation_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_rare_term_propagation_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "rare_term_propagation.enabled": {
                "value": "true" if validated["enabled"] else "false",
                "value_type": "bool",
                "description": "Whether FR-010 rare-term propagation profiles are built during suggestion scoring.",
            },
            "rare_term_propagation.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "value_type": "float",
                "description": "Ranking weight applied to the positive-only FR-010 rare-term propagation component.",
            },
            "rare_term_propagation.max_document_frequency": {
                "value": str(validated["max_document_frequency"]),
                "value_type": "int",
                "description": "Highest site-wide document frequency a token can have and still count as a propagated rare term.",
            },
            "rare_term_propagation.minimum_supporting_related_pages": {
                "value": str(validated["minimum_supporting_related_pages"]),
                "value_type": "int",
                "description": "Minimum number of eligible related pages that must support a propagated rare term before it stops being neutral.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class FieldAwareRelevanceSettingsView(APIView):
    """
    GET  /api/settings/field-aware-relevance/ - returns FR-011 field-aware settings
    PUT  /api/settings/field-aware-relevance/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_field_aware_relevance_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_field_aware_relevance_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "field_aware_relevance.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "value_type": "float",
                "description": "Ranking weight applied to the centered FR-011 field-aware relevance component.",
            },
            "field_aware_relevance.title_field_weight": {
                "value": str(validated["title_field_weight"]),
                "value_type": "float",
                "description": "Share of FR-011 field-aware relevance assigned to destination title matches.",
            },
            "field_aware_relevance.heading_field_weight": {
                "value": str(validated["heading_field_weight"]),
                "value_type": "float",
                "description": "Share of FR-011 field-aware relevance assigned to destination heading matches.",
            },
            "field_aware_relevance.intro_field_weight": {
                "value": str(validated["intro_field_weight"]),
                "value_type": "float",
                "description": "Share of FR-011 field-aware relevance assigned to early main-content matches.",
            },
            "field_aware_relevance.body_field_weight": {
                "value": str(validated["body_field_weight"]),
                "value_type": "float",
                "description": "Share of FR-011 field-aware relevance assigned to destination body-text matches.",
            },
            "field_aware_relevance.scope_field_weight": {
                "value": str(validated["scope_field_weight"]),
                "value_type": "float",
                "description": "Share of FR-011 field-aware relevance assigned to scope-label matches.",
            },
            "field_aware_relevance.learned_anchor_field_weight": {
                "value": str(validated["learned_anchor_field_weight"]),
                "value_type": "float",
                "description": "Share of FR-011 field-aware relevance assigned to learned-anchor vocabulary matches.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


# GA4/GSC row spec: (validated_key, setting_key, value_type, category, description, transform, is_secret)
# Pulling the row-shape config out of the helper keeps the helper pure-function
# and under the 50-line cap. New rows only require a tuple addition here.
_GA4_GSC_ROW_SPEC: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "ranking_weight",
        "ga4_gsc.ranking_weight",
        "float",
        "ml",
        "Ranking weight for the GA4/GSC content-value signal.",
    ),
    (
        "property_url",
        "ga4_gsc.property_url",
        "str",
        "analytics",
        "Google Search Console property URL for read access.",
    ),
    (
        "service_account_email",
        "ga4_gsc.service_account_email",
        "str",
        "analytics",
        "Service-account email used for Search Console read access.",
    ),
    (
        "sync_enabled",
        "ga4_gsc.sync_enabled",
        "bool",
        "analytics",
        "Whether Search Console sync is enabled when the importer is added.",
    ),
    (
        "sync_lookback_days",
        "ga4_gsc.sync_lookback_days",
        "int",
        "analytics",
        "How many days the future Search Console sync should reread.",
    ),
)


def _format_setting_value(raw: object, value_type: str) -> str:
    """Coerce a Python value into the on-disk AppSetting string form."""
    if value_type == "bool":
        return "true" if raw else "false"
    return str(raw)


def _build_ga4_gsc_rows(validated: dict) -> dict[str, dict]:
    """Pure function — turn a validated GA4/GSC dict into AppSetting row dicts.

    Mirrors the WordPress + value-model pattern. Optional secret row
    only included when the operator explicitly supplied a new value.
    """
    rows: dict[str, dict] = {
        setting_key: {
            "value": _format_setting_value(validated[validated_key], value_type),
            "value_type": value_type,
            "description": description,
            "category": category,
            "is_secret": False,
        }
        for validated_key, setting_key, value_type, category, description in _GA4_GSC_ROW_SPEC
    }
    if validated["private_key_provided"]:
        rows["ga4_gsc.private_key"] = {
            "value": str(validated["private_key"] or ""),
            "value_type": "str",
            "description": "Service-account private key for Search Console read access.",
            "category": "analytics",
            "is_secret": True,
        }
    return rows


class GA4GSCSettingsView(APIView):
    """
    GET  /api/settings/ga4-gsc/ - returns GA4/GSC settings including GSC credentials
    PUT  /api/settings/ga4-gsc/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_ga4_gsc_settings())

    def put(self, request):
        """Persist a validated GA4/GSC settings payload.

        Refactored 2026-05-04: was 66 lines mostly composed of the
        same row-builder pattern from value-model + WordPress puts.
        Pulled into ``_build_ga4_gsc_rows`` so the row shapes are
        independently testable. Optional ``private_key`` row stays
        only-when-provided so partial re-PUT doesn't clobber the
        stored secret.
        """
        from apps.core.models import AppSetting

        try:
            validated = _validate_ga4_gsc_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        for key, row in _build_ga4_gsc_rows(validated).items():
            AppSetting.objects.update_or_create(key=key, defaults=row)

        return Response(get_ga4_gsc_settings())


def _gsc_private_key() -> str:
    return (_get_app_setting_value("ga4_gsc.private_key", "") or "").strip()


def _build_gsc_service(*, service_account_email: str, private_key: str):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_info(
        {
            "type": "service_account",
            "client_email": service_account_email,
            "private_key": private_key.replace("\\n", "\n"),
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
    )
    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)


class GSCConnectionTestView(APIView):
    """POST /api/settings/ga4-gsc/test-connection/ - validate Search Console credentials."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        creds = _gsc_resolve_credentials(request.data)
        if (
            not creds["property_url"]
            or not creds["service_account_email"]
            or not creds["private_key"]
        ):
            return Response(
                {
                    "status": "not_configured",
                    "message": "Save the property URL, service-account email, and private key first.",
                },
                status=400,
            )
        return _gsc_probe_credentials(creds)


def _gsc_resolve_credentials(data: dict) -> dict[str, str]:
    """Resolve GA4/GSC credentials. Precedence: body > AppSetting > Django settings."""
    current = get_ga4_gsc_settings()
    return {
        "property_url": (
            str(data.get("property_url") or current["property_url"] or "")
            .strip()
            .rstrip("/")
        ),
        "service_account_email": str(
            data.get("service_account_email") or current["service_account_email"] or ""
        ).strip(),
        "private_key": str(data.get("private_key") or _gsc_private_key()).strip(),
    }


def _gsc_probe_credentials(creds: dict[str, str]) -> Response:
    """Probe GSC sites().list(); surfaces auth + property-visibility status."""
    try:
        service = _build_gsc_service(
            service_account_email=creds["service_account_email"],
            private_key=creds["private_key"],
        )
        response = service.sites().list().execute()
    except Exception as exc:  # noqa: BLE001 — surfaces in response body; logger keeps a paper trail.
        logger.warning(
            "GSC connection test failed for %s: %s",
            creds["service_account_email"][:60],
            exc,
            exc_info=True,
        )
        return Response(
            {"status": "error", "message": f"Search Console connection failed: {exc}"},
            status=400,
        )
    site_entries = response.get("siteEntry", []) if isinstance(response, dict) else []
    property_match = any(
        str(entry.get("siteUrl") or "").rstrip("/") == creds["property_url"]
        for entry in site_entries
    )
    return Response(
        {
            "status": "connected" if property_match else "saved",
            "message": (
                "Search Console credentials worked and the property is visible."
                if property_match
                else "Search Console credentials worked, but this property URL was not listed for the service account."
            ),
        }
    )


def _build_wordpress_rows(validated: dict) -> dict[str, dict]:
    """Pure function — turn a validated WordPress dict into AppSetting row dicts.

    Each value is the ``defaults={}`` payload for ``update_or_create``.
    Split into a base-rows dict + an optional secret-row appendix so
    the function stays under the lint budget and the secret-handling
    rule lives in its own block.
    """
    rows = _wordpress_base_rows(validated)
    if validated["app_password_provided"]:
        rows["wordpress.app_password"] = _wordpress_app_password_row(validated)
    return rows


def _wordpress_base_rows(validated: dict) -> dict[str, dict]:
    """Always-persisted WordPress AppSetting rows (no secrets)."""
    return {
        "wordpress.base_url": {
            "value": str(validated["base_url"]),
            "value_type": "str",
            "description": "Base URL for the read-only WordPress REST API.",
            "category": "sync",
            "is_secret": False,
        },
        "wordpress.username": {
            "value": str(validated["username"]),
            "value_type": "str",
            "description": "WordPress username used for Application Password authentication.",
            "category": "api",
            "is_secret": False,
        },
        "wordpress.sync_enabled": {
            "value": "true" if validated["sync_enabled"] else "false",
            "value_type": "bool",
            "description": "Whether scheduled WordPress sync is enabled for the active scheduler lane.",
            "category": "sync",
            "is_secret": False,
        },
        "wordpress.sync_hour": {
            "value": str(validated["sync_hour"]),
            "value_type": "int",
            "description": "UTC hour for the scheduled WordPress sync.",
            "category": "sync",
            "is_secret": False,
        },
        "wordpress.sync_minute": {
            "value": str(validated["sync_minute"]),
            "value_type": "int",
            "description": "UTC minute for the scheduled WordPress sync.",
            "category": "sync",
            "is_secret": False,
        },
    }


def _wordpress_app_password_row(validated: dict) -> dict:
    """The is_secret=True app-password row — only included when provided."""
    return {
        "value": str(validated["app_password"] or ""),
        "value_type": "str",
        "description": "WordPress Application Password for private-content reads.",
        "category": "api",
        "is_secret": True,
    }


class WordPressSettingsView(APIView):
    """
    GET  /api/settings/wordpress/ - returns saved WordPress sync settings
    PUT  /api/settings/wordpress/ - validates and persists WordPress sync settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_wordpress_settings())

    def put(self, request):
        """Persist a validated WordPress settings payload.

        Refactored 2026-05-04: was 68 lines mostly composed of a giant
        ``rows`` dict literal. Same per-feature-area pattern used by
        the value-model + ga4-gsc settings: extracted into pure helper
        ``_build_wordpress_rows`` so the row-shape is independently
        testable + the handler stays under the lint budget.
        """
        from apps.core.models import AppSetting

        try:
            validated = _validate_wordpress_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        for key, row in _build_wordpress_rows(validated).items():
            AppSetting.objects.update_or_create(key=key, defaults=row)

        _sync_wordpress_periodic_task(validated)
        return Response(get_wordpress_settings())


class WordPressSyncRunView(APIView):
    """POST /api/sync/wordpress/run/ - enqueue a manual WordPress sync job."""

    def post(self, request):
        from django.utils import timezone

        from apps.pipeline.tasks import dispatch_import_content
        from apps.sync.models import SyncJob

        config = get_wordpress_settings()
        if not config["base_url"]:
            return Response(
                {"detail": "Configure a WordPress base URL before starting a sync."},
                status=400,
            )

        job = SyncJob.objects.create(
            source="wp",
            mode="full",
            status="pending",
            message="Queued WordPress sync.",
            started_at=timezone.now(),
        )

        dispatch_import_content(
            mode="full",
            source="wp",
            job_id=str(job.job_id),
            force_reembed=bool(request.data.get("force_reembed") or False),
        )

        return Response(
            {
                "job_id": str(job.job_id),
                "source": "wp",
                "mode": "full",
            },
            status=202,
        )


class XenForoSettingsView(APIView):
    """
    GET  /api/settings/xenforo/ - returns saved XenForo connection settings
    PUT  /api/settings/xenforo/ - validates and persists XenForo credentials
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.health.services import get_service_health_status

        base_url = (
            _get_app_setting_value(
                "xenforo.base_url", getattr(django_settings, "XENFORO_BASE_URL", "")
            )
            or ""
        ).strip()
        api_key = (
            _get_app_setting_value(
                "xenforo.api_key", getattr(django_settings, "XENFORO_API_KEY", "")
            )
            or ""
        ).strip()

        # Get actual connectivity health
        health = get_service_health_status("xenforo")

        return Response(
            {
                "base_url": base_url,
                "api_key_configured": bool(api_key),
                "health": health,
            }
        )

    def put(self, request):
        from apps.core.models import AppSetting

        base_url = (request.data.get("base_url") or "").strip().rstrip("/")
        api_key = (request.data.get("api_key") or "").strip()

        if not base_url:
            return Response({"detail": "base_url is required."}, status=400)

        AppSetting.objects.update_or_create(
            key="xenforo.base_url",
            defaults={
                "value": base_url,
                "value_type": "str",
                "category": "api",
                "is_secret": False,
            },
        )
        if api_key:
            AppSetting.objects.update_or_create(
                key="xenforo.api_key",
                defaults={
                    "value": api_key,
                    "value_type": "str",
                    "category": "api",
                    "is_secret": True,
                },
            )

        return Response({"status": "saved"})


def _xf_resolve_credentials(data: dict) -> tuple[str, str]:
    """Resolve XenForo credentials. Precedence: body > AppSetting > Django settings."""
    base_url = (
        (
            data.get("base_url")
            or _get_app_setting_value(
                "xenforo.base_url",
                getattr(django_settings, "XENFORO_BASE_URL", ""),
            )
            or ""
        )
        .strip()
        .rstrip("/")
    )
    api_key = (
        data.get("api_key")
        or _get_app_setting_value(
            "xenforo.api_key",
            getattr(django_settings, "XENFORO_API_KEY", ""),
        )
        or ""
    ).strip()
    return base_url, api_key


def _xf_probe_credentials(base_url: str, api_key: str) -> Response:
    """Probe XenForo /api/me; return a Response that the view returns directly."""
    import requests as http_requests

    try:
        resp = http_requests.get(
            f"{base_url}/api/me",
            headers={"XF-Api-Key": api_key},
            timeout=10,
        )
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001 — surfaces in response body; logger keeps a paper trail.
        logger.warning("XenForo connection test failed: %s", exc, exc_info=True)
        return Response(
            {"status": "error", "message": f"Could not reach XenForo: {exc}"},
            status=502,
        )
    if resp.status_code != 200:
        errors = payload.get("errors", [])
        detail = (
            errors[0].get("message", "Authentication failed.")
            if errors
            else f"HTTP {resp.status_code}"
        )
        return Response({"status": "error", "message": detail}, status=400)
    username = payload.get("me", {}).get("username", "unknown")
    return Response(
        {"status": "connected", "message": f"Connected to XenForo as '{username}'."},
    )


class XenForoTestConnectionView(APIView):
    """POST /api/settings/xenforo/test-connection/ — verify XenForo API credentials."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        base_url, api_key = _xf_resolve_credentials(request.data)
        if not base_url or not api_key:
            return Response(
                {
                    "status": "not_configured",
                    "message": "Both Forum URL and API Key are required.",
                },
                status=400,
            )
        return _xf_probe_credentials(base_url, api_key)


def _wp_resolve_credentials(data: dict) -> dict[str, str]:
    """Pick credentials from request body → AppSetting → Django settings.

    Precedence: explicit body value > stored AppSetting > Django settings
    fallback. Stripped + URL-trailing-slash-removed for the base URL.
    """
    base_url = (
        (
            data.get("base_url")
            or _get_app_setting_value(
                "wordpress.base_url",
                getattr(django_settings, "WORDPRESS_BASE_URL", ""),
            )
            or ""
        )
        .strip()
        .rstrip("/")
    )
    username = (
        data.get("username")
        or _get_app_setting_value(
            "wordpress.username",
            getattr(django_settings, "WORDPRESS_USERNAME", ""),
        )
        or ""
    ).strip()
    app_password = (
        data.get("app_password")
        or _get_app_setting_value(
            "wordpress.app_password",
            getattr(django_settings, "WORDPRESS_APP_PASSWORD", ""),
        )
        or ""
    ).strip()
    return {
        "base_url": base_url,
        "username": username,
        "app_password": app_password,
    }


def _wp_probe_credentials(creds: dict[str, str]) -> Response:
    """Run the actual ``/wp-json/wp/v2/users/me`` probe + format the response.

    Defensive try wraps the network call so the connection-test
    endpoint surfaces the error in the response body (operator sees
    the failure clearly) rather than crashing with HTTP 500.
    """
    import requests as http_requests

    try:
        resp = http_requests.get(
            f"{creds['base_url']}/wp-json/wp/v2/users/me",
            auth=(creds["username"], creds["app_password"]),
            timeout=10,
        )
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001 — connection-test endpoint surfaces the error in the response body; logger keeps a paper trail.
        logger.warning("WordPress connection test failed: %s", exc, exc_info=True)
        return Response(
            {"status": "error", "message": f"Could not reach WordPress: {exc}"},
            status=502,
        )
    if resp.status_code != 200:
        detail = payload.get("message", f"HTTP {resp.status_code}")
        return Response({"status": "error", "message": detail}, status=400)
    display_name = payload.get("name", "unknown")
    return Response(
        {
            "status": "connected",
            "message": f"Connected to WordPress as '{display_name}'.",
        }
    )


class WordPressTestConnectionView(APIView):
    """POST /api/settings/wordpress/test-connection/ — verify WordPress REST API credentials."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Test WordPress REST API credentials.

        Refactored 2026-05-04: was 67 lines. Credential resolution +
        the actual probe are now per-domain helpers so the handler
        stays small and the credential-fallback chain is testable
        in isolation.
        """
        creds = _wp_resolve_credentials(request.data)
        if not creds["base_url"] or not creds["username"] or not creds["app_password"]:
            return Response(
                {
                    "status": "not_configured",
                    "message": "Site URL, username, and app password are all required.",
                },
                status=400,
            )
        return _wp_probe_credentials(creds)


def _probe_webhook_endpoint(
    view_class, url: str, slug: str, secret_env_name: str
) -> dict:
    """Probe a single webhook receiver via Django's RequestFactory.

    Returns a result dict with status / http_status / message. The factory
    bypass means we don't need a live HTTP server to self-test.
    """
    from django.test import RequestFactory

    factory = RequestFactory()
    try:
        req = factory.post(
            url,
            data={"event": "connection_test"},
            content_type="application/json",
        )
        resp = view_class.as_view()(req)
    except Exception as exc:  # noqa: BLE001 — webhook self-test surfaces the error in the response body; logger keeps a paper trail.
        logger.warning(
            "%s webhook self-test failed: %s", slug.upper(), exc, exc_info=True
        )
        return {"status": "error", "message": str(exc)}

    code = resp.status_code
    if code == 200:
        message = "Endpoint reachable."
    elif code == 403:
        message = (
            f"Endpoint reachable but webhook secret mismatch — check {secret_env_name}."
        )
    else:
        message = f"Unexpected response: HTTP {code}"
    return {
        "status": "ok" if code in (200, 403) else "error",
        "http_status": code,
        "message": message,
    }


class WebhookTestView(APIView):
    """POST /api/settings/webhooks/test/ — verify internal webhook receiver endpoints are alive."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.sync.views import WordPressWebhookView, XenForoWebhookView

        results = {
            "xenforo": _probe_webhook_endpoint(
                XenForoWebhookView,
                "/api/sync/webhooks/xenforo/",
                "xf",
                "XENFORO_WEBHOOK_SECRET",
            ),
            "wordpress": _probe_webhook_endpoint(
                WordPressWebhookView,
                "/api/sync/webhooks/wordpress/",
                "wp",
                "WORDPRESS_WEBHOOK_SECRET",
            ),
        }
        all_ok = all(r.get("status") == "ok" for r in results.values())
        return Response(
            {
                "status": "connected" if all_ok else "partial",
                "message": (
                    "All webhook endpoints are reachable."
                    if all_ok
                    else "Some webhook endpoints have issues."
                ),
                "details": results,
            },
        )


class WebhookSettingsView(APIView):
    """
    GET  /api/settings/webhooks/ — returns whether each webhook secret is configured
    PUT  /api/settings/webhooks/ — saves webhook secrets to AppSetting
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        xf = (
            _get_app_setting_value(
                "webhook.xenforo_secret",
                getattr(django_settings, "XENFORO_WEBHOOK_SECRET", ""),
            )
            or ""
        ).strip()
        wp = (
            _get_app_setting_value(
                "webhook.wordpress_secret",
                getattr(django_settings, "WORDPRESS_WEBHOOK_SECRET", ""),
            )
            or ""
        ).strip()
        return Response(
            {
                "xf_secret_configured": bool(xf),
                "wp_secret_configured": bool(wp),
            }
        )

    def put(self, request):
        from apps.core.models import AppSetting

        xf_secret = (request.data.get("xf_webhook_secret") or "").strip()
        wp_secret = (request.data.get("wp_webhook_secret") or "").strip()

        if xf_secret:
            AppSetting.objects.update_or_create(
                key="webhook.xenforo_secret",
                defaults={
                    "value": xf_secret,
                    "value_type": "str",
                    "category": "api",
                    "description": "XenForo webhook secret",
                    "is_secret": True,
                },
            )
        if wp_secret:
            AppSetting.objects.update_or_create(
                key="webhook.wordpress_secret",
                defaults={
                    "value": wp_secret,
                    "value_type": "str",
                    "category": "api",
                    "description": "WordPress webhook secret",
                    "is_secret": True,
                },
            )

        xf = (
            _get_app_setting_value(
                "webhook.xenforo_secret",
                getattr(django_settings, "XENFORO_WEBHOOK_SECRET", ""),
            )
            or ""
        ).strip()
        wp = (
            _get_app_setting_value(
                "webhook.wordpress_secret",
                getattr(django_settings, "WORDPRESS_WEBHOOK_SECRET", ""),
            )
            or ""
        ).strip()
        return Response(
            {
                "xf_secret_configured": bool(xf),
                "wp_secret_configured": bool(wp),
            }
        )


def _save_appearance_key(key: str, value) -> None:
    """Persist a single key into the appearance config AppSetting blob."""
    from apps.core.models import AppSetting

    # AutoIssue #20375: read the existing blob through the guarded get_json
    # helper so a corrupt stored value falls back to {} instead of raising an
    # uncaught JSONDecodeError when persisting a single appearance key.
    stored = AppSetting.get_json("appearance.config", {})
    if not isinstance(stored, dict):
        stored = {}
    stored[key] = value
    AppSetting.objects.update_or_create(
        key="appearance.config",
        defaults={
            "value": json.dumps(stored),
            "value_type": "json",
            "category": "appearance",
            "description": "Theme customizer appearance configuration (managed by UI).",
            "is_secret": False,
        },
    )


class _SiteAssetUploadView(APIView):
    """
    Base class for logo and favicon upload views.

    Subclasses set:
        asset_key      — the key in DEFAULT_APPEARANCE (e.g. 'logoUrl')
        allowed_types  — frozenset of permitted MIME types
        url_field      — the key returned in the JSON response (e.g. 'logo_url')
        subfolder      — directory inside MEDIA_ROOT/site-assets/ (e.g. 'logos')
    """

    asset_key: str = ""
    allowed_types: frozenset = frozenset()
    url_field: str = ""
    subfolder: str = ""

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"error": "No file uploaded. Use field name 'file'."}, status=400
            )

        # Size check
        if upload.size > _ASSET_MAX_BYTES:
            return Response({"error": "File exceeds 2 MB limit."}, status=400)

        # MIME-type check (uses the browser-reported content type)
        if upload.content_type not in self.allowed_types:
            return Response(
                {
                    "error": (
                        f"Unsupported file type '{upload.content_type}'. "
                        f"Allowed: {', '.join(sorted(self.allowed_types))}"
                    )
                },
                status=400,
            )

        # Derive safe extension from MIME type
        ext_map = {
            "image/png": ".png",
            "image/svg+xml": ".svg",
            "image/webp": ".webp",
            "image/jpeg": ".jpg",
            "image/x-icon": ".ico",
            "image/vnd.microsoft.icon": ".ico",
        }
        ext = ext_map.get(upload.content_type, ".bin")

        # Build destination path using UUID filename — never use the original name
        dest_dir = django_settings.MEDIA_ROOT / "site-assets" / self.subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4()}{ext}"
        dest_path = dest_dir / filename

        with open(dest_path, "wb") as f:
            for chunk in upload.chunks():
                f.write(chunk)

        asset_url = (
            f"{django_settings.MEDIA_URL}site-assets/{self.subfolder}/{filename}"
        )
        _save_appearance_key(self.asset_key, asset_url)

        return Response({self.url_field: asset_url}, status=201)

    def delete(self, request):
        _save_appearance_key(self.asset_key, "")
        return Response(status=204)


class LogoUploadView(_SiteAssetUploadView):
    """POST /api/settings/logo/ — upload site logo (PNG, SVG, WEBP, JPEG ≤ 2 MB)."""

    asset_key = "logoUrl"
    allowed_types = _LOGO_ALLOWED
    url_field = "logo_url"
    subfolder = "logos"


class FaviconUploadView(_SiteAssetUploadView):
    """POST /api/settings/favicon/ — upload site favicon (PNG, SVG, ICO ≤ 2 MB)."""

    asset_key = "faviconUrl"
    allowed_types = _FAVICON_ALLOWED
    url_field = "favicon_url"
    subfolder = "favicons"
