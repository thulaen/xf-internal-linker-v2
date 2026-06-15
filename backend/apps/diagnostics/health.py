"""Diagnostics health checks: runtime probes, native-kernel benchmarks, and conflict detection."""

import logging
import os
import importlib
import importlib.util
from datetime import timedelta
from time import perf_counter

from asgiref.sync import async_to_sync
from celery import current_app
from django.conf import settings
from django.db import connection
from django.utils import timezone
from django_redis import get_redis_connection

from apps.suggestions.models import Suggestion

from .models import ServiceStatusSnapshot, SystemConflict

logger = logging.getLogger(__name__)

# Native modules with staged Python extension artifacts are tracked here.
# Rust/PyO3 modules now own hot paths, while legacy C++ modules are reported
# only when their loaded artifact proves they are still present.
_NATIVE_RUNTIME_MODULES = (
    # ── Ranking / retrieval core (13) ──
    (
        "scoring",
        "calculate_composite_scores_full_batch",
        "Composite scoring kernel",
        True,
    ),
    (
        "ranking_decision_engine",
        "calculate_composite_scores_full_batch",
        "Ranking decision/governance engine",
        True,
    ),
    ("simsearch", "score_and_topk", "Sentence search kernel", True),
    ("pagerank", "pagerank_step", "PageRank kernel", True),
    ("texttok", "tokenize_text_batch", "Tokenizer kernel", True),
    ("feedrerank", "calculate_mmr_scores_batch", "Slate diversity kernel", False),
    ("l2norm", "normalize_l2_batch", "Embedding normalization kernel", False),
    ("fieldrel", "score_field_tokens", "Field-aware relevance kernel", False),
    ("rareterm", "evaluate_rare_terms", "Rare-term propagation kernel", False),
    ("linkparse", "find_urls", "Link parser kernel", False),
    ("phrasematch", "longest_contiguous_overlap", "Phrase matching kernel", False),
    ("passagesim", "maxsim", "FR-053 Passage-level similarity", False),
    ("quantemb", "opq_encode", "OPQ embedding quantiser", False),
    # ── Anchor analysis kernels (3) ──
    ("anchor_descriptiveness", "damerau_levenshtein", "Anchor descriptiveness scorer", False),
    ("anchor_diversity", "evaluate_batch", "Anchor diversity evaluator", False),
    ("anchor_self_information", "bigram_entropy", "Anchor self-information scorer", False),
    ("generic_anchor_matcher", "build_automaton", "Aho-Corasick anchor matcher", False),
    # ── Probabilistic data structures (4) ──
    ("compressed_bloom", "CompressedBloomFilter", "Compressed Bloom filter", False),
    ("counting_bloom", "CountingBloomFilter", "Counting Bloom filter", False),
    ("count_min_sketch", "CountMinSketch", "Count-Min sketch", False),
    ("papertrail_dedup", "DedupIndex", "Paper-trail MinHash+LSH dedup index", False),
    # ── Indexes and rate limiters (3) ──
    ("ivf_index", "ivf_search", "IVF vector index", False),
    ("lesson_index", "memory_cap_bytes", "Lesson ART index", False),
    ("api_rate_limiter", "RateLimiterRegistry", "API rate limiter", False),
    # ── Advanced graph signals (FR260-265) (1) ──
    ("advanced_graph_signals", "evaluate_batch", "Advanced graph signals kernel (FR260-265)", False),
)


def _result(
    state: str,
    explanation: str,
    next_step: str,
    metadata: dict | None = None,
):
    return state, explanation, next_step, metadata or {}


def _native_runtime_path(origin: str | None) -> str:
    """Classify a loaded native kernel as ``rust`` or ``cpp`` from its artifact filename.

    C++ pybind11 kernels ship an ABI-tagged ``<name>.cpython-*.so``; the Rust/PyO3 build ships
    a bare ``<name>.so``. The source of truth for the Rust set is ``RUST_EXTENSION_NAMES`` in
    ``scripts/ensure_compiled_artifacts.py``; here we read the loaded artifact's origin so the
    label reflects what actually loaded.
    """
    base = os.path.basename(str(origin or ""))
    return "cpp" if ".cpython-" in base else "rust"


def _classify_module_state(
    *,
    importable: bool,
    callable_present: bool,
    critical: bool,
    error: str,
    expected_attr: str,
    origin: str | None = None,
) -> tuple[str, str, bool, str]:
    """Map import/callable probe results to a (state, runtime_path, fallback_active, fallback_reason) tuple.

    A healthy kernel reports the language that actually backs it: ``rust`` for the Rust/PyO3
    build, ``cpp`` for C++ pybind11. There is no ``python`` value — the Python+Rust backend has
    no Python fallback, so a load failure is ``error``.
    """
    if importable and callable_present:
        return "healthy", _native_runtime_path(origin), False, ""
    fallback_reason = error or f"Missing expected callable '{expected_attr}'."
    state = "failed" if critical else "degraded"
    return state, "error", True, fallback_reason


def _native_module_runtime_status() -> list[dict[str, object]]:
    statuses: list[dict[str, object]] = []
    for module_name, expected_attr, label, critical in _NATIVE_RUNTIME_MODULES:
        dotted_name = f"extensions.{module_name}"
        spec = importlib.util.find_spec(dotted_name)
        origin = getattr(spec, "origin", None) if spec else None
        compiled = bool(origin and str(origin).endswith((".so", ".pyd")))
        importable = False
        callable_present = False
        error = ""

        if spec is not None:
            try:
                module = importlib.import_module(dotted_name)
                importable = True
                callable_present = hasattr(module, expected_attr)
            except Exception as exc:
                error = str(exc)
                logger.debug(
                    "Failed to import native extension %s; no Python fallback is available.",
                    dotted_name,
                    exc_info=True,
                )
        else:
            error = "Module spec not found."

        state, runtime_path, fallback_active, fallback_reason = _classify_module_state(
            importable=importable,
            callable_present=callable_present,
            critical=critical,
            error=error,
            expected_attr=expected_attr,
            origin=origin,
        )

        statuses.append(
            {
                "module": module_name,
                "label": label,
                "critical": critical,
                "compiled": compiled,
                "importable": importable,
                "callable_present": callable_present,
                "state": state,
                "runtime_path": runtime_path,
                "fallback_active": fallback_active,
                "fallback_reason": fallback_reason,
                "origin": origin or "",
            }
        )
    return statuses


def _runtime_owner_settings() -> dict[str, str]:
    return {
        "heavy_runtime_owner": getattr(settings, "HEAVY_RUNTIME_OWNER", "celery"),
        "broken_link_scan_owner": getattr(
            settings, "RUNTIME_OWNER_BROKEN_LINK_SCAN", "celery"
        ),
        "graph_sync_owner": getattr(settings, "RUNTIME_OWNER_GRAPH_SYNC", "celery"),
        "import_owner": getattr(settings, "RUNTIME_OWNER_IMPORT", "celery"),
        "pipeline_owner": getattr(settings, "RUNTIME_OWNER_PIPELINE", "celery"),
    }


def _measure_ms(fn, *, repeats: int = 3) -> float:
    best_ms: float | None = None
    for _ in range(repeats):
        started = perf_counter()
        fn()
        elapsed_ms = (perf_counter() - started) * 1000.0
        best_ms = elapsed_ms if best_ms is None else min(best_ms, elapsed_ms)
    return round(best_ms or 0.0, 3)


def _benchmark_scoring() -> dict[str, object]:
    """Benchmark composite scoring kernel against the Rust decision engine."""
    try:
        import numpy as np

        # pylint: disable-next=no-name-in-module,import-error
        from extensions import ranking_decision_engine as ranking_decision_ext
        from apps.pipeline.services import ranker as ranker_service

        np.random.seed(7)
        component_scores = np.random.uniform(-1.0, 1.0, size=(512, 12)).astype(
            np.float32
        )
        weights = np.random.uniform(-0.75, 0.75, size=(12,)).astype(np.float32)
        silo = np.random.uniform(-0.5, 0.5, size=(512,)).astype(np.float32)

        py_ms = _measure_ms(
            lambda: ranker_service._calculate_composite_scores_full_batch_py(
                component_scores, weights, silo
            )
        )
        cpp_ms = _measure_ms(
            lambda: ranking_decision_ext.calculate_composite_scores_full_batch(
                component_scores, weights, silo
            )
        )
        return _benchmark_result(py_ms, cpp_ms)
    except Exception as exc:
        logger.exception("Benchmark for scoring kernel failed")
        return _benchmark_error_result(exc)


def _benchmark_texttok() -> dict[str, object]:
    """Benchmark batched tokeniser (Python text_tokens vs texttok C++ extension)."""
    try:
        # pylint: disable-next=no-name-in-module,import-error
        from extensions import texttok as texttok_ext
        from apps.pipeline.services import text_tokens as text_tokens_service

        texts = [
            f"Internal linking benchmark sentence number {index} with repeated anchor text and topic overlap."
            for index in range(300)
        ]
        stopwords = text_tokens_service.STANDARD_ENGLISH_STOPWORDS

        py_ms = _measure_ms(
            lambda: text_tokens_service.tokenize_text_batch(texts, stopwords)
        )
        cpp_ms = _measure_ms(lambda: texttok_ext.tokenize_text_batch(texts, stopwords))
        return _benchmark_result(py_ms, cpp_ms)
    except Exception as exc:
        logger.exception("Benchmark for texttok kernel failed")
        return _benchmark_error_result(exc)


def _benchmark_simsearch() -> dict[str, object]:
    """Benchmark sentence top-K search (NumPy argpartition vs simsearch C++ extension)."""
    try:
        import numpy as np

        # pylint: disable-next=no-name-in-module,import-error
        from extensions import simsearch as simsearch_ext

        np.random.seed(11)
        destination_embedding = np.random.uniform(-1.0, 1.0, size=(128,)).astype(
            np.float32
        )
        destination_embedding /= np.maximum(
            np.linalg.norm(destination_embedding), 1e-12
        )
        sentence_embeddings = np.random.uniform(-1.0, 1.0, size=(1024, 128)).astype(
            np.float32
        )
        sentence_embeddings /= np.maximum(
            np.linalg.norm(sentence_embeddings, axis=1, keepdims=True), 1e-12
        )
        candidate_rows = list(range(700))
        top_k = 25

        def _py_simsearch() -> tuple[object, object]:
            candidate_matrix = sentence_embeddings[candidate_rows]
            scores = candidate_matrix @ destination_embedding
            k = min(top_k, len(scores))
            top_idx = np.argpartition(scores, -k)[-k:]
            top_idx = top_idx[np.argsort(-scores[top_idx])]
            return top_idx, scores[top_idx]

        py_ms = _measure_ms(_py_simsearch)
        cpp_ms = _measure_ms(
            lambda: simsearch_ext.score_and_topk(
                destination_embedding, sentence_embeddings, candidate_rows, top_k
            )
        )
        return _benchmark_result(py_ms, cpp_ms)
    except Exception as exc:
        logger.exception("Benchmark for simsearch kernel failed")
        return _benchmark_error_result(exc)


def _benchmark_pagerank() -> dict[str, object]:
    """Benchmark single PageRank step (Python weighted_pagerank vs pagerank C++ extension)."""
    try:
        import numpy as np

        # pylint: disable-next=no-name-in-module,import-error
        from extensions import pagerank as pagerank_ext
        from apps.pipeline.services import weighted_pagerank as pagerank_service

        np.random.seed(13)
        node_count = 256
        indptr = np.arange(0, (node_count + 1) * 4, 4, dtype=np.int32)
        indices = np.random.randint(0, node_count, size=node_count * 4, dtype=np.int32)
        data = np.random.uniform(0.01, 1.0, size=node_count * 4).astype(np.float64)
        ranks = np.full(node_count, 1.0 / node_count, dtype=np.float64)
        dangling_mask = np.zeros(node_count, dtype=bool)

        py_ms = _measure_ms(
            lambda: pagerank_service._pagerank_step_py(
                indptr=indptr,
                indices=indices,
                data=data,
                ranks=ranks,
                dangling_mask=dangling_mask,
                damping=0.15,
                node_count=node_count,
            )
        )
        cpp_ms = _measure_ms(
            lambda: pagerank_ext.pagerank_step(
                indptr,
                indices,
                data,
                ranks,
                dangling_mask,
                0.15,
                node_count,
            )
        )
        return _benchmark_result(py_ms, cpp_ms)
    except Exception as exc:
        logger.exception("Benchmark for pagerank kernel failed")
        return _benchmark_error_result(exc)


def _benchmark_feedrerank() -> dict[str, object]:
    """Benchmark MMR slate diversity (Python max-sim vs feedrerank C++ extension)."""
    try:
        import numpy as np

        # pylint: disable-next=no-name-in-module,import-error
        from extensions import feedrerank as feedrerank_ext

        np.random.seed(17)
        relevance = np.random.uniform(0.2, 1.0, size=(256,)).astype(np.float64)
        candidate_embeddings = np.random.uniform(-1.0, 1.0, size=(256, 64)).astype(
            np.float64
        )
        selected_embeddings = np.random.uniform(-1.0, 1.0, size=(12, 64)).astype(
            np.float64
        )

        def _py_feedrerank() -> tuple[object, object]:
            max_sims = np.array(
                [
                    max(
                        float(np.dot(candidate, selected))
                        for selected in selected_embeddings
                    )
                    for candidate in candidate_embeddings
                ],
                dtype=np.float64,
            )
            return (0.65 * relevance) - ((1.0 - 0.65) * max_sims), max_sims

        py_ms = _measure_ms(_py_feedrerank, repeats=2)
        cpp_ms = _measure_ms(
            lambda: feedrerank_ext.calculate_mmr_scores_batch(
                relevance,
                candidate_embeddings,
                selected_embeddings,
                0.65,
            ),
            repeats=2,
        )
        return _benchmark_result(py_ms, cpp_ms)
    except Exception as exc:
        logger.exception("Benchmark for feedrerank kernel failed")
        return _benchmark_error_result(exc)


def _benchmark_native_modules() -> dict[str, dict[str, object]]:
    """Run benchmarks for the 5 critical+core C++ kernels; one entry per module."""
    return {
        "scoring": _benchmark_scoring(),
        "texttok": _benchmark_texttok(),
        "simsearch": _benchmark_simsearch(),
        "pagerank": _benchmark_pagerank(),
        "feedrerank": _benchmark_feedrerank(),
    }


def _benchmark_result(py_ms: float, cpp_ms: float) -> dict[str, object]:
    if cpp_ms <= 0.0 or py_ms <= 0.0:
        return {
            "benchmark_status": "invalid_result",
            "python_ms": py_ms,
            "cpp_ms": cpp_ms,
            "speedup_vs_python": None,
            "proof_available": False,
            "error": "Benchmark produced a non-positive duration.",
        }

    speedup = round(py_ms / cpp_ms, 3)
    if speedup >= 1.1:
        status = "benchmarked_faster"
    elif speedup >= 0.95:
        status = "no_material_speedup"
    else:
        status = "slower_than_python"

    return {
        "benchmark_status": status,
        "python_ms": py_ms,
        "cpp_ms": cpp_ms,
        "speedup_vs_python": speedup,
        "proof_available": True,
        "error": "",
    }


def _benchmark_error_result(exc: Exception) -> dict[str, object]:
    return {
        "benchmark_status": "benchmark_failed",
        "python_ms": None,
        "cpp_ms": None,
        "speedup_vs_python": None,
        "proof_available": False,
        "error": str(exc),
    }


def check_django():
    return _result(
        "healthy",
        "Django answered this health check.",
        "No action needed.",
        {
            "settings_module": os.environ.get("DJANGO_SETTINGS_MODULE", ""),
        },
    )


def check_postgresql():
    try:
        connection.ensure_connection()
        return _result(
            "healthy",
            "PostgreSQL accepted a live connection.",
            "No action needed.",
            {
                "database": connection.settings_dict.get("NAME", ""),
                "host": connection.settings_dict.get("HOST", ""),
            },
        )
    except Exception as exc:
        logger.exception("PostgreSQL health check failed")
        return _result(
            "failed",
            f"PostgreSQL connection failed: {exc}",
            "Check whether PostgreSQL is running and whether the Django database settings are correct.",
        )


def check_redis():
    try:
        conn = get_redis_connection("default")
        conn.ping()
        return _result(
            "healthy",
            "Redis answered a live ping.",
            "No action needed.",
            {
                "redis_url": getattr(settings, "REDIS_URL", ""),
            },
        )
    except Exception as exc:
        logger.exception("Redis health check failed")
        return _result(
            "failed",
            f"Redis connection failed: {exc}",
            "Check whether Redis is running and whether REDIS_URL is correct.",
        )


def check_celery():
    try:
        inspect = current_app.control.inspect()
        ping = inspect.ping() or {}
        worker_count = len(ping)
        if worker_count > 0:
            return _result(
                "healthy",
                f"Celery workers replied to a ping ({worker_count} worker(s)).",
                "No action needed.",
                {
                    "worker_count": worker_count,
                },
            )
        return _result(
            "failed",
            "No Celery workers replied to a ping.",
            "Start the Celery worker process or check the broker connection.",
        )
    except Exception as exc:
        logger.exception("Celery health check failed")
        return _result(
            "failed",
            f"Celery check failed: {exc}",
            "Check Redis connectivity and the Celery worker logs.",
        )


def check_celery_beat():
    if not getattr(settings, "CELERY_BEAT_RUNTIME_ENABLED", True):
        return _result(
            "disabled",
            "Celery Beat is disabled in this runtime shape.",
            "No action needed unless periodic execution stops.",
            {
                "runtime_enabled": False,
            },
        )

    try:
        from django_celery_beat.models import PeriodicTask

        enabled_tasks = PeriodicTask.objects.filter(enabled=True).count()
        if enabled_tasks == 0:
            return _result(
                "not_configured",
                "Celery Beat is installed, but there are no enabled periodic tasks.",
                "Add or enable a periodic task before relying on Celery Beat.",
                {
                    "enabled_periodic_tasks": 0,
                    "proof": "configuration_only",
                },
            )
        return _result(
            "degraded",
            f"Found {enabled_tasks} enabled periodic task(s), but this check does not have a live Beat heartbeat yet.",
            "Add a Beat heartbeat before treating Celery Beat as fully healthy.",
            {
                "enabled_periodic_tasks": enabled_tasks,
                "proof": "configuration_only",
            },
        )
    except ImportError:
        return _result(
            "not_installed",
            "django-celery-beat is not installed.",
            "Install django-celery-beat if scheduled tasks are required.",
        )
    except Exception as exc:
        logger.exception("Celery Beat health check failed")
        return _result(
            "failed",
            f"Celery Beat check failed: {exc}",
            "Check the database and the Celery Beat configuration.",
        )


def check_channels():
    if not hasattr(settings, "CHANNEL_LAYERS"):
        return _result(
            "not_configured",
            "Django Channels is not configured.",
            "Add CHANNEL_LAYERS to the Django settings before relying on WebSocket progress updates.",
        )
    try:
        from channels.layers import get_channel_layer

        channel_layer = get_channel_layer()
        if channel_layer is None:
            return _result(
                "failed",
                "Channel layer could not be created.",
                "Check the Channels backend settings and Redis connection.",
            )
        async_to_sync(channel_layer.group_send)(
            "diagnostics_health_probe",
            {"type": "diagnostics.noop"},
        )
        return _result(
            "healthy",
            "Channel layer accepted a live send operation.",
            "No action needed.",
            {
                "backend": channel_layer.__class__.__name__,
            },
        )
    except Exception as exc:
        logger.exception("Channels health check failed")
        return _result(
            "failed",
            f"Channels check failed: {exc}",
            "Check the Channels backend and Redis connection.",
        )


def check_runtime_lanes():
    owners = _runtime_owner_settings()
    metadata = {
        **owners,
        "runtime_path": "python",
        "fallback_active": False,
        "fallback_reason": "",
    }
    return _result(
        "healthy",
        "All heavy runtime lanes are natively owned by Celery (Python/C++).",
        "No action needed.",
        metadata,
    )


def check_scheduler_lane():
    return _result(
        "healthy",
        "Periodic task scheduling is natively owned by Celery Beat.",
        "No action needed.",
        {
            "runtime_path": "python",
        },
    )


def _merge_benchmark_into_statuses(
    module_statuses: list[dict[str, object]],
    benchmark_results: dict[str, dict[str, object]],
) -> None:
    """Copy benchmark fields onto each module-status dict (in place)."""
    for status in module_statuses:
        benchmark = benchmark_results.get(str(status["module"]), {})
        status["benchmark_status"] = benchmark.get(
            "benchmark_status", "not_benchmarked"
        )
        status["python_ms"] = benchmark.get("python_ms")
        status["cpp_ms"] = benchmark.get("cpp_ms")
        status["speedup_vs_python"] = benchmark.get("speedup_vs_python")
        status["proof_available"] = benchmark.get("proof_available", False)
        status["benchmark_error"] = benchmark.get("error", "")


def _classify_native_modules(
    module_statuses: list[dict[str, object]],
) -> dict[str, object]:
    """Partition module statuses into critical_failures/degraded/healthy and count compiled/importable."""
    critical_failures = [
        status
        for status in module_statuses
        if status["critical"] and status["state"] != "healthy"
    ]
    degraded_modules = [
        status for status in module_statuses if status["state"] == "degraded"
    ]
    healthy_modules = [
        status for status in module_statuses if status["state"] == "healthy"
    ]
    return {
        "critical_failures": critical_failures,
        "degraded_modules": degraded_modules,
        "healthy_modules": healthy_modules,
        "compiled_count": sum(1 for s in module_statuses if s["compiled"]),
        "importable_count": sum(1 for s in module_statuses if s["importable"]),
        "fallback_active": bool(critical_failures or degraded_modules),
    }


def _aggregate_benchmark_results(
    benchmark_results: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Sum py/cpp ms across modules and derive the overall benchmark_status verdict."""
    proof_ready = [
        b
        for b in benchmark_results.values()
        if b.get("proof_available") and isinstance(b.get("cpp_ms"), (int, float))
    ]
    failures = [
        name
        for name, b in benchmark_results.items()
        if b.get("benchmark_status") == "benchmark_failed"
    ]
    overall_cpp_ms = (
        round(sum(float(b["cpp_ms"]) for b in proof_ready), 3) if proof_ready else None
    )
    overall_python_ms = (
        round(sum(float(b["python_ms"]) for b in proof_ready), 3)
        if proof_ready
        else None
    )
    overall_speedup = (
        round((overall_python_ms / overall_cpp_ms), 3)
        if overall_cpp_ms and overall_python_ms
        else None
    )
    if overall_speedup is None:
        benchmark_status = "benchmark_failed"
    elif overall_speedup >= 1.1:
        benchmark_status = "benchmarked_faster"
    elif overall_speedup >= 0.95:
        benchmark_status = "no_material_speedup"
    else:
        benchmark_status = "slower_than_python"
    return {
        "proof_ready": proof_ready,
        "failures": failures,
        "overall_cpp_ms": overall_cpp_ms,
        "overall_python_ms": overall_python_ms,
        "overall_speedup": overall_speedup,
        "benchmark_status": benchmark_status,
    }


def _aggregate_runtime_path(
    module_statuses: list[dict[str, object]],
    classification: dict[str, object],
) -> str:
    """Return the aggregate native runtime label from healthy module statuses."""
    healthy_paths = sorted(
        {
            str(status["runtime_path"])
            for status in module_statuses
            if (
                status.get("state", "healthy") == "healthy"
                and not status.get("fallback_reason")
                and status.get("runtime_path")
            )
        }
    )
    if bool(classification["fallback_active"]):
        return "mixed_error" if healthy_paths else "error"
    if not healthy_paths:
        return "error"
    if len(healthy_paths) == 1:
        return healthy_paths[0]
    return "mixed"


def _native_scoring_metadata(
    module_statuses: list[dict[str, object]],
    classification: dict[str, object],
    aggregate: dict[str, object],
    benchmark_results: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Build the comprehensive metadata payload returned by check_native_scoring."""
    critical_failures = classification["critical_failures"]
    healthy_modules = classification["healthy_modules"]
    fallback_active = bool(classification["fallback_active"])
    runtime_path = _aggregate_runtime_path(module_statuses, classification)
    return {
        "runtime_path": runtime_path,
        "native_scoring_active": not bool(critical_failures),
        "compiled": classification["compiled_count"] == len(module_statuses),
        "importable": classification["importable_count"] == len(module_statuses),
        "safe_to_use": not bool(critical_failures),
        "fallback_active": fallback_active,
        "fallback_reason": "",
        "compiled_module_count": classification["compiled_count"],
        "importable_module_count": classification["importable_count"],
        "healthy_module_count": len(healthy_modules),
        "degraded_module_count": len(classification["degraded_modules"]),
        "critical_failure_count": len(critical_failures),
        "last_benchmark_ms": aggregate["overall_cpp_ms"],
        "python_benchmark_ms": aggregate["overall_python_ms"],
        "speedup_vs_python": aggregate["overall_speedup"],
        "benchmark_status": aggregate["benchmark_status"],
        "benchmarked_module_count": len(aggregate["proof_ready"]),
        "benchmark_failure_count": len(aggregate["failures"]),
        "module_statuses": module_statuses,
        "benchmark_results": benchmark_results,
        "last_error_summary": "; ".join(
            f"{status['module']}: {status['fallback_reason']}"
            for status in module_statuses
            if status["fallback_reason"]
        )[:500],
    }


def _native_scoring_module_failure_result(
    classification: dict[str, object],
    metadata: dict[str, object],
) -> tuple[str, str, str, dict] | None:
    """Return failure/degraded tuple when modules are missing; None when modules are healthy."""
    critical_failures = classification["critical_failures"]
    if critical_failures:
        metadata["fallback_reason"] = (
            "One or more critical native kernels are not available; no Python fallback is available."
        )
        return _result(
            "failed",
            f"The native fast path is not fully safe right now. Critical kernels missing: {', '.join(s['module'] for s in critical_failures)}.",
            "Rebuild the native extensions and restore the missing critical kernels before trusting the path.",
            metadata,
        )
    degraded_modules = classification["degraded_modules"]
    if degraded_modules:
        metadata["fallback_reason"] = (
            "Some optional native kernels are not available; no Python fallback is available."
        )
        return _result(
            "degraded",
            f"Core native scoring is active, but some optional kernels are unavailable: {', '.join(s['module'] for s in degraded_modules)}.",
            "Rebuild the optional native extensions if you want every fast path ready.",
            metadata,
        )
    return None


def _native_scoring_benchmark_result(
    benchmark_status: str,
    metadata: dict[str, object],
) -> tuple[str, str, str, dict] | None:
    """Return degraded tuple when benchmark verdict is unfavourable; None when speed advantage is proven."""
    if benchmark_status == "benchmark_failed":
        metadata["fallback_reason"] = (
            "Benchmarks could not prove the fast path, even though the critical kernels imported."
        )
        return _result(
            "degraded",
            "The native C++ fast path imported successfully, but benchmark proof could not be captured yet.",
            "Check benchmark failures and fix the benchmark harness before trusting speed claims.",
            metadata,
        )
    if benchmark_status in {"no_material_speedup", "slower_than_python"}:
        metadata["fallback_reason"] = (
            "The native path is available, but the benchmark did not show a meaningful speed win over Python."
        )
        return _result(
            "degraded",
            "The native C++ fast path is available, but diagnostics did not measure a strong speed advantage over Python.",
            "Inspect the benchmark details before assuming the native complexity is paying off.",
            metadata,
        )
    return None


def _native_scoring_result(
    classification: dict[str, object],
    aggregate: dict[str, object],
    metadata: dict[str, object],
) -> tuple[str, str, str, dict]:
    """Choose the (state, explanation, next_step, metadata) tuple based on classification + benchmark verdict."""
    module_result = _native_scoring_module_failure_result(classification, metadata)
    if module_result is not None:
        return module_result
    benchmark_result = _native_scoring_benchmark_result(
        str(aggregate["benchmark_status"]), metadata
    )
    if benchmark_result is not None:
        return benchmark_result
    return _result(
        "healthy",
        "All tracked native C++ kernels are importable, and diagnostics measured a real speed advantage over Python.",
        "No action needed.",
        metadata,
    )


def check_native_scoring():
    module_statuses = _native_module_runtime_status()
    benchmark_results = _benchmark_native_modules()
    _merge_benchmark_into_statuses(module_statuses, benchmark_results)
    classification = _classify_native_modules(module_statuses)
    aggregate = _aggregate_benchmark_results(benchmark_results)
    metadata = _native_scoring_metadata(
        module_statuses, classification, aggregate, benchmark_results
    )
    return _native_scoring_result(classification, aggregate, metadata)


def check_slate_diversity_runtime():
    from apps.pipeline.services.slate_diversity import (
        get_slate_diversity_runtime_status,
    )

    runtime = get_slate_diversity_runtime_status()
    metadata = {
        "runtime_path": runtime["path"],
        "cpp_fast_path_active": bool(runtime["available"]),
        "python_fallback_active": not bool(runtime["available"]),
        "fallback_active": not bool(runtime["available"]),
        "safe_to_use": bool(runtime["available"]),
    }

    if runtime["available"]:
        return _result(
            "healthy",
            "FR-015 slate diversity can use the native C++ MMR kernel for the final reranking step.",
            "No action needed.",
            metadata,
        )

    return _result(
        "degraded",
        "FR-015 slate diversity is running on the Python fallback path right now.",
        "Rebuild the native extensions if you want the FR-015 C++ fast path back.",
        {
            **metadata,
            "fallback_reason": runtime["reason"],
        },
    )


def check_embedding_specialist():
    return _result(
        "disabled",
        "No dedicated async embedding specialist is deployed yet; embedding operations are currently handled by standard Celery workers.",
        "Ensure Celery worker memory limits are sufficient for embedding models.",
        {
            "runtime_path": "python",
            "fallback_active": False,
            "fallback_reason": "",
            "safe_to_use": False,
            "embedding_specialist_active": False,
        },
    )


def check_ga4():
    from apps.analytics.models import SearchMetric

    latest_row = SearchMetric.objects.filter(source="ga4").order_by("-date").first()
    if latest_row is None:
        return _result(
            "not_configured",
            "GA4 has no synced telemetry rows yet.",
            "Configure GA4 sync and wait for fresh rows before trusting this signal.",
            {
                "ga4_connected": False,
            },
        )

    is_fresh = latest_row.date >= timezone.now().date() - timedelta(days=7)
    return _result(
        "healthy" if is_fresh else "degraded",
        "GA4 telemetry rows exist."
        if is_fresh
        else "GA4 telemetry rows exist, but they look stale.",
        "No action needed."
        if is_fresh
        else "Run the GA4 sync again before trusting this signal.",
        {
            "ga4_connected": True,
            "latest_ga4_date": latest_row.date.isoformat(),
        },
    )


def check_gsc():
    from apps.analytics.models import SearchMetric

    latest_row = SearchMetric.objects.filter(source="gsc").order_by("-date").first()
    if latest_row is None:
        return _result(
            "not_configured",
            "GSC has no synced telemetry rows yet.",
            "Configure GSC sync and wait for fresh rows before trusting this signal.",
            {
                "gsc_connected": False,
            },
        )

    is_fresh = latest_row.date >= timezone.now().date() - timedelta(days=7)
    return _result(
        "healthy" if is_fresh else "degraded",
        "GSC telemetry rows exist."
        if is_fresh
        else "GSC telemetry rows exist, but they look stale.",
        "No action needed."
        if is_fresh
        else "Run the GSC sync again before trusting this signal.",
        {
            "gsc_connected": True,
            "latest_gsc_date": latest_row.date.isoformat(),
        },
    )


def check_matomo():
    from apps.core.models import AppSetting

    setting_keys = {
        "analytics.matomo_enabled",
        "analytics.matomo_url",
        "analytics.matomo_site_id_xenforo",
        "analytics.matomo_token_auth",
    }
    configured_keys = set(
        AppSetting.objects.filter(
            key__in=setting_keys,
        )
        .exclude(value="")
        .values_list("key", flat=True)
    )
    if configured_keys != setting_keys:
        return _result(
            "not_configured",
            "Matomo is not fully configured in the app settings yet.",
            "Fill in the Matomo settings before expecting telemetry from this dependency.",
            {
                "matomo_connected": False,
            },
        )

    return _result(
        "degraded",
        "Matomo settings exist, but there is no live sync proof in diagnostics yet.",
        "Add the Matomo sync lane and freshness proof before calling this dependency healthy.",
        {
            "matomo_connected": False,
        },
    )


def get_resource_usage():
    metrics = {
        "cpu_percent": "unavailable",
        "ram_usage_mb": "unavailable",
        "disk_usage_percent": "unavailable",
    }
    try:
        import psutil

        metrics["cpu_percent"] = psutil.cpu_percent()
        metrics["ram_usage_mb"] = psutil.virtual_memory().used / (1024 * 1024)
        metrics["disk_usage_percent"] = psutil.disk_usage("/").percent
    except ImportError:
        pass  # psutil is optional; defaults above are returned
    return metrics


def _write_service_snapshot(
    *,
    service: str,
    state: str,
    explanation: str,
    next_step: str,
    metadata: dict,
    checked_at,
) -> None:
    """Persist a service health snapshot, updating only the columns that changed."""
    snapshot, _ = ServiceStatusSnapshot.objects.get_or_create(service_name=service)
    snapshot.state = state
    snapshot.explanation = explanation
    snapshot.next_action_step = next_step
    snapshot.metadata = metadata
    update_fields = ["state", "explanation", "next_action_step", "metadata", "updated_at"]
    if state == "healthy":
        snapshot.last_success = checked_at
        update_fields.append("last_success")
    elif state == "failed":
        snapshot.last_failure = checked_at
        update_fields.append("last_failure")
    snapshot.save(update_fields=update_fields)


def run_health_checks():
    checks = {
        "django": check_django,
        "postgresql": check_postgresql,
        "redis": check_redis,
        "celery_worker": check_celery,
        "celery_beat": check_celery_beat,
        "channels": check_channels,
        "runtime_lanes": check_runtime_lanes,
        "scheduler_lane": check_scheduler_lane,
        "native_scoring": check_native_scoring,
        "slate_diversity_runtime": check_slate_diversity_runtime,
        "embedding_specialist": check_embedding_specialist,
        "ga4": check_ga4,
        "gsc": check_gsc,
        "matomo": check_matomo,
    }

    results = {}
    checked_at = timezone.now()
    for service, check_fn in checks.items():
        state, explanation, next_step, metadata = check_fn()
        _write_service_snapshot(
            service=service,
            state=state,
            explanation=explanation,
            next_step=next_step,
            metadata=metadata,
            checked_at=checked_at,
        )
        results[service] = {
            "state": state,
            "explanation": explanation,
            "next_step": next_step,
            "last_check": checked_at,
            "metadata": metadata,
        }
    return results


def _conflict_analytics_missing() -> list[dict]:
    """Flag missing analytics data when no SearchMetric rows exist yet."""
    from apps.analytics.models import SearchMetric

    if SearchMetric.objects.count() > 0:
        return []
    return [
        {
            "type": "placeholder",
            "title": "Analytics Data Missing",
            "description": "Analytics models exist, but there are no SearchMetric rows yet.",
            "severity": "medium",
            "location": "apps/analytics",
            "why": "The code can read analytics data, but no sync has populated it yet.",
            "next_step": "Run the analytics sync before trusting traffic-based ranking signals.",
        }
    ]


def _conflict_orphaned_suggestions() -> list[dict]:
    """Flag suggestion rows whose destination ContentItem has been deleted."""
    orphaned = Suggestion.objects.filter(destination__isnull=True).count()
    if orphaned == 0:
        return []
    return [
        {
            "type": "drift",
            "title": "Orphaned Suggestions",
            "description": f"Found {orphaned} suggestion row(s) without a destination content item.",
            "severity": "high",
            "location": "apps.suggestions.models.Suggestion",
            "why": "Content was deleted while suggestions were still hanging around.",
            "next_step": "Clean up orphaned suggestions and check the delete flow.",
        }
    ]


def _conflict_native_unhealthy() -> list[dict]:
    """Flag drift when the native fast path is not fully healthy."""
    state, _, _, metadata = check_native_scoring()
    if state == "healthy":
        return []
    return [
        {
            "type": "drift",
            "title": "Native Fast Path Not Fully Healthy",
            "description": "The repo expects Rust or remaining native kernels to be ready, but runtime diagnostics report an unavailable kernel.",
            "severity": "high" if state == "failed" else "medium",
            "location": "backend/apps/diagnostics/health.py",
            "why": "Hot-loop work has a missing native kernel, which can stop the affected path or hide a broken build.",
            "next_step": metadata.get("fallback_reason")
            or "Rebuild native extensions and re-run parity checks.",
        }
    ]


def _conflict_dev_runtime() -> list[dict]:
    """Flag drift when the main Django process is running with development settings."""
    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
    if not settings_module.endswith(".development"):
        return []
    return [
        {
            "type": "drift",
            "title": "Development Runtime Active",
            "description": "The main Django process is running with development settings.",
            "severity": "medium",
            "location": settings_module,
            "why": "Development mode is fine for local work, but it is not a trustworthy runtime shape for a 16 GB production box.",
            "next_step": "Move the main compose runtime onto production settings before calling the stack production-ready.",
        }
    ]


def _conflict_planned_services() -> list[dict]:
    """Flag any planned-only ServiceStatusSnapshot rows for ga4/gsc as roadmap-tracked, not live."""
    out: list[dict] = []
    for service in ("ga4", "gsc"):
        snapshot, _ = ServiceStatusSnapshot.objects.get_or_create(service_name=service)
        if snapshot.state == "planned_only":
            out.append(
                {
                    "type": "mismatch",
                    "title": f"Planned Service: {service}",
                    "description": f"{service} is on the roadmap but does not have a live runtime yet.",
                    "severity": "low",
                    "location": f"diagnostics:{service}",
                    "why": "This entry is roadmap tracking, not proof that the service exists.",
                    "next_step": "Do not treat this row as a live dependency until a real runtime is wired in.",
                }
            )
    return out


def _persist_conflicts(conflicts: list[dict]) -> None:
    """Upsert each conflict into SystemConflict, keyed by title."""
    for conflict in conflicts:
        SystemConflict.objects.get_or_create(
            title=conflict["title"],
            defaults={
                "conflict_type": conflict["type"],
                "description": conflict["description"],
                "severity": conflict["severity"],
                "location": conflict["location"],
                "why": conflict["why"],
                "next_step": conflict["next_step"],
            },
        )


def detect_conflicts():
    conflicts = (
        _conflict_analytics_missing()
        + _conflict_orphaned_suggestions()
        + _conflict_native_unhealthy()
        + _conflict_dev_runtime()
        + _conflict_planned_services()
    )
    _persist_conflicts(conflicts)
    return conflicts


def get_feature_readinessMatrix():
    """
    Returns a list of features (FR-006 to FR-021) and their readiness state.
    """
    features = [
        {"id": "FR-006", "name": "XenForo import", "status": "verified"},
        {"id": "FR-007", "name": "WordPress import", "status": "implemented"},
        {"id": "FR-008", "name": "Phrase relevance", "status": "implemented"},
        {"id": "FR-009", "name": "Learned anchors", "status": "implemented"},
        {"id": "FR-010", "name": "Rare-term propagation", "status": "implemented"},
        {"id": "FR-011", "name": "Field-aware relevance", "status": "implemented"},
        {"id": "FR-012", "name": "Link freshness", "status": "implemented"},
        {"id": "FR-013", "name": "Node affinity", "status": "implemented"},
        {"id": "FR-014", "name": "Global ranking (PageRank)", "status": "implemented"},
        {"id": "FR-015", "name": "3-stage pipeline", "status": "verified"},
        {"id": "FR-016", "name": "GA4 telemetry", "status": "implemented"},
        {"id": "FR-017", "name": "GSC attribution", "status": "implemented"},
        {"id": "FR-018", "name": "Weight tuning", "status": "implemented"},
        {"id": "FR-019", "name": "Alert delivery", "status": "implemented"},
        {"id": "FR-020", "name": "Hot swap", "status": "implemented"},
        {"id": "FR-021", "name": "System health", "status": "implemented"},
    ]
    return features
