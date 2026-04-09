"""Knowledge graph API views — entity browsing."""

from __future__ import annotations

from django.db.models import Count
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from .models import EntityNode
from .serializers import EntityNodeSerializer


class _EntityPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class EntityListView(ListAPIView):
    """
    GET /api/graph/entities/

    Lists all EntityNode records ordered by article count descending.

    Query params:
      ?entity_type=keyword|named_entity|topic_tag  — filter by type
      ?search=<text>                                — icontains on canonical_form
      ?page=<n>                                     — pagination
    """

    serializer_class = EntityNodeSerializer
    pagination_class = _EntityPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = EntityNode.objects.annotate(article_count=Count("article_edges")).order_by(
            "-article_count", "canonical_form"
        )

        entity_type = self.request.query_params.get("entity_type")
        if entity_type and entity_type in {"keyword", "named_entity", "topic_tag"}:
            qs = qs.filter(entity_type=entity_type)

        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(canonical_form__icontains=search)

        return qs
