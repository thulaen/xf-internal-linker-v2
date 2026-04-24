"""
Root API URL configuration for XF Internal Linker V2.

All REST API endpoints are routed through /api/.
DRF routers wire viewsets from each app into clean URL patterns.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.diagnostics.views import GlitchtipEventsView
from apps.health.views import HealthStatusViewSet, HealthDiskView, HealthGpuView
from apps.content.views import ContentItemViewSet, ScopeItemViewSet, SiloGroupViewSet
from apps.core.views import (
    AppearanceSettingsView,
    DashboardView,
    ClusteringSettingsView,
    ClusteringRecalculateView,
    FieldAwareRelevanceSettingsView,
    ClickDistanceSettingsView,
    ClickDistanceRecalculateView,
    FeedbackRerankSettingsView,
    FaviconUploadView,
    GA4GSCSettingsView,
    GSCConnectionTestView,
    LearnedAnchorSettingsView,
    LinkFreshnessRecalculateView,
    LinkFreshnessSettingsView,
    LogoUploadView,
    PhraseMatchingSettingsView,
    RareTermPropagationSettingsView,
    ChallengerEvaluateView,
    WeightTuneTriggerView,
    SiloSettingsView,
    SlateDiversitySettingsView,
    WeightedAuthorityRecalculateView,
    WeightedAuthoritySettingsView,
    UserMeView,
    UserLogoutView,
    LocalVerificationBootstrapView,
    ActiveUsersView,
    GraphCandidateSettingsView,
    ValueModelSettingsView,
    SpamGuardSettingsView,
    GraphRebuildView,
    WebhookSettingsView,
    WebhookTestView,
    WordPressSettingsView,
    WordPressSyncRunView,
    WordPressTestConnectionView,
    XenForoSettingsView,
    XenForoTestConnectionView,
)
from apps.core.views_passkey import (
    PasskeyRegisterBeginView,
    PasskeyRegisterFinishView,
    PasskeyLoginBeginView,
    PasskeyLoginFinishView,
)
from apps.graph.views import (
    BrokenLinkViewSet,
    GapAnalysisView,
    GraphStatsView,
    GraphTopologyView,
    PageRankEquityView,
    OrphanArticleListView,
    OrphanExportCSVView,
    OrphanSuggestView,
    GraphPathView,
)
from apps.knowledge_graph.views import EntityListView
from apps.cooccurrence.views import (
    CoOccurrencePairListView,
    CoOccurrencePairBySourceView,
    CoOccurrenceRunListView,
    TriggerCoOccurrenceView,
    BehavioralHubListView,
    BehavioralHubDetailView,
    BehavioralHubMemberView,
    BehavioralHubMemberDetailView,
    TriggerHubDetectionView,
    CoOccurrenceSettingsView,
)
from apps.suggestions.views import (
    MetaAlgorithmSettingsView,
    MetaAlgorithmToggleView,
    PipelineDiagnosticViewSet,
    PipelineRunViewSet,
    RankingChallengerViewSet,
    SuggestionReadinessView,
    SuggestionViewSet,
    WeightAdjustmentHistoryViewSet,
    WeightPresetViewSet,
)
from apps.sync.views import (
    ImportUploadView,
    SyncJobViewSet,
    XenForoWebhookView,
    WordPressWebhookView,
    WebhookReceiptViewSet,
)
from django.conf import settings
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.throttling import AnonRateThrottle


class _LoginRateThrottle(AnonRateThrottle):
    """Per-IP throttle on the login endpoint.

    Ten attempts per rolling sixty-second window. This covers both the
    login page and the session re-auth dialog, which share the same
    endpoint. A 60-second window prevents the two flows from competing
    for the same short budget. DRF's default rate parser only understands
    whole units (s/m/h/d), so we override parse_rate to express the
    window directly.
    """

    rate = "10/60s"

    def parse_rate(self, rate):
        return (10, 60)

    def allow_request(self, request, view):
        # Skip in DEBUG so a few mistyped passwords can't lock the local
        # operator out of their own dev stack. Production (DEBUG=False)
        # keeps the brute-force guard.
        if settings.DEBUG:
            return True
        return super().allow_request(request, view)


class _CsrfFreeObtainAuthToken(ObtainAuthToken):
    """Token login endpoint — no session auth so CSRF is never checked."""

    authentication_classes = []
    throttle_classes = [_LoginRateThrottle]


obtain_auth_token = _CsrfFreeObtainAuthToken.as_view()

from apps.api.ml_views import MLDistillView, MLEmbedView

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
router.register(
    r"weight-history", WeightAdjustmentHistoryViewSet, basename="weight-history"
)
router.register(
    r"weight-challengers", RankingChallengerViewSet, basename="weight-challenger"
)
router.register(r"webhook-receipts", WebhookReceiptViewSet, basename="webhook-receipt")
router.register(r"health", HealthStatusViewSet, basename="health")

urlpatterns = [
    path("auth/token/", obtain_auth_token, name="auth-token"),
    path("auth/me/", UserMeView.as_view(), name="user-me"),
    path("auth/logout/", UserLogoutView.as_view(), name="user-logout"),
    path(
        "auth/local-verification-bootstrap/",
        LocalVerificationBootstrapView.as_view(),
        name="auth-local-verification-bootstrap",
    ),
    path("auth/active-users/", ActiveUsersView.as_view(), name="auth-active-users"),
    # WebAuthn / Passkey — two ceremonies (register + login), two steps each.
    path(
        "auth/passkey/register/begin/",
        PasskeyRegisterBeginView.as_view(),
        name="passkey-register-begin",
    ),
    path(
        "auth/passkey/register/finish/",
        PasskeyRegisterFinishView.as_view(),
        name="passkey-register-finish",
    ),
    path(
        "auth/passkey/login/begin/",
        PasskeyLoginBeginView.as_view(),
        name="passkey-login-begin",
    ),
    path(
        "auth/passkey/login/finish/",
        PasskeyLoginFinishView.as_view(),
        name="passkey-login-finish",
    ),
    path("", include("apps.core.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("", include("apps.audit.urls")),
    path("", include("apps.plugins.urls")),
    # Keep these ahead of the health viewset routes so "disk" and "gpu"
    # are not mistaken for service-key detail lookups.
    path("health/disk/", HealthDiskView.as_view(), name="health-disk"),
    path("health/gpu/", HealthGpuView.as_view(), name="health-gpu"),
    # Phase SR / Phase MS — these share the `suggestions/` + `meta-algorithms/`
    # URL prefixes with DRF router ViewSets below. Must come BEFORE the
    # router include or DRF treats "readiness" and "<id>/toggle" as pk
    # lookups on SuggestionViewSet / non-existent meta ViewSet and 404s.
    path(
        "suggestions/readiness/",
        SuggestionReadinessView.as_view(),
        name="suggestion-readiness",
    ),
    path(
        "meta-algorithms/",
        MetaAlgorithmSettingsView.as_view(),
        name="meta-algorithm-settings",
    ),
    path(
        "meta-algorithms/<str:algo_id>/toggle/",
        MetaAlgorithmToggleView.as_view(),
        name="meta-algorithm-toggle",
    ),
    path(
        "glitchtip/events/",
        GlitchtipEventsView.as_view(),
        name="glitchtip-events",
    ),
    path("", include(router.urls)),
    path("import/upload/", ImportUploadView.as_view(), name="import-upload"),
    path("ml/distill/", MLDistillView.as_view(), name="ml-distill"),
    path("ml/embed/", MLEmbedView.as_view(), name="ml-embed"),
    path(
        "sync/webhooks/xenforo/", XenForoWebhookView.as_view(), name="xenforo-webhook"
    ),
    path(
        "sync/webhooks/wordpress/",
        WordPressWebhookView.as_view(),
        name="wordpress-webhook",
    ),
    # Plan item 24 — 3-minute dry-run sync preview.
    path(
        "sync/preview/",
        __import__(
            "apps.core.views_preview", fromlist=["SyncPreviewView"]
        ).SyncPreviewView.as_view(),
        name="sync-preview",
    ),
    # Plan item 26 — safe prune (GET allowed targets; POST dry-run / commit).
    path(
        "prune/safe/",
        __import__(
            "apps.core.views_prune", fromlist=["SafePruneView"]
        ).SafePruneView.as_view(),
        name="prune-safe",
    ),
    path(
        "settings/appearance/",
        AppearanceSettingsView.as_view(),
        name="appearance-settings",
    ),
    path("settings/silos/", SiloSettingsView.as_view(), name="silo-settings"),
    path(
        "settings/weighted-authority/",
        WeightedAuthoritySettingsView.as_view(),
        name="weighted-authority-settings",
    ),
    path(
        "settings/weighted-authority/recalculate/",
        WeightedAuthorityRecalculateView.as_view(),
        name="weighted-authority-recalculate",
    ),
    path(
        "settings/link-freshness/",
        LinkFreshnessSettingsView.as_view(),
        name="link-freshness-settings",
    ),
    path(
        "settings/link-freshness/recalculate/",
        LinkFreshnessRecalculateView.as_view(),
        name="link-freshness-recalculate",
    ),
    path(
        "settings/phrase-matching/",
        PhraseMatchingSettingsView.as_view(),
        name="phrase-matching-settings",
    ),
    path(
        "settings/learned-anchor/",
        LearnedAnchorSettingsView.as_view(),
        name="learned-anchor-settings",
    ),
    path(
        "settings/rare-term-propagation/",
        RareTermPropagationSettingsView.as_view(),
        name="rare-term-propagation-settings",
    ),
    path(
        "settings/field-aware-relevance/",
        FieldAwareRelevanceSettingsView.as_view(),
        name="field-aware-relevance-settings",
    ),
    path("settings/ga4-gsc/", GA4GSCSettingsView.as_view(), name="ga4-gsc-settings"),
    path(
        "settings/ga4-gsc/test-connection/",
        GSCConnectionTestView.as_view(),
        name="ga4-gsc-test-connection",
    ),
    path(
        "settings/explore-exploit/",
        FeedbackRerankSettingsView.as_view(),
        name="explore-exploit-settings",
    ),
    path(
        "settings/click-distance/",
        ClickDistanceSettingsView.as_view(),
        name="settings-click-distance",
    ),
    path(
        "settings/click-distance/recalculate/",
        ClickDistanceRecalculateView.as_view(),
        name="settings-click-distance-recalculate",
    ),
    path(
        "settings/clustering/",
        ClusteringSettingsView.as_view(),
        name="clustering-settings",
    ),
    path(
        "settings/clustering/recalculate/",
        ClusteringRecalculateView.as_view(),
        name="clustering-recalculate",
    ),
    path(
        "settings/slate-diversity/",
        SlateDiversitySettingsView.as_view(),
        name="slate-diversity-settings",
    ),
    path(
        "settings/weight-tune/trigger/",
        WeightTuneTriggerView.as_view(),
        name="weight-tune-trigger",
    ),
    path(
        "settings/weight-tune/evaluate/<str:run_id>/",
        ChallengerEvaluateView.as_view(),
        name="weight-tune-evaluate",
    ),
    path(
        "settings/wordpress/",
        WordPressSettingsView.as_view(),
        name="wordpress-settings",
    ),
    path(
        "settings/wordpress/test-connection/",
        WordPressTestConnectionView.as_view(),
        name="wordpress-test-connection",
    ),
    path("settings/xenforo/", XenForoSettingsView.as_view(), name="xenforo-settings"),
    path(
        "settings/xenforo/test-connection/",
        XenForoTestConnectionView.as_view(),
        name="xenforo-test-connection",
    ),
    path("settings/webhooks/", WebhookSettingsView.as_view(), name="webhook-settings"),
    path("settings/webhooks/test/", WebhookTestView.as_view(), name="webhook-test"),
    path("settings/logo/", LogoUploadView.as_view(), name="settings-logo"),
    path("settings/favicon/", FaviconUploadView.as_view(), name="settings-favicon"),
    path(
        "settings/graph-candidate/",
        GraphCandidateSettingsView.as_view(),
        name="graph-candidate-settings",
    ),
    path(
        "settings/value-model/",
        ValueModelSettingsView.as_view(),
        name="value-model-settings",
    ),
    path(
        "settings/spam-guards/",
        SpamGuardSettingsView.as_view(),
        name="settings-spam-guards",
    ),
    path("settings/graph/rebuild/", GraphRebuildView.as_view(), name="graph-rebuild"),
    path(
        "settings/cooccurrence/",
        CoOccurrenceSettingsView.as_view(),
        name="cooccurrence-settings",
    ),
    path(
        "cooccurrence/pairs/",
        CoOccurrencePairListView.as_view(),
        name="cooccurrence-pairs",
    ),
    path(
        "cooccurrence/pairs/<int:source_id>/",
        CoOccurrencePairBySourceView.as_view(),
        name="cooccurrence-pairs-by-source",
    ),
    path(
        "cooccurrence/runs/",
        CoOccurrenceRunListView.as_view(),
        name="cooccurrence-runs",
    ),
    path(
        "cooccurrence/compute/",
        TriggerCoOccurrenceView.as_view(),
        name="cooccurrence-compute",
    ),
    path("behavioral-hubs/", BehavioralHubListView.as_view(), name="behavioral-hubs"),
    path(
        "behavioral-hubs/detect/",
        TriggerHubDetectionView.as_view(),
        name="behavioral-hub-detect",
    ),
    path(
        "behavioral-hubs/<uuid:hub_id>/",
        BehavioralHubDetailView.as_view(),
        name="behavioral-hub-detail",
    ),
    path(
        "behavioral-hubs/<uuid:hub_id>/members/",
        BehavioralHubMemberView.as_view(),
        name="behavioral-hub-members",
    ),
    path(
        "behavioral-hubs/<uuid:hub_id>/members/<int:content_item_id>/",
        BehavioralHubMemberDetailView.as_view(),
        name="behavioral-hub-member-detail",
    ),
    path("graph/stats/", GraphStatsView.as_view(), name="graph-stats"),
    path("graph/entities/", EntityListView.as_view(), name="graph-entities"),
    path("graph/orphans/", OrphanArticleListView.as_view(), name="graph-orphans"),
    path(
        "graph/orphans/export-csv/",
        OrphanExportCSVView.as_view(),
        name="graph-orphans-export-csv",
    ),
    path(
        "graph/orphans/<int:pk>/suggest/",
        OrphanSuggestView.as_view(),
        name="graph-orphan-suggest",
    ),
    path("graph/path/", GraphPathView.as_view(), name="graph-path"),
    path("graph/topology/", GraphTopologyView.as_view(), name="graph-topology"),
    path(
        "graph/pagerank-equity/",
        PageRankEquityView.as_view(),
        name="graph-pagerank-equity",
    ),
    path("graph/gap-analysis/", GapAnalysisView.as_view(), name="graph-gap-analysis"),
    path(
        "sync/wordpress/run/", WordPressSyncRunView.as_view(), name="wordpress-sync-run"
    ),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    # Phase SR + MS routes live above the DRF router include (see note
    # next to `suggestions/readiness/` earlier in this file).
    path("crawler/", include("apps.crawler.urls")),
    path("", include("apps.notifications.urls")),
    path("system/status/", include("apps.diagnostics.urls")),
    path("auth/", include("rest_framework.urls", namespace="rest_framework")),
    path("benchmarks/", include("apps.benchmarks.urls")),
    # Phase OF — /api/operations/events/ hydrates the feed on reload.
    path("operations/", include("apps.ops_feed.urls")),
    # PR-B — Scheduled Updates REST surface (jobs / alerts / window status).
    path(
        "scheduled-updates/",
        include("apps.scheduled_updates.urls", namespace="scheduled_updates"),
    ),
    # Embeddings page (plan Part 8c, FR-235).
    path("embedding/status/", __import__("apps.api.embedding_views", fromlist=["embedding_status"]).embedding_status, name="embedding-status"),
    path("embedding/provider/", __import__("apps.api.embedding_views", fromlist=["embedding_provider"]).embedding_provider, name="embedding-provider"),
    path("embedding/settings/", __import__("apps.api.embedding_views", fromlist=["embedding_settings"]).embedding_settings, name="embedding-settings"),
    path("embedding/test-connection/", __import__("apps.api.embedding_views", fromlist=["embedding_test_connection"]).embedding_test_connection, name="embedding-test-connection"),
    path("embedding/bakeoff/", __import__("apps.api.embedding_views", fromlist=["embedding_bakeoff_results"]).embedding_bakeoff_results, name="embedding-bakeoff-results"),
    path("embedding/bakeoff/run/", __import__("apps.api.embedding_views", fromlist=["embedding_bakeoff_run"]).embedding_bakeoff_run, name="embedding-bakeoff-run"),
    path("embedding/audit/run/", __import__("apps.api.embedding_views", fromlist=["embedding_audit_run"]).embedding_audit_run, name="embedding-audit-run"),
    path("embedding/gate-decisions/", __import__("apps.api.embedding_views", fromlist=["embedding_gate_decisions"]).embedding_gate_decisions, name="embedding-gate-decisions"),
    path("embedding/hardware-profile/", __import__("apps.api.embedding_views", fromlist=["embedding_hardware_profile"]).embedding_hardware_profile, name="embedding-hardware-profile"),
]
