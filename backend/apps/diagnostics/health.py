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

_NATIVE_RUNTIME_MODULES = (
    # ── Existing core extensions (12) ──
    (
        "scoring",
        "calculate_composite_scores_full_batch",
        "Composite scoring kernel",
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
    # ── FR-051/058/053: Patent-backed ranking signal extensions ──
    ("refcontext", "ref_context_score", "FR-051 Reference context scorer", False),
    ("ngramqual", "ngram_score", "FR-058 N-gram quality scorer", False),
    ("passagesim", "passage_max_sim", "FR-053 Passage-level similarity", False),
    # ── FR-066/067/068: Core meta-algorithm extensions ──
    ("smoothrank", "smoothrank_step", "FR-066 SmoothRank NDCG optimiser", False),
    ("rankagg", "power_iter", "FR-067 Markov rank aggregation", False),
    ("cascade", "stage_score", "FR-068 Cascade re-ranker", False),
    # ── OPT-01 to OPT-06: Initial resource optimisations ──
    ("embpool", "alloc", "OPT-01 Embedding memory pool", False),
    ("vecdeser", "parse_vector", "OPT-02 Fast vector deserialiser", False),
    ("jaccard_avx", "jaccard_similarity", "OPT-03 AVX2 Jaccard kernel", False),
    ("clustuf", "union_find", "OPT-04 Cluster union-find", False),
    ("candfilter", "filter_candidates", "OPT-05 SIMD candidate filter", False),
    ("quantemb", "quantize_int8", "OPT-06 Embedding int8 quantiser", False),
    # ── OPT-07 to OPT-12: Memory allocators ──
    ("slab_alloc", "alloc", "OPT-07 Slab allocator", False),
    ("buddy_alloc", "alloc", "OPT-08 Buddy allocator", False),
    ("cow_buffer", "wrap", "OPT-09 Copy-on-write buffer", False),
    ("obj_recycle", "recycle", "OPT-10 Object recycler", False),
    ("stack_scratch", "alloc", "OPT-11 Stack scratch allocator", False),
    ("compact_heap", "compact", "OPT-12 Compact heap", False),
    # ── OPT-13 to OPT-20: Data structures ──
    ("robin_map", "lookup", "OPT-13 Robin Hood hash map", False),
    ("btree_map", "range_query", "OPT-14 B-tree range map", False),
    ("skip_rank", "insert", "OPT-15 Skip list top-K", False),
    ("trie_prefix", "search", "OPT-16 Patricia trie prefix search", False),
    ("compact_set", "contains", "OPT-17 Compact hash set", False),
    ("bitset_bloom", "check", "OPT-18 Bloom filter", False),
    ("sparse_bitvec", "rank", "OPT-19 Sparse bit vector", False),
    ("ring_queue", "push", "OPT-20 Lock-free ring buffer", False),
    # ── OPT-21 to OPT-27: SIMD / AVX2 vectorised operations ──
    ("simd_cosine", "cosine_sim", "OPT-21 AVX2 cosine similarity", False),
    ("simd_topk", "partial_sort", "OPT-22 AVX2 top-K selection", False),
    ("simd_dotbatch", "dot_batch", "OPT-23 AVX2 batched dot product", False),
    ("simd_hamming", "hamming_dist", "OPT-24 AVX2 Hamming distance", False),
    ("simd_strlen", "bulk_strlen", "OPT-25 SIMD string length", False),
    ("simd_minmax", "reduce", "OPT-26 AVX2 min/max reduction", False),
    ("simd_gather", "gather", "OPT-27 AVX2 gather", False),
    # ── OPT-28 to OPT-34: Compression & encoding ──
    ("varint_enc", "encode", "OPT-28 Varint encoder", False),
    ("delta_enc", "encode", "OPT-29 Delta encoder", False),
    ("dict_enc", "encode", "OPT-30 Dictionary encoder", False),
    ("rle_flags", "encode", "OPT-31 Run-length encoder", False),
    ("fp16_vec", "convert", "OPT-32 Float16 converter", False),
    ("nibble_score", "pack", "OPT-33 4-bit score packer", False),
    ("lz4_block", "compress", "OPT-34 LZ4 block compressor", False),
    # ── OPT-35 to OPT-38: Cache-line-friendly layouts ──
    ("soa_candidate", "to_soa", "OPT-35 Struct-of-arrays layout", False),
    ("padded_vec", "alloc_aligned", "OPT-36 Cache-aligned vectors", False),
    ("hot_cold_split", "split", "OPT-37 Hot/cold field splitter", False),
    ("tile_matrix", "tile_mul", "OPT-38 Cache-tiled matrix ops", False),
    # ── OPT-39 to OPT-43: String optimisation ──
    ("sso_string", "create", "OPT-39 Small-string optimised container", False),
    ("str_intern", "intern", "OPT-40 String interning table", False),
    ("rope_text", "concat", "OPT-41 Rope data structure", False),
    ("suffix_arr", "search", "OPT-42 Suffix array substring search", False),
    ("url_canon", "canonicalize", "OPT-43 URL canonicaliser", False),
    # ── OPT-44 to OPT-47: Serialisation & zero-copy ──
    ("flatvec", "serialize", "OPT-44 FlatBuffers zero-copy", False),
    ("zerocopy_buf", "as_numpy", "OPT-45 Zero-copy buffer protocol", False),
    ("msgpack_fast", "pack", "OPT-46 Fast MessagePack", False),
    ("proto_lite", "encode", "OPT-47 Lightweight protobuf", False),
    # ── OPT-48 to OPT-52: Parallel processing ──
    ("worksteal_pool", "submit", "OPT-48 Work-stealing thread pool", False),
    ("lockfree_map", "insert", "OPT-49 Lock-free sharded map", False),
    ("par_merge", "merge", "OPT-50 Parallel merge sort", False),
    ("rw_spinlock", "read_lock", "OPT-51 Reader-writer spinlock", False),
    ("atomic_counter", "increment", "OPT-52 Cache-aligned atomic counter", False),
    # ── OPT-53 to OPT-57: I/O prefetching ──
    ("async_reader", "read_async", "OPT-53 io_uring async reader", False),
    ("mmap_embed", "open_mmap", "OPT-54 Memory-mapped embeddings", False),
    ("prefetch_hint", "prefetch", "OPT-55 Cache prefetch hints", False),
    ("buffered_write", "flush", "OPT-56 Buffered writer", False),
    ("page_touch", "touch", "OPT-57 Page pre-fault", False),
    # ── OPT-58 to OPT-61: Numerical optimisation ──
    ("fixedpt_score", "to_fixed", "OPT-58 Fixed-point scoring", False),
    ("lut_sigmoid", "sigmoid", "OPT-59 Lookup-table sigmoid", False),
    ("fast_log", "log2", "OPT-60 Fast IEEE754 log2", False),
    ("rsqrt_norm", "rsqrt", "OPT-61 Fast inverse sqrt", False),
    # ── OPT-62 to OPT-65: Index structures ──
    ("radix_tree", "lookup", "OPT-62 Radix tree URL index", False),
    ("bitmap_idx", "query", "OPT-63 Bitmap index filter", False),
    ("sparse_matrix", "spmv", "OPT-64 Sparse CSR matrix-vector", False),
    ("interval_tree", "overlap", "OPT-65 Interval tree query", False),
    # ── OPT-66 to OPT-68: Network / IPC ──
    ("redis_pipe", "execute", "OPT-66 Redis pipeline batcher", False),
    ("pg_batch", "copy_in", "OPT-67 PostgreSQL COPY batcher", False),
    ("ipc_shm", "write", "OPT-68 Shared-memory IPC", False),
    # ── OPT-69 to OPT-70: SQL optimisation ──
    ("prepared_stmt", "execute", "OPT-69 Prepared statement cache", False),
    ("result_codec", "decode", "OPT-70 Binary result decoder", False),
    # ── OPT-71 to OPT-72: Pipeline-specific ──
    ("incr_diff", "has_changed", "OPT-71 Incremental content differ", False),
    ("result_cache", "get", "OPT-72 Two-tier result cache", False),
    # ── META-04 to META-39: Extended meta-algorithm extensions ──
    ("coord_ascent", "optimize", "META-04 Coordinate ascent ranker", False),
    ("cma_es", "optimize", "META-05 CMA-ES weight optimiser", False),
    ("random_search", "search", "META-06 Random search sampler", False),
    ("sim_anneal", "anneal", "META-07 Simulated annealing ranker", False),
    ("diff_evolution", "evolve", "META-08 Differential evolution", False),
    ("quantile_norm", "normalize", "META-09 Quantile score normaliser", False),
    ("sigmoid_temp", "scale", "META-10 Sigmoid temperature scaler", False),
    ("zscore_norm", "normalize", "META-11 Z-score query normaliser", False),
    ("boxcox_tf", "transform", "META-12 Box-Cox transformer", False),
    ("rank_pctl", "normalize", "META-13 Rank percentile normaliser", False),
    ("feat_cross", "cross", "META-14 Pairwise feature crosses", False),
    ("residual_stack", "stack", "META-15 Residual feature stacker", False),
    ("ratio_feat", "generate", "META-16 Ratio feature generator", False),
    ("elastic_reg", "regularize", "META-17 Elastic net regulariser", False),
    ("weight_drop", "ensemble", "META-18 Weight dropout ensemble", False),
    ("maxnorm_clip", "clip", "META-19 Max-norm weight clipper", False),
    ("huber_loss", "loss", "META-20 Huber pairwise loss", False),
    ("focal_loss", "loss", "META-21 Focal ranking loss", False),
    ("hinge_loss", "loss", "META-22 Hinge rank loss", False),
    ("pa_ranker", "update", "META-23 Passive-aggressive ranker", False),
    ("exp_decay", "decay", "META-24 Exponential decay updater", False),
    ("slide_window", "retrain", "META-25 Sliding window retrainer", False),
    ("stack_meta", "blend", "META-26 Stacking meta-learner", False),
    ("bayes_avg", "average", "META-27 Bayesian model averaging", False),
    ("bucket_blend", "blend", "META-28 Bucket-wise blender", False),
    ("bootstrap_ci", "confidence", "META-29 Bootstrap confidence scorer", False),
    ("conformal_band", "predict", "META-30 Conformal prediction bands", False),
    ("winsorize", "clip", "META-31 Winsorize score clipper", False),
    ("iso_forest", "score", "META-32 Isolation forest filter", False),
    ("eq_freq_bin", "bin", "META-33 Equal frequency binner", False),
    ("adam_opt", "step", "META-34 Adam weight optimiser", False),
    ("sgd_mom", "step", "META-35 SGD+momentum optimiser", False),
    ("rmsprop_opt", "step", "META-36 RMSProp weight optimiser", False),
    ("kfold_sel", "select", "META-37 K-fold weight selector", False),
    ("succ_halve", "evaluate", "META-38 Successive halving tuner", False),
    ("qcluster_route", "route", "META-39 Query cluster router", False),
)


def _result(
    state: str,
    explanation: str,
    next_step: str,
    metadata: dict | None = None,
):
    return state, explanation, next_step, metadata or {}


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
        else:
            error = "Module spec not found."

        if importable and callable_present:
            state = "healthy"
            runtime_path = "cpp"
            fallback_active = False
            fallback_reason = ""
        elif critical:
            state = "failed"
            runtime_path = "python"
            fallback_active = True
            fallback_reason = error or f"Missing expected callable '{expected_attr}'."
        else:
            state = "degraded"
            runtime_path = "python"
            fallback_active = True
            fallback_reason = error or f"Missing expected callable '{expected_attr}'."

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


def _benchmark_native_modules() -> dict[str, dict[str, object]]:
    import numpy as np

    benchmark_results: dict[str, dict[str, object]] = {}

    try:
        from extensions import scoring as scoring_ext
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
            lambda: scoring_ext.calculate_composite_scores_full_batch(
                component_scores, weights, silo
            )
        )
        benchmark_results["scoring"] = _benchmark_result(py_ms, cpp_ms)
    except Exception as exc:
        benchmark_results["scoring"] = _benchmark_error_result(exc)

    try:
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
        benchmark_results["texttok"] = _benchmark_result(py_ms, cpp_ms)
    except Exception as exc:
        benchmark_results["texttok"] = _benchmark_error_result(exc)

    try:
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
        benchmark_results["simsearch"] = _benchmark_result(py_ms, cpp_ms)
    except Exception as exc:
        benchmark_results["simsearch"] = _benchmark_error_result(exc)

    try:
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
        benchmark_results["pagerank"] = _benchmark_result(py_ms, cpp_ms)
    except Exception as exc:
        benchmark_results["pagerank"] = _benchmark_error_result(exc)

    try:
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
        benchmark_results["feedrerank"] = _benchmark_result(py_ms, cpp_ms)
    except Exception as exc:
        benchmark_results["feedrerank"] = _benchmark_error_result(exc)

    return benchmark_results


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


def check_native_scoring():
    module_statuses = _native_module_runtime_status()
    benchmark_results = _benchmark_native_modules()
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
    compiled_count = sum(1 for status in module_statuses if status["compiled"])
    importable_count = sum(1 for status in module_statuses if status["importable"])
    fallback_active = bool(critical_failures or degraded_modules)
    proof_ready_benchmarks = [
        benchmark
        for benchmark in benchmark_results.values()
        if benchmark.get("proof_available")
        and isinstance(benchmark.get("cpp_ms"), (int, float))
    ]
    benchmark_failures = [
        module_name
        for module_name, benchmark in benchmark_results.items()
        if benchmark.get("benchmark_status") == "benchmark_failed"
    ]
    overall_cpp_ms = (
        round(
            sum(float(benchmark["cpp_ms"]) for benchmark in proof_ready_benchmarks), 3
        )
        if proof_ready_benchmarks
        else None
    )
    overall_python_ms = (
        round(
            sum(float(benchmark["python_ms"]) for benchmark in proof_ready_benchmarks),
            3,
        )
        if proof_ready_benchmarks
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

    metadata = {
        "runtime_path": "cpp"
        if not fallback_active
        else ("mixed" if healthy_modules else "python"),
        "native_scoring_active": not bool(critical_failures),
        "compiled": compiled_count == len(module_statuses),
        "importable": importable_count == len(module_statuses),
        "safe_to_use": not bool(critical_failures),
        "fallback_active": fallback_active,
        "fallback_reason": "",
        "compiled_module_count": compiled_count,
        "importable_module_count": importable_count,
        "healthy_module_count": len(healthy_modules),
        "degraded_module_count": len(degraded_modules),
        "critical_failure_count": len(critical_failures),
        "last_benchmark_ms": overall_cpp_ms,
        "python_benchmark_ms": overall_python_ms,
        "speedup_vs_python": overall_speedup,
        "benchmark_status": benchmark_status,
        "benchmarked_module_count": len(proof_ready_benchmarks),
        "benchmark_failure_count": len(benchmark_failures),
        "module_statuses": module_statuses,
        "benchmark_results": benchmark_results,
        "last_error_summary": "; ".join(
            f"{status['module']}: {status['fallback_reason']}"
            for status in module_statuses
            if status["fallback_reason"]
        )[:500],
    }

    if critical_failures:
        metadata["fallback_reason"] = (
            "One or more critical C++ kernels are unavailable, so Python fallback is protecting ranking."
        )
        return _result(
            "failed",
            f"The native C++ fast path is not fully safe right now. Critical kernels missing: {', '.join(status['module'] for status in critical_failures)}.",
            "Rebuild the native extensions and restore the missing critical kernels before trusting the fast path.",
            metadata,
        )

    if degraded_modules:
        metadata["fallback_reason"] = (
            "Some optional C++ kernels are unavailable, so mixed C++/Python execution is active."
        )
        return _result(
            "degraded",
            f"Core C++ scoring is active, but some optional kernels are falling back to Python: {', '.join(status['module'] for status in degraded_modules)}.",
            "Rebuild the optional native extensions if you want every fast path back.",
            metadata,
        )

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

    return _result(
        "healthy",
        "All tracked native C++ kernels are importable, and diagnostics measured a real speed advantage over Python.",
        "No action needed.",
        metadata,
    )


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
        snapshot, _ = ServiceStatusSnapshot.objects.get_or_create(service_name=service)
        snapshot.state = state
        snapshot.explanation = explanation
        snapshot.next_action_step = next_step
        snapshot.metadata = metadata
        if state == "healthy":
            snapshot.last_success = checked_at
        elif state == "failed":
            snapshot.last_failure = checked_at
        snapshot.save()
        results[service] = {
            "state": state,
            "explanation": explanation,
            "next_step": next_step,
            "last_check": checked_at,
            "metadata": metadata,
        }
    return results


def detect_conflicts():
    conflicts = []

    from apps.analytics.models import SearchMetric

    if SearchMetric.objects.count() == 0:
        conflicts.append(
            {
                "type": "placeholder",
                "title": "Analytics Data Missing",
                "description": "Analytics models exist, but there are no SearchMetric rows yet.",
                "severity": "medium",
                "location": "apps/analytics",
                "why": "The code can read analytics data, but no sync has populated it yet.",
                "next_step": "Run the analytics sync before trusting traffic-based ranking signals.",
            }
        )

    orphaned_suggestions = Suggestion.objects.filter(destination__isnull=True).count()
    if orphaned_suggestions > 0:
        conflicts.append(
            {
                "type": "drift",
                "title": "Orphaned Suggestions",
                "description": f"Found {orphaned_suggestions} suggestion row(s) without a destination content item.",
                "severity": "high",
                "location": "apps.suggestions.models.Suggestion",
                "why": "Content was deleted while suggestions were still hanging around.",
                "next_step": "Clean up orphaned suggestions and check the delete flow.",
            }
        )

    native_scoring_state, _, _, native_scoring_metadata = check_native_scoring()

    if native_scoring_state != "healthy":
        conflicts.append(
            {
                "type": "drift",
                "title": "C++ Fast Path Not Fully Healthy",
                "description": "The repo expects C++ to be the default hot-path, but native runtime diagnostics report fallback or failure.",
                "severity": "high" if native_scoring_state == "failed" else "medium",
                "location": "backend/apps/diagnostics/health.py",
                "why": "Hot-loop work is falling back to Python in at least part of the runtime, which can reduce speed and hide native regressions.",
                "next_step": native_scoring_metadata.get("fallback_reason")
                or "Rebuild native extensions and re-run parity checks.",
            }
        )

    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
    if settings_module.endswith(".development"):
        conflicts.append(
            {
                "type": "drift",
                "title": "Development Runtime Active",
                "description": "The main Django process is running with development settings.",
                "severity": "medium",
                "location": settings_module,
                "why": "Development mode is fine for local work, but it is not a trustworthy runtime shape for a 16 GB production box.",
                "next_step": "Move the main compose runtime onto production settings before calling the stack production-ready.",
            }
        )

    planned_services = ["ga4", "gsc"]
    for service in planned_services:
        snapshot, _ = ServiceStatusSnapshot.objects.get_or_create(service_name=service)
        if snapshot.state == "planned_only":
            conflicts.append(
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
