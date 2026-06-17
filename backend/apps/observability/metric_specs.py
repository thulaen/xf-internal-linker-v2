from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ObservabilityItem:
    item_id: int
    name: str
    kind: str


@dataclass(frozen=True)
class MetricSpec:
    name: str
    kind: str
    labels: tuple[str, ...] = ()


RESERVED_METRICS: tuple[MetricSpec, ...] = (
    MetricSpec("xf_import_posts_total", "counter", ("source",)),
    MetricSpec("xf_import_failures_total", "counter", ("source", "reason")),
    MetricSpec("xf_import_source_api_latency_seconds", "histogram", ("source",)),
    MetricSpec("xf_import_webhook_events_total", "counter", ("source", "event_type")),
    MetricSpec("xf_cleaning_documents_total", "counter"),
    MetricSpec("xf_cleaning_failures_total", "counter", ("reason",)),
    MetricSpec("xf_cleaning_text_length_chars", "histogram", ("phase",)),
    MetricSpec("xf_sentence_split_sentences_per_doc", "histogram"),
    MetricSpec("xf_sentence_split_bad_sentence_ratio", "gauge"),
    MetricSpec("xf_embedding_jobs_total", "counter", ("model",)),
    MetricSpec("xf_embedding_latency_seconds", "histogram", ("model",)),
    MetricSpec("xf_embedding_model_errors_total", "counter", ("model", "reason")),
    MetricSpec("xf_embedding_retry_count_total", "counter", ("model",)),
    MetricSpec("xf_index_build_seconds", "histogram"),
    MetricSpec("xf_index_size_bytes", "gauge"),
    MetricSpec("xf_index_search_seconds", "histogram"),
    MetricSpec("xf_index_candidate_count", "histogram"),
    MetricSpec("xf_scoring_score", "histogram"),
    MetricSpec("xf_scoring_latency_seconds", "histogram"),
    MetricSpec("xf_scoring_rejected_total", "counter", ("reason",)),
    MetricSpec("xf_ranking_decision_latency_seconds", "histogram", ("path",)),
    MetricSpec("xf_ranking_batch_size", "histogram", ("path",)),
    MetricSpec("xf_ranking_decision_last_batch_size", "gauge", ("path",)),
    MetricSpec("xf_ranking_batches_total", "counter", ("path", "status")),
    MetricSpec("xf_ranking_batch_failures_total", "counter", ("path", "reason")),
    MetricSpec("xf_ranking_batch_timeouts_total", "counter", ("path",)),
    MetricSpec("xf_ranking_signal_raw_score", "histogram", ("signal",)),
    MetricSpec("xf_ranking_signal_contribution", "histogram", ("signal", "direction")),
    MetricSpec("xf_ranking_signal_last_contribution", "gauge", ("signal",)),
    MetricSpec("xf_ranking_score_change_total", "counter", ("driver", "direction")),
    MetricSpec("xf_scoring_near_dup_removed_total", "counter"),
    MetricSpec("xf_suggestions_saved_total", "counter"),
    MetricSpec("xf_suggestions_per_doc", "histogram"),
    MetricSpec("xf_suggestions_confidence", "histogram"),
    MetricSpec("xf_review_pending_count", "gauge"),
    MetricSpec("xf_review_approvals_total", "counter", ("reviewer",)),
    MetricSpec("xf_review_rejections_total", "counter", ("reviewer",)),
    MetricSpec("xf_review_throughput_per_hour", "gauge"),
    MetricSpec("xf_crawl_pages_total", "counter", ("source",)),
    MetricSpec("xf_crawl_failures_total", "counter", ("source", "reason")),
    MetricSpec("xf_crawl_robots_errors_total", "counter", ("source", "kind")),
    MetricSpec("xf_crawl_response_status_total", "counter", ("source", "status_code")),
    MetricSpec("xf_system_cpu_seconds_total", "counter", ("service",)),
    MetricSpec("xf_system_memory_rss_bytes", "gauge", ("service",)),
    MetricSpec("xf_system_disk_usage_bytes", "gauge", ("mount",)),
    MetricSpec("xf_system_disk_capacity_bytes", "gauge", ("mount",)),
    MetricSpec("xf_container_restarts_total", "counter", ("service",)),
    MetricSpec("xf_db_latency_seconds", "histogram", ("operation", "status")),
    MetricSpec("xf_queue_depth", "gauge", ("queue",)),
    MetricSpec("xf_active_series_per_tenant", "gauge", ("tenant_id",)),
    MetricSpec("xf_glitchtip_events_received_total", "counter", ("outcome",)),
    MetricSpec("xf_loki_log_volume_bytes", "gauge", ("service",)),
    MetricSpec("xf_tempo_trace_rate_per_sec", "gauge"),
    MetricSpec("xf_pyroscope_uploads_total", "counter", ("service",)),
    MetricSpec("xf_faro_session_count", "gauge"),
    MetricSpec("xf_module_request_total", "counter", ("module", "status")),
    MetricSpec("xf_module_request_duration_seconds", "histogram", ("module",)),
    MetricSpec("xf_module_api_call_seconds", "histogram", ("from_module", "to_module")),
    MetricSpec("xf_sidecar_health", "gauge", ("service",)),
    MetricSpec("xf_cpp_kernel_calls_total", "counter", ("kernel",)),
    MetricSpec("xf_cpp_kernel_latency_seconds", "histogram", ("kernel",)),
    MetricSpec("xf_cpp_kernel_fallback_total", "counter", ("kernel",)),
    MetricSpec("xf_pg_dead_tuple_ratio", "gauge", ("table",)),
    MetricSpec("xf_pg_index_hit_ratio", "gauge", ("index",)),
    MetricSpec("xf_pg_slow_queries_total", "counter", ("queryid",)),
    MetricSpec("xf_redis_cache_hits_total", "counter", ("namespace",)),
    MetricSpec("xf_redis_cache_misses_total", "counter", ("namespace",)),
    MetricSpec("xf_celery_task_duration_seconds", "histogram", ("task_name", "status")),
    MetricSpec("xf_celery_deadletter_depth", "gauge", ("queue",)),
    MetricSpec("xf_autoissue_created_total", "counter", ("source",)),
    MetricSpec("xf_autoissue_resolved_per_agent_total", "counter", ("agent",)),
    MetricSpec("xf_paper_trail_filed_total", "counter", ("category",)),
    MetricSpec("xf_precommit_hook_duration_seconds", "histogram", ("hook",)),
    MetricSpec("xf_precommit_hook_failures_total", "counter", ("hook",)),
    MetricSpec("xf_test_artefact_disk_bytes", "gauge", ("prefix",)),
    MetricSpec("xf_compiled_store_size_bytes", "gauge"),
    MetricSpec("xf_external_api_rate_budget_remaining", "gauge", ("provider",)),
)


_RESERVED_ITEM_NAMES: tuple[tuple[str, str], ...] = (
    *[(spec.name, spec.kind) for spec in RESERVED_METRICS[:48]],
    ("ImportFailuresHigh", "alert"),
    ("WebhookBacklogGrowing", "alert"),
    ("EmbeddingQueueAgeHigh", "alert"),
    ("FaissSearchLatencyHigh", "alert"),
    ("SuggestionGenerationStopped", "alert"),
    ("DatabaseWriteErrors", "alert"),
    ("DiskSpaceLow", "alert"),
    ("ReviewBacklogTooLarge", "alert"),
    ("xf_active_series_per_tenant", "capability"),
    ("bucket_url_label", "capability"),
    ("MetricCardinalityBudget", "capability"),
    ("ImportRateDropPredicted", "alert"),
    ("EmbeddingLatencyDrift", "alert"),
    ("ReservedMetricStale", "alert"),
    ("ScoreDistributionShift", "alert"),
    ("xf_glitchtip_events_received_total", "metric"),
    ("xf_loki_log_volume_bytes", "metric"),
    ("xf_tempo_trace_rate_per_sec", "metric"),
    ("xf_pyroscope_uploads_total", "metric"),
    ("xf_faro_session_count", "metric"),
    ("xf_module_request_total", "metric"),
    ("xf_module_api_call_seconds", "metric"),
    ("xf_sidecar_health", "metric"),
    ("xf_cpp_kernel_calls_total", "metric"),
    ("xf_pg_dead_tuple_ratio", "metric"),
    ("xf_pg_index_hit_ratio", "metric"),
    ("xf_pg_slow_queries_total", "metric"),
    ("xf_redis_cache_hits_total", "metric"),
    ("xf_celery_task_duration_seconds", "metric"),
    ("xf_celery_deadletter_depth", "metric"),
    ("xf_autoissue_created_total", "metric"),
    ("xf_autoissue_resolved_per_agent_total", "metric"),
    ("xf_paper_trail_filed_total", "metric"),
    ("xf_precommit_hook_duration_seconds", "metric"),
    ("xf_test_artefact_disk_bytes", "metric"),
    ("xf_compiled_store_size_bytes", "metric"),
    ("xf_external_api_rate_budget_remaining", "metric"),
)

RESERVED_OBSERVABILITY_ITEMS: tuple[ObservabilityItem, ...] = tuple(
    ObservabilityItem(index + 1, name, kind)
    for index, (name, kind) in enumerate(_RESERVED_ITEM_NAMES)
)
