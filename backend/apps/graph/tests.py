import ctypes
import json
import os
from statistics import median
from time import perf_counter
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APITestCase

from apps.content.models import ContentItem, Post, ScopeItem
from apps.graph.models import ExistingLink, LinkFreshnessEdge
from apps.graph.services import graph_sync
from apps.graph.services import http_worker_client


class HttpWorkerClientTests(SimpleTestCase):
    @override_settings(
        HTTP_WORKER_ENABLED=True,
        HTTP_WORKER_URL="http://http-worker-api:8080/api/v1/status",
    )
    @patch("apps.graph.services.http_worker_client.request.urlopen")
    def test_client_strips_status_suffix_from_base_url(self, mock_urlopen):
        response = MagicMock()
        response.getcode.return_value = 200
        response.read.return_value = b'{"checked": []}'
        mock_urlopen.return_value.__enter__.return_value = response

        http_worker_client.check_health(["https://example.com/health"])

        outgoing_request = mock_urlopen.call_args.args[0]
        self.assertEqual(
            outgoing_request.full_url,
            "http://http-worker-api:8080/api/v1/health/check",
        )

    @override_settings(
        HTTP_WORKER_ENABLED=True,
        HTTP_WORKER_URL="http://http-worker-api:8080/api/v1/status",
    )
    @patch("apps.graph.services.http_worker_client.request.urlopen")
    def test_graph_sync_client_uses_graph_sync_endpoint(self, mock_urlopen):
        response = MagicMock()
        response.getcode.return_value = 200
        response.read.return_value = b'{"active_links": 3}'
        mock_urlopen.return_value.__enter__.return_value = response

        http_worker_client.sync_graph_content(
            content_item_pk=11,
            content_id=77,
            content_type="thread",
            raw_bbcode="[URL=https://example.com/threads/demo.2/]demo[/URL]",
            forum_domains=["example.com"],
        )

        outgoing_request = mock_urlopen.call_args.args[0]
        self.assertEqual(
            outgoing_request.full_url,
            "http://http-worker-api:8080/api/v1/graph-sync/content",
        )


class GraphSyncDispatchTests(TestCase):
    def setUp(self):
        self.scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Scope")
        self.content = ContentItem.objects.create(
            content_id=10,
            content_type="thread",
            title="Host",
            scope=self.scope,
            url="https://forum.example.com/threads/host.10",
        )

    @override_settings(HEAVY_RUNTIME_OWNER="celery", RUNTIME_OWNER_GRAPH_SYNC="csharp")
    @patch("apps.graph.services.graph_sync._sync_existing_links_via_http_worker", return_value=4)
    @patch("apps.graph.services.graph_sync._sync_existing_links_py")
    def test_sync_existing_links_for_content_item_routes_to_csharp_owner(
        self,
        py_mock,
        csharp_mock,
    ):
        result = graph_sync.sync_existing_links_for_content_item(
            self.content,
            "[URL=https://forum.example.com/threads/target.2/]Target[/URL]",
        )

        self.assertEqual(result, 4)
        csharp_mock.assert_called_once()
        py_mock.assert_not_called()

    @override_settings(HEAVY_RUNTIME_OWNER="celery", RUNTIME_OWNER_GRAPH_SYNC="celery")
    @patch("apps.graph.services.graph_sync._sync_existing_links_py", return_value=2)
    @patch("apps.graph.services.graph_sync._sync_existing_links_via_http_worker")
    def test_sync_existing_links_for_content_item_keeps_python_reference_when_owner_is_celery(
        self,
        csharp_mock,
        py_mock,
    ):
        result = graph_sync.sync_existing_links_for_content_item(
            self.content,
            "[URL=https://forum.example.com/threads/target.2/]Target[/URL]",
        )

        self.assertEqual(result, 2)
        py_mock.assert_called_once()
        csharp_mock.assert_not_called()

    @override_settings(HEAVY_RUNTIME_OWNER="celery", RUNTIME_OWNER_GRAPH_SYNC="csharp")
    @patch("apps.graph.services.graph_sync._refresh_existing_links_via_http_worker", return_value=9)
    @patch("apps.graph.services.graph_sync._refresh_existing_links_py")
    def test_refresh_existing_links_routes_to_csharp_owner(self, py_mock, csharp_mock):
        result = graph_sync.refresh_existing_links()

        self.assertEqual(result, 9)
        csharp_mock.assert_called_once()
        py_mock.assert_not_called()


class GraphSyncPythonBenchmarkTests(TestCase):
    def test_reports_benchmark_metrics_for_python_graph_sync_reference(self):
        if os.environ.get("XF_RUN_BENCHMARKS") != "1":
            return

        scope = ScopeItem.objects.create(scope_id=1, scope_type="node", title="Scope")
        source_count = 250
        links_per_source = 4

        for destination_id in range(1, source_count * links_per_source + 1):
            ContentItem.objects.create(
                content_id=destination_id,
                content_type="thread",
                title=f"Destination {destination_id}",
                scope=scope,
                url=f"https://forum.example.com/threads/target.{destination_id}",
            )

        for source_index in range(1, source_count + 1):
            content = ContentItem.objects.create(
                content_id=10_000 + source_index,
                content_type="thread",
                title=f"Source {source_index}",
                scope=scope,
                url=f"https://forum.example.com/threads/source.{source_index}",
            )
            links = []
            for offset in range(links_per_source):
                destination_id = ((source_index - 1) * links_per_source) + offset + 1
                links.append(
                    f"[URL=https://forum.example.com/threads/target.{destination_id}/]Target {destination_id}[/URL]"
                )
            Post.objects.create(content_item=content, raw_bbcode=" ".join(links), clean_text="bench")

        run_times_ms: list[float] = []
        peak_working_set_bytes = 0
        for _ in range(3):
            ExistingLink.objects.all().delete()
            LinkFreshnessEdge.objects.all().delete()
            started = perf_counter()
            refreshed = graph_sync._refresh_existing_links_py()
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            run_times_ms.append(elapsed_ms)
            peak_working_set_bytes = max(peak_working_set_bytes, _peak_working_set_bytes())
            self.assertEqual(refreshed, source_count)

        payload = {
            "lane": "graph_sync",
            "owner": "python_reference",
            "dataset_sources": source_count,
            "links_per_source": links_per_source,
            "wall_time_ms_runs": run_times_ms,
            "median_wall_time_ms": median(run_times_ms),
            "peak_working_set_bytes": peak_working_set_bytes,
            "throughput_links_per_second": round(
                (source_count * links_per_source) / max(median(run_times_ms) / 1000.0, 0.001),
                2,
            ),
        }
        print(f"GRAPH_SYNC_PYTHON_BENCHMARK_JSON:{json.dumps(payload)}")


def _peak_working_set_bytes() -> int:
    if os.name == "nt":
        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_uint32),
                ("PageFaultCount", ctypes.c_uint32),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        psapi = ctypes.WinDLL("psapi")
        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        ok = psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
        if ok:
            return max(int(counters.PeakWorkingSetSize), int(counters.WorkingSetSize))
        return 0

    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        peak = int(usage.ru_maxrss)
        return peak if peak > 10_000_000 else peak * 1024
    except Exception:
        return 0


class GraphTopologyViewTests(APITestCase):
    """FR-034: topology edges must include the 'anchor' field."""

    def setUp(self):
        user = get_user_model().objects.create_user(username="topo_tester", password="pass")
        self.client.force_authenticate(user=user)

        self.scope = ScopeItem.objects.create(scope_id=99, scope_type="node", title="Scope")
        self.src = ContentItem.objects.create(
            content_id=101, content_type="thread", title="Source",
            scope=self.scope, url="https://forum.example.com/threads/source.101",
        )
        self.tgt = ContentItem.objects.create(
            content_id=102, content_type="thread", title="Target",
            scope=self.scope, url="https://forum.example.com/threads/target.102",
        )
        from apps.graph.models import ExistingLink
        ExistingLink.objects.create(
            from_content_item=self.src,
            to_content_item=self.tgt,
            anchor_text="click here",
            context_class="contextual",
        )

    def test_topology_edges_include_anchor_field(self):
        response = self.client.get("/api/graph/topology/")
        self.assertEqual(response.status_code, 200)
        links = response.data["links"]
        self.assertGreater(len(links), 0)
        edge = links[0]
        self.assertIn("anchor", edge, "topology edge must expose anchor field (FR-034)")
        self.assertEqual(edge["anchor"], "click here")

    def test_topology_edges_include_context_field(self):
        response = self.client.get("/api/graph/topology/")
        self.assertEqual(response.status_code, 200)
        edge = response.data["links"][0]
        self.assertIn("context", edge)
        self.assertEqual(edge["context"], "contextual")
