import ctypes
import json
import os
from statistics import median
from time import perf_counter

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.content.models import ContentItem, Post, Sentence, ScopeItem
from apps.graph.models import ExistingLink, LinkFreshnessEdge
from apps.graph.services import graph_sync
from apps.suggestions.models import PipelineRun, Suggestion


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
            Post.objects.create(
                content_item=content, raw_bbcode=" ".join(links), clean_text="bench"
            )

        run_times_ms: list[float] = []
        peak_working_set_bytes = 0
        for _ in range(3):
            ExistingLink.objects.all().delete()
            LinkFreshnessEdge.objects.all().delete()
            started = perf_counter()
            refreshed = graph_sync._refresh_existing_links_py()
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            run_times_ms.append(elapsed_ms)
            peak_working_set_bytes = max(
                peak_working_set_bytes, _peak_working_set_bytes()
            )
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
                (source_count * links_per_source)
                / max(median(run_times_ms) / 1000.0, 0.001),
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
        user = get_user_model().objects.create_user(
            username="topo_tester", password="pass"
        )
        self.client.force_authenticate(user=user)

        self.scope = ScopeItem.objects.create(
            scope_id=99, scope_type="node", title="Scope"
        )
        self.src = ContentItem.objects.create(
            content_id=101,
            content_type="thread",
            title="Source",
            scope=self.scope,
            url="https://forum.example.com/threads/source.101",
        )
        self.tgt = ContentItem.objects.create(
            content_id=102,
            content_type="thread",
            title="Target",
            scope=self.scope,
            url="https://forum.example.com/threads/target.102",
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


class GapAnalysisViewTests(APITestCase):
    """FR-036: Suggestion vs. Reality Coverage Gap Analysis."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="gaptest", password="x")
        self.client.force_authenticate(user=self.user)

        self.scope = ScopeItem.objects.create(
            scope_id=99, scope_type="node", title="Scope"
        )
        self.host = ContentItem.objects.create(
            content_id=301,
            content_type="thread",
            title="Host Article",
            scope=self.scope,
            url="https://forum.example.com/host.301",
        )
        self.dest = ContentItem.objects.create(
            content_id=302,
            content_type="thread",
            title="Destination Article",
            scope=self.scope,
            url="https://forum.example.com/dest.302",
        )
        post = Post.objects.create(
            content_item=self.host,
            raw_bbcode="Body",
            clean_text="A relevant sentence.",
        )
        sentence = Sentence.objects.create(
            content_item=self.host,
            post=post,
            text="A relevant sentence.",
            position=0,
            char_count=20,
            start_char=0,
            end_char=20,
            word_position=0,
        )
        run = PipelineRun.objects.create(run_state="completed")
        self.suggestion = Suggestion.objects.create(
            pipeline_run=run,
            destination=self.dest,
            destination_title=self.dest.title,
            host=self.host,
            host_sentence=sentence,
            host_sentence_text=sentence.text,
            anchor_phrase="relevant sentence",
            anchor_start=2,
            anchor_end=19,
            anchor_confidence="strong",
            score_semantic=0.88,
            score_keyword=0.85,
            score_final=0.9,
            status="pending",
        )

    def test_ghost_edge_returned_when_no_existing_link(self):
        response = self.client.get("/api/graph/gap-analysis/?threshold=0.8")
        self.assertEqual(response.status_code, 200)
        ghost_edges = response.data["ghost_edges"]
        self.assertEqual(len(ghost_edges), 1)
        self.assertEqual(ghost_edges[0]["source"], self.host.pk)
        self.assertEqual(ghost_edges[0]["target"], self.dest.pk)
        self.assertAlmostEqual(ghost_edges[0]["score_final"], 0.9, places=2)
        self.assertEqual(response.data["total_ghost_edges"], 1)

    def test_ghost_edge_excluded_when_existing_link_present(self):
        ExistingLink.objects.create(
            from_content_item=self.host,
            to_content_item=self.dest,
            anchor_text="relevant sentence",
        )
        response = self.client.get("/api/graph/gap-analysis/?threshold=0.8")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["ghost_edges"]), 0)
        self.assertEqual(response.data["total_ghost_edges"], 0)

    def test_suggestion_below_threshold_excluded(self):
        response = self.client.get("/api/graph/gap-analysis/?threshold=0.95")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["ghost_edges"]), 0)

    def test_empty_response_when_no_pending_suggestions(self):
        self.suggestion.status = "approved"
        self.suggestion.save()
        response = self.client.get("/api/graph/gap-analysis/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["nodes"], [])
        self.assertEqual(response.data["ghost_edges"], [])
        self.assertEqual(response.data["total_ghost_edges"], 0)

    def test_neglect_score_present_in_nodes(self):
        response = self.client.get("/api/graph/gap-analysis/?threshold=0.8")
        self.assertEqual(response.status_code, 200)
        nodes = response.data["nodes"]
        # The destination should appear with a neglect_score
        dest_node = next((n for n in nodes if n["id"] == self.dest.pk), None)
        self.assertIsNotNone(dest_node)
        self.assertGreater(dest_node["neglect_score"], 0)
        self.assertEqual(dest_node["pending_suggestion_count"], 1)
