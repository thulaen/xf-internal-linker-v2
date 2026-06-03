"""Unit tests for the private clusterd gRPC client request/response mapping.

These exercise the pure helpers (no live socket): URI scheme handling, the
ClusterRequest builder, and the ClusterResponse mapper. The generated stubs are
imported, so this runs in the backend-quality image where grpc is installed.
"""
from django.test import SimpleTestCase

from apps.auto_issues._clusterd_client import (
    ClusterResult,
    _build_request,
    _map_clusters,
    _unix_target,
)


class UnixTargetTests(SimpleTestCase):
    def test_adds_unix_scheme(self):
        self.assertEqual(_unix_target("/var/run/x.sock"), "unix:///var/run/x.sock")

    def test_preserves_existing_scheme(self):
        self.assertEqual(_unix_target("unix:///a.sock"), "unix:///a.sock")


class ClusterResultTests(SimpleTestCase):
    def test_equality_and_coercion(self):
        a = ClusterResult(100, [100, 200])
        b = ClusterResult(100, (100, 200))
        self.assertEqual(a, b)
        self.assertEqual(a.member_ids, [100, 200])

    def test_inequality_on_members(self):
        self.assertNotEqual(ClusterResult(1, [1, 2]), ClusterResult(1, [1, 3]))


class BuildRequestTests(SimpleTestCase):
    def test_maps_items_and_threshold(self):
        req = _build_request([(100, [1, 2, 3]), (200, [4, 5])], 0.8)
        self.assertAlmostEqual(req.threshold, 0.8, places=6)
        self.assertEqual([it.id for it in req.items], [100, 200])
        self.assertEqual(list(req.items[0].features), [1, 2, 3])

    def test_empty_items(self):
        req = _build_request([], 0.75)
        self.assertEqual(len(req.items), 0)


class MapClustersTests(SimpleTestCase):
    def test_maps_response_clusters(self):
        from apps.auto_issues._clusterd_pb2 import api_pb2

        resp = api_pb2.ClusterResponse(
            clusters=[
                api_pb2.Cluster(representative_id=100, member_ids=[100, 200]),
                api_pb2.Cluster(representative_id=300, member_ids=[300]),
            ]
        )
        self.assertEqual(
            _map_clusters(resp),
            [ClusterResult(100, [100, 200]), ClusterResult(300, [300])],
        )
