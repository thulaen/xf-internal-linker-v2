"""
Crawler REST API views.

Endpoints for managing crawl sessions, sitemap configuration, SEO audit
results, and the system activity feed.
"""

import logging
import uuid as uuid_mod

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from .models import (
    CrawlSession,
    CrawledLink,
    CrawledPageMeta,
    SitemapConfig,
    SystemEvent,
)
from .serializers import (
    CrawledLinkSerializer,
    CrawledPageMetaSerializer,
    CrawledPageMetaSummarySerializer,
    CrawlerContextSerializer,
    CrawlSessionCreateSerializer,
    CrawlSessionSerializer,
    SEOAuditSummarySerializer,
    SitemapAutoDiscoverSerializer,
    SitemapConfigCreateSerializer,
    SitemapConfigSerializer,
    SystemEventSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CrawlSession CRUD + actions
# ---------------------------------------------------------------------------
class CrawlSessionViewSet(ModelViewSet):
    """Manage crawl sessions: list, start, pause, resume."""

    queryset = CrawlSession.objects.all()
    serializer_class = CrawlSessionSerializer
    pagination_class = None

    def create(self, request):
        """Start a new crawl session or resume a paused one."""
        ser = CrawlSessionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        resume_id = ser.validated_data.get("resume_session_id")
        if resume_id:
            return self._resume_session(resume_id)

        session = CrawlSession.objects.create(
            site_domain=ser.validated_data["site_domain"],
            status="pending",
            config={
                "rate_limit": ser.validated_data.get("rate_limit", 4),
                "max_depth": ser.validated_data.get("max_depth", 5),
                "excluded_paths": [
                    "/members/",
                    "/login/",
                    "/register/",
                    "/account/",
                    "/search/",
                    "/admin.php",
                    "/help/",
                ],
                "timeout_hours": 2,
            },
        )

        # TODO Phase 2: Enqueue crawl_session job to C# HTTP Worker via Redis
        # from apps.graph.services.http_worker_client import queue_job
        # queue_job(str(session.session_id), "crawl_session", {...})

        _emit_event(
            "info",
            "crawler",
            f"Crawl session started for {session.site_domain}",
            metadata={"session_id": str(session.session_id)},
        )

        return Response(
            CrawlSessionSerializer(session).data,
            status=status.HTTP_201_CREATED,
        )

    def _resume_session(self, session_id):
        try:
            session = CrawlSession.objects.get(session_id=session_id, is_resumable=True)
        except CrawlSession.DoesNotExist:
            return Response(
                {"error": "Session not found or not resumable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        session.status = "pending"
        session.message = "Resuming from checkpoint..."
        session.save(update_fields=["status", "message", "updated_at"])

        # TODO Phase 2: Enqueue resume job to C# HTTP Worker

        _emit_event(
            "info",
            "crawler",
            f"Resuming crawl for {session.site_domain}",
            metadata={"session_id": str(session.session_id)},
        )

        return Response(CrawlSessionSerializer(session).data)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        """Pause a running crawl session."""
        session = self.get_object()
        if session.status != "running":
            return Response(
                {"error": "Only running sessions can be paused."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.status = "paused"
        session.paused_at = timezone.now()
        session.is_resumable = True
        session.message = "Paused by user."
        session.save(
            update_fields=[
                "status",
                "paused_at",
                "is_resumable",
                "message",
                "updated_at",
            ]
        )

        _emit_event(
            "info",
            "crawler",
            f"Crawl paused for {session.site_domain} ({session.pages_crawled} pages done)",
        )

        return Response(CrawlSessionSerializer(session).data)


# ---------------------------------------------------------------------------
# CrawledPageMeta (read-only)
# ---------------------------------------------------------------------------
class CrawledPageMetaViewSet(ReadOnlyModelViewSet):
    """List and detail view for crawled page metadata."""

    serializer_class = CrawledPageMetaSummarySerializer
    pagination_class = None

    def get_queryset(self):
        qs = CrawledPageMeta.objects.all()
        session_id = self.request.query_params.get("session")
        if session_id:
            qs = qs.filter(session_id=uuid_mod.UUID(session_id))
        http_status = self.request.query_params.get("http_status")
        if http_status:
            qs = qs.filter(http_status=int(http_status))
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CrawledPageMetaSerializer
        return CrawledPageMetaSummarySerializer


# ---------------------------------------------------------------------------
# CrawledLink (read-only)
# ---------------------------------------------------------------------------
class CrawledLinkViewSet(ReadOnlyModelViewSet):
    """List internal links discovered during crawl."""

    serializer_class = CrawledLinkSerializer
    pagination_class = None

    def get_queryset(self):
        qs = CrawledLink.objects.select_related("page").all()
        session_id = self.request.query_params.get("session")
        if session_id:
            qs = qs.filter(page__session_id=uuid_mod.UUID(session_id))
        context = self.request.query_params.get("context")
        if context:
            qs = qs.filter(context_class=context)
        return qs


# ---------------------------------------------------------------------------
# SitemapConfig CRUD + auto-discover
# ---------------------------------------------------------------------------
class SitemapConfigViewSet(ModelViewSet):
    """Manage sitemap URL configuration per domain."""

    queryset = SitemapConfig.objects.all()
    serializer_class = SitemapConfigSerializer
    pagination_class = None

    def create(self, request):
        ser = SitemapConfigCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        raw_url = ser.validated_data["sitemap_url"]
        normalized = _normalize_sitemap_url(raw_url)

        if SitemapConfig.objects.filter(normalized_url=normalized).exists():
            return Response(
                {"error": "This sitemap URL already exists (after normalisation)."},
                status=status.HTTP_409_CONFLICT,
            )

        config = SitemapConfig.objects.create(
            domain=ser.validated_data["domain"],
            sitemap_url=raw_url,
            normalized_url=normalized,
            discovery_method="manual",
        )
        return Response(
            SitemapConfigSerializer(config).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"])
    def auto_discover(self, request):
        """Auto-discover sitemaps for a domain by checking common locations."""
        ser = SitemapAutoDiscoverSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        # TODO Phase 2: Call C# HTTP Worker to check:
        # /sitemap.xml, /sitemap_index.xml, /sitemap.php, robots.txt Sitemap:
        # For now return a placeholder.
        return Response(
            {
                "message": "Auto-discovery will be implemented in Phase 2.",
                "domain": ser.validated_data["domain"],
            }
        )

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Test-fetch a sitemap and report URL count."""
        config = self.get_object()

        # TODO Phase 2: Call crawl_sitemap() and update last_fetch_at
        return Response(
            {
                "message": "Sitemap test will be implemented in Phase 2.",
                "sitemap_url": config.sitemap_url,
            }
        )


# ---------------------------------------------------------------------------
# SystemEvent (read-only feed)
# ---------------------------------------------------------------------------
class SystemEventViewSet(ReadOnlyModelViewSet):
    """Activity feed for the Dashboard. Most recent 50 events."""

    serializer_class = SystemEventSerializer
    pagination_class = None

    def get_queryset(self):
        qs = SystemEvent.objects.all()
        source = self.request.query_params.get("source")
        if source:
            qs = qs.filter(source=source)
        severity = self.request.query_params.get("severity")
        if severity:
            qs = qs.filter(severity=severity)
        return qs[:50]


# ---------------------------------------------------------------------------
# SEO Audit aggregation
# ---------------------------------------------------------------------------
class SEOAuditView(APIView):
    """Aggregated SEO audit summary for the latest completed crawl session."""

    def get(self, request):
        session = (
            CrawlSession.objects.filter(status="completed")
            .order_by("-completed_at")
            .first()
        )
        if not session:
            return Response(
                {"error": "No completed crawl session found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        pages = CrawledPageMeta.objects.filter(session=session)
        total = pages.count()

        # Count duplicate titles (titles appearing more than once).
        dup_titles = (
            pages.exclude(title="")
            .values("title")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
            .count()
        )

        # Noindexed pages.
        noindexed = pages.filter(robots_meta__icontains="noindex").count()

        # Images missing alt (aggregate across all pages).
        img_alt_agg = pages.aggregate(total=Sum("img_missing_alt"))
        img_missing_alt_total = img_alt_agg["total"] or 0

        summary = {
            "total_pages": total,
            "missing_title": pages.filter(title="").count(),
            "duplicate_titles": dup_titles,
            "missing_meta_description": pages.filter(meta_description="").count(),
            "missing_h1": pages.filter(h1_count=0).count(),
            "multiple_h1": pages.filter(h1_count__gt=1).count(),
            "missing_canonical": pages.filter(canonical_url="").count(),
            "noindexed_pages": noindexed,
            "thin_content": pages.filter(word_count__lt=200, word_count__gt=0).count(),
            "slow_pages": pages.filter(response_time_ms__gt=2000).count(),
            "non_mobile": pages.filter(has_viewport=False).count(),
            "missing_og": pages.filter(og_title="").count(),
            "images_missing_alt": img_missing_alt_total,
            "broken_links": pages.filter(
                Q(http_status__gte=400) | Q(http_status=0)
            ).count(),
            "orphan_pages": 0,  # Computed in Phase 5 after link graph build
        }

        ser = SEOAuditSummarySerializer(summary)
        return Response(ser.data)


# ---------------------------------------------------------------------------
# Crawler page context header
# ---------------------------------------------------------------------------
class CrawlerContextView(APIView):
    """Lightweight data for the crawler page context header bar."""

    def get(self, request):
        last_session = (
            CrawlSession.objects.filter(status="completed")
            .order_by("-completed_at")
            .first()
        )
        active_session = (
            CrawlSession.objects.filter(status__in=["pending", "running"])
            .order_by("-created_at")
            .first()
        )

        # Estimate storage: sum of extracted_text lengths across all sessions.
        storage = CrawledPageMeta.objects.aggregate(total=Sum("content_length"))

        data = {
            "last_crawl_at": last_session.completed_at if last_session else None,
            "total_pages_crawled": CrawledPageMeta.objects.count(),
            "storage_bytes": storage["total"] or 0,
            "active_session": (
                CrawlSessionSerializer(active_session).data if active_session else None
            ),
        }
        return Response(CrawlerContextSerializer(data).data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize_sitemap_url(url: str) -> str:
    """Lowercase host, strip trailing slash, strip fragment."""
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    normalized = urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            "",
            "",
        )
    )
    return normalized


def _emit_event(
    severity: str,
    source: str,
    title: str,
    detail: str = "",
    metadata: dict | None = None,
) -> SystemEvent:
    """Create a SystemEvent and broadcast via WebSocket."""
    event = SystemEvent.objects.create(
        severity=severity,
        source=source,
        title=title,
        detail=detail,
        metadata=metadata or {},
    )
    # TODO Phase 4: Broadcast via channel_layer to 'system_pulse' group
    return event
