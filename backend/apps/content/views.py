"""
Content app DRF viewsets.

All content endpoints are READ-ONLY — the app never writes content to XenForo.
Content is imported via the sync pipeline (Celery tasks).
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ContentItem, ScopeItem, Sentence, SiloGroup
from .serializers import (
    ContentItemDetailSerializer,
    ContentItemListSerializer,
    ScopeItemSerializer,
    SentenceSerializer,
    SiloGroupSerializer,
)


class SiloGroupViewSet(viewsets.ModelViewSet):
    """CRUD API for topical silo groups."""

    queryset = SiloGroup.objects.order_by("display_order", "name")
    serializer_class = SiloGroupSerializer
    pagination_class = None
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "slug", "description"]
    ordering_fields = ["display_order", "name", "updated_at"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]


class ScopeItemViewSet(viewsets.ModelViewSet):
    """
    List and retrieve XenForo forum nodes and resource categories.

    GET /api/scopes/          — list all scope items
    GET /api/scopes/{id}/     — retrieve a single scope item
    GET /api/scopes/enabled/  — list only enabled scopes
    """

    queryset = ScopeItem.objects.select_related("parent", "silo_group").order_by("display_order", "title")
    serializer_class = ScopeItemSerializer
    pagination_class = None
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["scope_type", "is_enabled", "silo_group"]
    search_fields = ["title"]
    http_method_names = ["get", "patch", "head", "options"]

    @action(detail=False, methods=["get"])
    def enabled(self, request) -> Response:
        """Return only enabled scope items."""
        qs = self.get_queryset().filter(is_enabled=True)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs) -> Response:
        disallowed_keys = set(request.data.keys()) - {"silo_group"}
        if disallowed_keys:
            return Response(
                {"detail": "Only silo_group can be updated from this endpoint."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().partial_update(request, *args, **kwargs)


class ContentItemViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and retrieve content items (threads, resources, WordPress posts).

    GET /api/content/              — paginated list (lightweight)
    GET /api/content/{id}/         — full detail with distilled_text
    GET /api/content/{id}/sentences/ — list sentences for this content item
    """

    queryset = ContentItem.objects.select_related("scope").order_by("-march_2026_pagerank_score")
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["content_type", "scope", "is_deleted"]
    search_fields = ["title", "content_id"]
    ordering_fields = [
        "march_2026_pagerank_score",
        "velocity_score",
        "view_count",
        "post_date",
        "created_at",
    ]

    def get_serializer_class(self):
        if self.action == "retrieve" or self.action == "sentences":
            return ContentItemDetailSerializer
        return ContentItemListSerializer

    @action(detail=True, methods=["get"])
    def sentences(self, request, pk=None) -> Response:
        """Return all sentences extracted from this content item's post."""
        content_item = self.get_object()
        sentences = (
            Sentence.objects
            .filter(content_item=content_item)
            .order_by("position")
        )
        serializer = SentenceSerializer(sentences, many=True)
        return Response(serializer.data)
