"""
Root API URL configuration for XF Internal Linker V2.

All REST API endpoints are routed through /api/.
DRF routers wire viewsets from each app into clean URL patterns.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.content.views import ContentItemViewSet, ScopeItemViewSet, SiloGroupViewSet
from apps.core.views import (
    AppearanceSettingsView,
    DashboardView,
    ClusteringSettingsView,
    ClusteringRecalculateView,
    FieldAwareRelevanceSettingsView,
    FieldAwareRelevanceSettingsView,
    ClickDistanceSettingsView,
    ClickDistanceRecalculateView,
    FeedbackRerankSettingsView,
    FaviconUploadView,
    GA4GSCSettingsView,
    LearnedAnchorSettingsView,
    LinkFreshnessRecalculateView,
    LinkFreshnessSettingsView,
    LogoUploadView,
    PhraseMatchingSettingsView,
    RareTermPropagationSettingsView,
    RTuneTriggerView,
    SiloSettingsView,
    SlateDiversitySettingsView,
    WeightedAuthorityRecalculateView,
    WeightedAuthoritySettingsView,
    WordPressSettingsView,
    WordPressSyncRunView,
)
from apps.graph.views import BrokenLinkViewSet
from apps.suggestions.views import (
    PipelineDiagnosticViewSet,
    PipelineRunViewSet,
    SuggestionViewSet,
    WeightAdjustmentHistoryViewSet,
    WeightPresetViewSet,
)
from apps.sync.views import ImportUploadView, SyncJobViewSet, XenForoWebhookView

router = DefaultRouter()

# Content (read-only)
router.register(r"scopes", ScopeItemViewSet, basename="scope")
router.register(r"silo-groups", SiloGroupViewSet, basename="silo-group")
router.register(r"content", ContentItemViewSet, basename="content")

# Suggestions + pipeline
router.register(r"suggestions", SuggestionViewSet, basename="suggestion")
router.register(r"pipeline-runs", PipelineRunViewSet, basename="pipeline-run")
router.register(r"diagnostics", PipelineDiagnosticViewSet, basename="diagnostic")
router.register(r"sync-jobs", SyncJobViewSet, basename="sync-job")
router.register(r"broken-links", BrokenLinkViewSet, basename="broken-link")
router.register(r"weight-presets", WeightPresetViewSet, basename="weight-preset")
router.register(r"weight-history", WeightAdjustmentHistoryViewSet, basename="weight-history")

urlpatterns = [
    path("", include("apps.core.urls")),
    path("", include(router.urls)),
    path("import/upload/", ImportUploadView.as_view(), name="import-upload"),
    path("sync/webhooks/xenforo/", XenForoWebhookView.as_view(), name="xenforo-webhook"),
    path("settings/appearance/", AppearanceSettingsView.as_view(), name="appearance-settings"),
    path("settings/silos/", SiloSettingsView.as_view(), name="silo-settings"),
    path("settings/weighted-authority/", WeightedAuthoritySettingsView.as_view(), name="weighted-authority-settings"),
    path("settings/weighted-authority/recalculate/", WeightedAuthorityRecalculateView.as_view(), name="weighted-authority-recalculate"),
    path("settings/link-freshness/", LinkFreshnessSettingsView.as_view(), name="link-freshness-settings"),
    path("settings/link-freshness/recalculate/", LinkFreshnessRecalculateView.as_view(), name="link-freshness-recalculate"),
    path("settings/phrase-matching/", PhraseMatchingSettingsView.as_view(), name="phrase-matching-settings"),
    path("settings/learned-anchor/", LearnedAnchorSettingsView.as_view(), name="learned-anchor-settings"),
    path("settings/rare-term-propagation/", RareTermPropagationSettingsView.as_view(), name="rare-term-propagation-settings"),
    path("settings/field-aware-relevance/", FieldAwareRelevanceSettingsView.as_view(), name="field-aware-relevance-settings"),
    path("settings/ga4-gsc/", GA4GSCSettingsView.as_view(), name="ga4-gsc-settings"),
    path("settings/explore-exploit/", FeedbackRerankSettingsView.as_view(), name="explore-exploit-settings"),
    path("settings/click-distance/", ClickDistanceSettingsView.as_view(), name="settings-click-distance"),
    path("settings/click-distance/recalculate/", ClickDistanceRecalculateView.as_view(), name="settings-click-distance-recalculate"),
    path("settings/clustering/", ClusteringSettingsView.as_view(), name="clustering-settings"),
    path("settings/clustering/recalculate/", ClusteringRecalculateView.as_view(), name="clustering-recalculate"),
    path("settings/slate-diversity/", SlateDiversitySettingsView.as_view(), name="slate-diversity-settings"),
    path("settings/r-tune/trigger/", RTuneTriggerView.as_view(), name="r-tune-trigger"),
    path("settings/wordpress/", WordPressSettingsView.as_view(), name="wordpress-settings"),
    path("settings/logo/", LogoUploadView.as_view(), name="settings-logo"),
    path("settings/favicon/", FaviconUploadView.as_view(), name="settings-favicon"),
    path("sync/wordpress/run/", WordPressSyncRunView.as_view(), name="wordpress-sync-run"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("system/status/", include("apps.diagnostics.urls")),
    path("auth/", include("rest_framework.urls", namespace="rest_framework")),
]
