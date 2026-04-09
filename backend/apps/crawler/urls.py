"""
Crawler URL configuration.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"sessions", views.CrawlSessionViewSet, basename="crawl-session")
router.register(r"pages", views.CrawledPageMetaViewSet, basename="crawled-page")
router.register(r"links", views.CrawledLinkViewSet, basename="crawled-link")
router.register(r"sitemaps", views.SitemapConfigViewSet, basename="sitemap-config")
router.register(r"events", views.SystemEventViewSet, basename="system-event")

urlpatterns = [
    path("", include(router.urls)),
    path("seo-audit/", views.SEOAuditView.as_view(), name="seo-audit"),
    path("context/", views.CrawlerContextView.as_view(), name="crawler-context"),
]
