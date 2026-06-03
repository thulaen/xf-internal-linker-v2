"""Focused tests for the searchd sidecar client.

Mirrors test_sidecar_clients.py: the generated gRPC stubs are faked and
load_service_stubs / sidecars_channel are patched, so the client's request
mapping and response decoding are exercised without a live sidecar.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.auto_issues._sidecars import searchd_client


class _FakeChannel:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _Request:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class _HealthStatus:
    HEALTH_SERVING = 1

    @staticmethod
    def Name(value: int) -> str:
        return {1: "HEALTH_SERVING"}.get(value, f"H_{value}")


class _SearchdPb:
    SearchdIndexRequest = _Request
    SearchdDocument = _Request
    SearchdQueryRequest = _Request
    SearchdDeleteRequest = _Request
    Empty = _Request
    HealthStatus = _HealthStatus


class _SearchdGrpc:
    last_index = None
    last_query = None

    class SearchdStub:
        def __init__(self, channel) -> None:
            self.channel = channel

        def Index(self, request, timeout):
            _SearchdGrpc.last_index = request
            return SimpleNamespace(ok=True, detail="indexed")

        def Search(self, request, timeout):
            _SearchdGrpc.last_query = request
            return SimpleNamespace(
                hits=[
                    SimpleNamespace(
                        id="autoissue:1", kind="autoissue",
                        title="t", score=1.23, fragment="<mark>hit</mark>",
                    )
                ],
                total=1,
            )

        def Delete(self, request, timeout):
            return SimpleNamespace(ok=True, detail="deleted")

        def Health(self, request, timeout):
            return SimpleNamespace(status=1)


class SearchdClientTests(SimpleTestCase):
    def _patches(self, pb, grpc_mod):
        return (
            mock.patch.object(searchd_client, "load_service_stubs",
                              return_value=(pb, grpc_mod)),
            mock.patch.object(searchd_client, "sidecars_channel",
                              return_value=_FakeChannel()),
        )

    def test_index_builds_document_batch(self) -> None:
        pb, grpc_mod = _SearchdPb(), _SearchdGrpc()
        p1, p2 = self._patches(pb, grpc_mod)
        with p1, p2:
            ok = searchd_client.SearchdClient(deadline=1.0).index([
                searchd_client.SearchDocumentDTO(
                    id="autoissue:1", kind="autoissue", title="t",
                    body="b", area="backend/apps/x",
                )
            ])
        self.assertTrue(ok)
        self.assertEqual(len(grpc_mod.last_index.documents), 1)

    def test_search_maps_hits_to_dtos(self) -> None:
        pb, grpc_mod = _SearchdPb(), _SearchdGrpc()
        p1, p2 = self._patches(pb, grpc_mod)
        with p1, p2:
            hits = searchd_client.SearchdClient(deadline=1.0).search(
                "pipeline", kind="autoissue", area="backend/apps", limit=5
            )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].id, "autoissue:1")
        self.assertAlmostEqual(hits[0].score, 1.23, places=2)
        self.assertEqual(grpc_mod.last_query.kind, "autoissue")
        self.assertEqual(grpc_mod.last_query.area, "backend/apps")

    def test_delete_returns_ok(self) -> None:
        pb, grpc_mod = _SearchdPb(), _SearchdGrpc()
        p1, p2 = self._patches(pb, grpc_mod)
        with p1, p2:
            self.assertTrue(
                searchd_client.SearchdClient(deadline=1.0).delete(["autoissue:1"])
            )

    def test_health_maps_enum_name(self) -> None:
        pb, grpc_mod = _SearchdPb(), _SearchdGrpc()
        p1, p2 = self._patches(pb, grpc_mod)
        with p1, p2:
            self.assertEqual(
                searchd_client.SearchdClient(deadline=1.0).health(), "HEALTH_SERVING"
            )
