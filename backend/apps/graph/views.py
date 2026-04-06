"""Graph views — existing-link, broken-link, and graph explorer API endpoints."""

from __future__ import annotations

import csv
import uuid
from datetime import datetime

from django.http import StreamingHttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import BrokenLinkSerializer


class BrokenLinkViewSet(viewsets.ModelViewSet):
    """
    Link-health endpoints.

    GET   /api/broken-links/
    PATCH /api/broken-links/{broken_link_id}/
    POST  /api/broken-links/scan/
    GET   /api/broken-links/export-csv/
    """

    permission_classes = [AllowAny]
    serializer_class = BrokenLinkSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status", "http_status"]
    http_method_names = ["get", "patch", "post", "head", "options"]
    lookup_field = "broken_link_id"

    def get_queryset(self):
        from apps.graph.models import BrokenLink

        return BrokenLink.objects.select_related("source_content").order_by("status", "-last_checked_at")

    def partial_update(self, request, *args, **kwargs) -> Response:
        disallowed_keys = set(request.data.keys()) - {"status", "notes"}
        if disallowed_keys:
            return Response(
                {"detail": "Only status and notes can be updated."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().partial_update(request, *args, **kwargs)

    @action(detail=False, methods=["post"])
    def scan(self, request) -> Response:
        from apps.graph.services.http_worker_client import HttpWorkerError
        from apps.pipeline.tasks import dispatch_broken_link_scan

        try:
            payload = dispatch_broken_link_scan(job_id=str(uuid.uuid4()))
            return Response(payload, status=status.HTTP_202_ACCEPTED)
        except HttpWorkerError as exc:
            return Response(
                {
                    "detail": (
                        "The broken-link scan could not start because the C# worker lane is unavailable. "
                        "The system did not silently fall back to Celery."
                    ),
                    "error": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    @action(detail=False, methods=["get"], url_path="export-csv")
    def export_csv(self, request) -> StreamingHttpResponse:
        queryset = self.filter_queryset(self.get_queryset())

        class Echo:
            def write(self, value: str) -> str:
                return value

        writer = csv.writer(Echo())

        def _rows():
            yield writer.writerow(
                [
                    "broken_link_id",
                    "source_content_id",
                    "source_content_title",
                    "source_content_url",
                    "url",
                    "http_status",
                    "redirect_url",
                    "status",
                    "notes",
                    "first_detected_at",
                    "last_checked_at",
                ]
            )
            for record in queryset.iterator(chunk_size=250):
                yield writer.writerow(
                    [
                        str(record.broken_link_id),
                        record.source_content_id,
                        record.source_content.title,
                        record.source_content.url,
                        record.url,
                        record.http_status,
                        record.redirect_url,
                        record.status,
                        record.notes,
                        _isoformat(record.first_detected_at),
                        _isoformat(record.last_checked_at),
                    ]
                )

        response = StreamingHttpResponse(_rows(), content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="broken-links-{datetime.utcnow().strftime("%Y%m%d-%H%M%S")}.csv"'
        )
        return response


def _isoformat(value: datetime | None) -> str:
    return value.isoformat() if value else ""


# ── Graph Explorer Views ──────────────────────────────────────────────────────


class GraphStatsView(APIView):
    """
    GET /api/graph/stats/

    Returns a summary of the knowledge graph state:
      total_nodes, total_edges, entity_count, orphan_count,
      connected_pct, topic_count
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        from apps.content.models import ContentItem, SiloGroup
        from apps.graph.models import ExistingLink
        from apps.knowledge_graph.models import EntityNode

        total_nodes = ContentItem.objects.filter(is_deleted=False).count()
        total_edges = ExistingLink.objects.count()
        entity_count = EntityNode.objects.count()
        topic_count = SiloGroup.objects.count()

        linked_ids = (
            ExistingLink.objects
            .filter(
                to_content_item__is_deleted=False,
                from_content_item__is_deleted=False,
            )
            .values_list("to_content_item_id", flat=True)
            .distinct()
        )
        orphan_count = (
            ContentItem.objects
            .filter(is_deleted=False)
            .exclude(pk__in=linked_ids)
            .count()
        )

        connected_pct = (
            round((total_nodes - orphan_count) / total_nodes * 100, 1)
            if total_nodes > 0
            else 0.0
        )

        return Response(
            {
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "entity_count": entity_count,
                "orphan_count": orphan_count,
                "connected_pct": connected_pct,
                "topic_count": topic_count,
            }
        )


class _OrphanPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class OrphanArticleListView(ListAPIView):
    """
    GET /api/graph/orphans/

    Returns ContentItems that have no inbound ExistingLinks,
    ordered by pagerank score descending (lowest authority first).
    """

    pagination_class = _OrphanPagination
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        from apps.content.serializers import ContentItemListSerializer
        return ContentItemListSerializer

    def get_queryset(self):
        from apps.content.models import ContentItem
        from apps.graph.models import ExistingLink

        linked_ids = (
            ExistingLink.objects
            .filter(
                to_content_item__is_deleted=False,
                from_content_item__is_deleted=False,
            )
            .values_list("to_content_item_id", flat=True)
            .distinct()
        )
        return (
            ContentItem.objects
            .filter(is_deleted=False)
            .exclude(pk__in=linked_ids)
            .order_by("march_2026_pagerank_score", "id")
        )


class GraphPathView(APIView):
    """
    GET /api/graph/path/?from_id=<int>&to_id=<int>

    Finds the shortest directed link path between two articles using BFS.
    Max depth: 4 hops.

    Returns:
      { found: true,  path: [{id, title, url}, ...], hops: N }
      { found: false, path: [],                       hops: 0 }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        try:
            from_id = int(request.query_params["from_id"])
            to_id = int(request.query_params["to_id"])
        except (KeyError, ValueError, TypeError):
            return Response(
                {"detail": "Both from_id and to_id (integers) are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        path = _bfs_path(from_id, to_id, max_depth=4)
        if path is None:
            return Response({"found": False, "path": [], "hops": 0})
        return Response({"found": True, "path": path, "hops": len(path) - 1})


class GraphTopologyView(APIView):
    """
    GET /api/graph/topology/

    Returns nodes and links for the D3.js force-directed link graph.

    Query params:
      ?limit=<int>   Max number of nodes (default 500, max 1000).
                     Nodes are selected by descending PageRank so the most
                     connected articles appear first.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        from apps.content.models import ContentItem
        from apps.graph.models import ExistingLink
        from django.db.models import Count

        try:
            limit = min(int(request.query_params.get("limit", 500)), 1000)
        except (ValueError, TypeError):
            limit = 500

        # One query: top-N nodes annotated with in/out degree counts.
        qs = (
            ContentItem.objects
            .filter(is_deleted=False)
            .annotate(
                in_degree=Count("incoming_links", distinct=True),
                out_degree=Count("outgoing_links", distinct=True),
            )
            .values(
                "id", "title", "content_type",
                "scope_id",
                "march_2026_pagerank_score",
                "in_degree", "out_degree",
            )
            .order_by("-march_2026_pagerank_score")[:limit]
        )

        node_ids: set[int] = set()
        nodes: list[dict] = []
        for row in qs:
            node_ids.add(row["id"])
            nodes.append({
                "id": row["id"],
                "title": row["title"],
                "type": row["content_type"],
                "silo_id": row["scope_id"] or 0,
                "pagerank": float(row["march_2026_pagerank_score"] or 0),
                "in_degree": row["in_degree"],
                "out_degree": row["out_degree"],
            })

        # Only include edges where both endpoints are in the node set.
        links_qs = (
            ExistingLink.objects
            .filter(
                from_content_item_id__in=node_ids,
                to_content_item_id__in=node_ids,
            )
            .values("from_content_item_id", "to_content_item_id", "context_class")
        )

        links: list[dict] = [
            {
                "source": row["from_content_item_id"],
                "target": row["to_content_item_id"],
                "context": row["context_class"] or "contextual",
                "weight": 1.0,
            }
            for row in links_qs
        ]

        return Response({"nodes": nodes, "links": links})


def _bfs_path(from_id: int, to_id: int, max_depth: int = 4) -> list | None:
    """BFS over ExistingLink directed edges. Returns node list or None."""
    from apps.content.models import ContentItem
    from apps.graph.models import ExistingLink

    # Resolve the start node
    start = (
        ContentItem.objects
        .filter(pk=from_id, is_deleted=False)
        .values("id", "title", "url")
        .first()
    )
    if start is None:
        return None

    if from_id == to_id:
        return [{"id": start["id"], "title": start["title"], "url": start["url"]}]

    # parent[child_id] = (parent_id, child_title, child_url)
    parent: dict[int, tuple] = {}
    visited: set[int] = {from_id}
    frontier: list[int] = [from_id]

    for _ in range(max_depth):
        if not frontier:
            break

        edges = (
            ExistingLink.objects
            .filter(
                from_content_item_id__in=frontier,
                to_content_item__is_deleted=False,
            )
            .values(
                "from_content_item_id",
                "to_content_item_id",
                "to_content_item__title",
                "to_content_item__url",
            )
        )

        next_frontier: list[int] = []
        found = False

        for edge in edges:
            child_id = edge["to_content_item_id"]
            if child_id in visited:
                continue
            visited.add(child_id)
            parent[child_id] = (
                edge["from_content_item_id"],
                edge["to_content_item__title"],
                edge["to_content_item__url"],
            )
            if child_id == to_id:
                found = True
                break
            next_frontier.append(child_id)

        if found:
            # Reconstruct path from to_id back to from_id
            path: list[dict] = []
            node_id = to_id
            while node_id in parent:
                p_id, title, url = parent[node_id]
                path.append({"id": node_id, "title": title, "url": url})
                node_id = p_id
            path.append({"id": start["id"], "title": start["title"], "url": start["url"]})
            path.reverse()
            return path

        frontier = next_frontier

    return None
