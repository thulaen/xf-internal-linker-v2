"""Slice 1.6 — private searchd client.

Wraps the gRPC contract at services/sidecars/api/searchd.proto. searchd is the
Lucene-equivalent full-text index (Bleve) over AutoIssues, PaperTrail entries,
and snapshots. Callers use it to index documents and run ranked (BM25)
searches instead of SQL substring matches — e.g. read_scoped_lessons can ask
searchd for the most relevant lessons in a touched area.

Mirrors apps.auto_issues._sidecars.schemard_client. Generated Python stubs
live under apps._sidecars_pb.searchd (same build path as every sidecar client).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from apps._sidecars_shared.channel import (
    DEFAULT_CALL_DEADLINE,
    load_service_stubs,
    sidecars_channel,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "searchd"


@dataclass(frozen=True)
class SearchDocumentDTO:
    id: str
    kind: str
    title: str
    body: str
    area: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchHitDTO:
    id: str
    kind: str
    title: str
    score: float
    fragment: str


class SearchdClient:
    """Sync gRPC client for the full-text index."""

    def __init__(self, deadline: float = DEFAULT_CALL_DEADLINE) -> None:
        self._deadline = deadline

    def index(self, documents: list[SearchDocumentDTO]) -> bool:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        request = pb.SearchdIndexRequest(
            documents=[
                pb.SearchdDocument(
                    id=d.id,
                    kind=d.kind,
                    title=d.title,
                    body=d.body,
                    area=d.area,
                    tags=list(d.tags),
                )
                for d in documents
            ]
        )
        with sidecars_channel() as channel:
            stub = grpc_mod.SearchdStub(channel)
            response = stub.Index(request, timeout=self._deadline)
        return bool(response.ok)

    def search(
        self,
        query: str,
        *,
        kind: str = "",
        area: str = "",
        limit: int = 10,
    ) -> list[SearchHitDTO]:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        request = pb.SearchdQueryRequest(
            query=query, kind=kind, area=area, limit=limit
        )
        with sidecars_channel() as channel:
            stub = grpc_mod.SearchdStub(channel)
            response = stub.Search(request, timeout=self._deadline)
        return [
            SearchHitDTO(
                id=hit.id,
                kind=hit.kind,
                title=hit.title,
                score=hit.score,
                fragment=hit.fragment,
            )
            for hit in response.hits
        ]

    def delete(self, ids: list[str]) -> bool:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.SearchdStub(channel)
            response = stub.Delete(
                pb.SearchdDeleteRequest(ids=list(ids)), timeout=self._deadline
            )
        return bool(response.ok)

    def health(self) -> str:
        pb, grpc_mod = load_service_stubs(SERVICE_NAME)
        with sidecars_channel() as channel:
            stub = grpc_mod.SearchdStub(channel)
            response = stub.Health(pb.Empty(), timeout=self._deadline)
        return pb.HealthStatus.Name(response.status)
