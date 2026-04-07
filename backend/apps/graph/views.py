"""Graph views — existing-link, broken-link, and graph explorer API endpoints."""

from __future__ import annotations

import csv
import uuid
from datetime import datetime, timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date

from django.http import StreamingHttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import BrokenLinkSerializer, OrphanAuditSerializer


class BrokenLinkViewSet(viewsets.ModelViewSet):
    """
    Link-health endpoints.

    GET   /api/broken-links/
    PATCH /api/broken-links/{broken_link_id}/
    POST  /api/broken-links/scan/
    GET   /api/broken-links/export-csv/
    """

    permission_classes = [IsAuthenticated]
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


def _get_audit_queryset(mode: str = "orphan"):
    """Return the queryset for the orphan/low-authority audit.

    Args:
        mode: ``"orphan"`` returns pages with zero inbound links.
              ``"low_authority"`` returns pages below the 5th percentile PageRank.
    """
    from django.db.models import Count, IntegerField, Value

    from apps.content.models import ContentItem
    from apps.graph.models import ExistingLink

    base = ContentItem.objects.filter(is_deleted=False).select_related("scope")

    if mode == "low_authority":
        total = base.count()
        if total == 0:
            return base.none()
        offset = max(0, int(total * 0.05) - 1)
        threshold_qs = (
            base
            .order_by("march_2026_pagerank_score")
            .values_list("march_2026_pagerank_score", flat=True)[offset:offset + 1]
        )
        threshold_list = list(threshold_qs)
        if not threshold_list:
            return base.none()
        threshold = threshold_list[0]
        return (
            base
            .filter(march_2026_pagerank_score__lte=threshold)
            .annotate(inbound_link_count=Count("incoming_links"))
            .order_by("march_2026_pagerank_score", "id")
        )

    # Default: orphan mode — pages with no inbound links.
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
        base
        .exclude(pk__in=linked_ids)
        .annotate(inbound_link_count=Value(0, output_field=IntegerField()))
        .order_by("march_2026_pagerank_score", "id")
    )


class OrphanArticleListView(ListAPIView):
    """
    GET /api/graph/orphans/?mode=orphan|low_authority

    Returns ContentItems that are structurally weak:
      - ``orphan`` (default): pages with zero inbound internal links.
      - ``low_authority``: pages below the 5th percentile PageRank.
    """

    pagination_class = _OrphanPagination
    permission_classes = [IsAuthenticated]
    serializer_class = OrphanAuditSerializer

    def get_queryset(self):
        mode = self.request.query_params.get("mode", "orphan")
        return _get_audit_queryset(mode)


class OrphanExportCSVView(APIView):
    """
    GET /api/graph/orphans/export-csv/?mode=orphan|low_authority

    Streams the audit list as a CSV download.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> StreamingHttpResponse:
        mode = request.query_params.get("mode", "orphan")
        queryset = _get_audit_queryset(mode)

        class Echo:
            def write(self, value: str) -> str:
                return value

        writer = csv.writer(Echo())

        def _rows():
            yield writer.writerow([
                "id", "title", "url", "scope_title",
                "inbound_link_count", "pagerank_score",
            ])
            for item in queryset.iterator(chunk_size=250):
                yield writer.writerow([
                    item.id,
                    item.title,
                    item.url,
                    item.scope.title if item.scope else "",
                    item.inbound_link_count,
                    item.march_2026_pagerank_score,
                ])

        label = "low-authority" if mode == "low_authority" else "orphan"
        response = StreamingHttpResponse(_rows(), content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="{label}-audit-{datetime.utcnow().strftime("%Y%m%d-%H%M%S")}.csv"'
        )
        return response


class OrphanSuggestView(APIView):
    """
    POST /api/graph/orphans/<pk>/suggest/

    Triggers a pipeline run scoped to a single content item as the destination,
    generating inbound link suggestions for it.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int) -> Response:
        from apps.content.models import ContentItem
        from apps.pipeline.tasks import dispatch_pipeline_run
        from apps.suggestions.models import PipelineRun
        from apps.suggestions.serializers import PipelineRunSerializer

        try:
            content_item = ContentItem.objects.get(pk=pk, is_deleted=False)
        except ContentItem.DoesNotExist:
            return Response(
                {"detail": "Content item not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        run = PipelineRun.objects.create(
            rerun_mode="skip_pending",
            host_scope={},
            destination_scope={"content_item_ids": [content_item.pk]},
        )
        dispatch_pipeline_run(
            run_id=str(run.run_id),
            host_scope=run.host_scope,
            destination_scope=run.destination_scope,
            rerun_mode=run.rerun_mode,
        )
        return Response(
            PipelineRunSerializer(run).data,
            status=status.HTTP_201_CREATED,
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
      ?limit=<int>        Max number of nodes (default 500, max 1000).
                          Nodes are selected by descending PageRank so the most
                          connected articles appear first.
      ?at=YYYY-MM-DD      Return the historical edge set active on that date,
                          sourced from LinkFreshnessEdge instead of ExistingLink.
                          When omitted the current live edges are returned.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        from apps.content.models import ContentItem
        from apps.graph.models import ExistingLink, LinkFreshnessEdge

        try:
            limit = min(int(request.query_params.get("limit", 500)), 1000)
        except (ValueError, TypeError):
            limit = 500

        at_date = None
        at_raw = request.query_params.get("at")
        if at_raw:
            at_date = parse_date(at_raw)

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

        if at_date:
            # Historical edge set: edges active on `at_date` from LinkFreshnessEdge.
            freshness_qs = (
                LinkFreshnessEdge.objects
                .filter(
                    from_content_item_id__in=node_ids,
                    to_content_item_id__in=node_ids,
                    first_seen_at__date__lte=at_date,
                )
                .filter(
                    Q(is_active=True) | Q(last_disappeared_at__date__gte=at_date)
                )
                .values("from_content_item_id", "to_content_item_id")
            )
            links: list[dict] = [
                {
                    "source": row["from_content_item_id"],
                    "target": row["to_content_item_id"],
                    "context": "contextual",
                    "anchor": "",
                    "weight": 1.0,
                }
                for row in freshness_qs
            ]
        else:
            # Current live edges from ExistingLink.
            links_qs = (
                ExistingLink.objects
                .filter(
                    from_content_item_id__in=node_ids,
                    to_content_item_id__in=node_ids,
                )
                .values("from_content_item_id", "to_content_item_id", "context_class", "anchor_text")
            )
            links = [
                {
                    "source": row["from_content_item_id"],
                    "target": row["to_content_item_id"],
                    "context": row["context_class"] or "contextual",
                    "anchor": row["anchor_text"] or "",
                    "weight": 1.0,
                }
                for row in links_qs
            ]

        # ── History: daily created / deleted counts for the last 30 days ──────
        thirty_days_ago = timezone.now() - timedelta(days=30)

        created_qs = (
            LinkFreshnessEdge.objects
            .filter(first_seen_at__gte=thirty_days_ago)
            .annotate(day=TruncDate("first_seen_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        deleted_qs = (
            LinkFreshnessEdge.objects
            .filter(
                last_disappeared_at__isnull=False,
                last_disappeared_at__gte=thirty_days_ago,
            )
            .annotate(day=TruncDate("last_disappeared_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )

        created_map = {r["day"].isoformat(): r["count"] for r in created_qs}
        deleted_map = {r["day"].isoformat(): r["count"] for r in deleted_qs}
        all_days = sorted(set(list(created_map) + list(deleted_map)))
        history = [
            {"date": d, "created": created_map.get(d, 0), "deleted": deleted_map.get(d, 0)}
            for d in all_days
        ]

        # ── Churny nodes: pages with repeated link disappearances ─────────────
        churny_qs = list(
            LinkFreshnessEdge.objects
            .filter(
                last_disappeared_at__isnull=False,
                last_disappeared_at__gte=thirty_days_ago,
            )
            .values("from_content_item_id", "from_content_item__title")
            .annotate(churn_count=Count("id"))
            .filter(churn_count__gte=2)
            .order_by("-churn_count")[:20]
        )
        churny_ids = [r["from_content_item_id"] for r in churny_qs]
        churny_nodes = [
            {"id": r["from_content_item_id"], "title": r["from_content_item__title"], "churn_count": r["churn_count"]}
            for r in churny_qs
        ]

        return Response({"nodes": nodes, "links": links, "history": history, "churny_ids": churny_ids, "churny_nodes": churny_nodes})


class PageRankEquityView(APIView):
    """
    GET /api/graph/pagerank-equity/

    Returns PageRank distribution stats for the authority heatmap (FR-033):
      pr_min, pr_max, total_nodes, concentration_warning, concentration_ratio,
      top_authorities (top 20 pages by PageRank with silo name and degree counts).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        from django.db.models import Count, Max, Min, Sum

        from apps.content.models import ContentItem

        qs = (
            ContentItem.objects
            .filter(is_deleted=False)
            .select_related("scope__silo_group")
        )

        agg = qs.aggregate(
            pr_min=Min("march_2026_pagerank_score"),
            pr_max=Max("march_2026_pagerank_score"),
            pr_total=Sum("march_2026_pagerank_score"),
            total_nodes=Count("id"),
        )

        pr_total = agg["pr_total"] or 1.0  # guard division by zero
        top_5_pct = max(1, int((agg["total_nodes"] or 0) * 0.05))
        top_sum = (
            qs
            .order_by("-march_2026_pagerank_score")[:top_5_pct]
            .aggregate(s=Sum("march_2026_pagerank_score"))["s"]
        ) or 0.0
        ratio = top_sum / pr_total

        top_pages = (
            qs
            .annotate(
                in_degree=Count("incoming_links", distinct=True),
                out_degree=Count("outgoing_links", distinct=True),
            )
            .order_by("-march_2026_pagerank_score")[:20]
        )

        return Response({
            "pr_min": float(agg["pr_min"] or 0.0),
            "pr_max": float(agg["pr_max"] or 0.0),
            "total_nodes": agg["total_nodes"] or 0,
            "concentration_warning": ratio > 0.5,
            "concentration_ratio": round(ratio, 4),
            "top_authorities": [
                {
                    "id": p.id,
                    "title": p.title,
                    "url": p.url,
                    "silo_name": (
                        p.scope.silo_group.name
                        if p.scope and p.scope.silo_group
                        else ""
                    ),
                    "pagerank": float(p.march_2026_pagerank_score or 0.0),
                    "in_degree": p.in_degree,
                    "out_degree": p.out_degree,
                }
                for p in top_pages
            ],
        })


class GapAnalysisView(APIView):
    """
    GET /api/graph/gap-analysis/

    Compares pending AI suggestions against live ExistingLinks to surface
    "ghost edges" — high-confidence suggestions where no real link yet exists.

    Query params:
      ?threshold=<float>   Minimum score_final to include (default 0.8, range 0.5–1.0).
      ?limit=<int>         Max nodes to return (default 300, max 1000).

    Returns:
      {
        "nodes":             [...],   # unique ContentItems involved in ghost edges
        "ghost_edges":       [...],   # pending suggestions with no ExistingLink
        "threshold":         0.8,
        "total_ghost_edges": N,
      }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        from apps.content.models import ContentItem
        from apps.graph.models import ExistingLink
        from apps.suggestions.models import Suggestion

        try:
            threshold = float(request.query_params.get("threshold", 0.8))
            threshold = max(0.5, min(1.0, threshold))
        except (ValueError, TypeError):
            threshold = 0.8

        try:
            limit = min(int(request.query_params.get("limit", 300)), 1000)
        except (ValueError, TypeError):
            limit = 300

        # Step 1: All pending high-confidence suggestions.
        suggestions = list(
            Suggestion.objects
            .filter(status="pending", score_final__gte=threshold)
            .values(
                "suggestion_id",
                "host_id",
                "destination_id",
                "anchor_phrase",
                "score_final",
                "score_semantic",
                "score_keyword",
            )
        )

        if not suggestions:
            return Response({
                "nodes": [],
                "ghost_edges": [],
                "threshold": threshold,
                "total_ghost_edges": 0,
            })

        # Step 2: Build set of existing (host → dest) link pairs.
        host_ids = {s["host_id"] for s in suggestions}
        dest_ids = {s["destination_id"] for s in suggestions}

        existing_pairs: set[tuple[int, int]] = set(
            ExistingLink.objects
            .filter(
                from_content_item_id__in=host_ids,
                to_content_item_id__in=dest_ids,
            )
            .values_list("from_content_item_id", "to_content_item_id")
        )

        # Step 3: Ghost edges = suggestions where no real link exists yet.
        ghost_edges = [
            {
                "source": s["host_id"],
                "target": s["destination_id"],
                "score_final": float(s["score_final"]),
                "anchor_phrase": s["anchor_phrase"] or "",
                "suggestion_id": str(s["suggestion_id"]),
                "score_semantic": float(s["score_semantic"] or 0),
                "score_keyword": float(s["score_keyword"] or 0),
            }
            for s in suggestions
            if (s["host_id"], s["destination_id"]) not in existing_pairs
        ]

        total_ghost_edges = len(ghost_edges)

        # Step 4: Unique node IDs that appear in ghost edges.
        ghost_node_ids: set[int] = set()
        for ge in ghost_edges:
            ghost_node_ids.add(ge["source"])
            ghost_node_ids.add(ge["target"])

        if not ghost_node_ids:
            return Response({
                "nodes": [],
                "ghost_edges": [],
                "threshold": threshold,
                "total_ghost_edges": 0,
            })

        # Step 5: Annotate nodes with their real inbound link count.
        node_rows = list(
            ContentItem.objects
            .filter(pk__in=ghost_node_ids, is_deleted=False)
            .annotate(inbound_count=Count("incoming_links"))
            .values("id", "title", "url", "inbound_count")
        )

        # Step 6: Compute per-destination neglect score.
        # neglect_score = Σ(ghost score_final for this dest) / (inbound_count + 1)
        dest_score_sum: dict[int, float] = {}
        dest_ghost_count: dict[int, int] = {}
        for ge in ghost_edges:
            t = ge["target"]
            dest_score_sum[t] = dest_score_sum.get(t, 0.0) + ge["score_final"]
            dest_ghost_count[t] = dest_ghost_count.get(t, 0) + 1

        nodes = []
        for row in node_rows:
            nid = row["id"]
            inbound = row["inbound_count"]
            neglect = round(dest_score_sum.get(nid, 0.0) / (inbound + 1), 4)
            nodes.append({
                "id": nid,
                "title": row["title"],
                "url": row["url"],
                "neglect_score": neglect,
                "inbound_count": inbound,
                "pending_suggestion_count": dest_ghost_count.get(nid, 0),
            })

        nodes.sort(key=lambda n: n["neglect_score"], reverse=True)
        nodes = nodes[:limit]

        return Response({
            "nodes": nodes,
            "ghost_edges": ghost_edges,
            "threshold": threshold,
            "total_ghost_edges": total_ghost_edges,
        })


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
