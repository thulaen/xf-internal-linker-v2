using System.Text.Json.Serialization;

namespace HttpWorker.Core.Contracts.V1;

public sealed class HttpWorkerTaskSnapshot
{
    [JsonPropertyName("job_type")]
    public string JobType { get; set; } = string.Empty;

    [JsonPropertyName("recorded_at")]
    public DateTimeOffset RecordedAt { get; set; }

    [JsonPropertyName("error")]
    public string? Error { get; set; }

    [JsonPropertyName("retry_count")]
    public int RetryCount { get; set; }

    [JsonPropertyName("duration_ms")]
    public long DurationMs { get; set; }
}

public sealed class HttpWorkerWorkerSnapshot
{
    [JsonPropertyName("instance_id")]
    public string InstanceId { get; set; } = string.Empty;

    [JsonPropertyName("started_at")]
    public DateTimeOffset StartedAt { get; set; }

    [JsonPropertyName("heartbeat_at")]
    public DateTimeOffset HeartbeatAt { get; set; }

    [JsonPropertyName("last_completed")]
    public HttpWorkerTaskSnapshot? LastCompleted { get; set; }

    [JsonPropertyName("last_failed")]
    public HttpWorkerTaskSnapshot? LastFailed { get; set; }

    [JsonPropertyName("retry_count_total")]
    public long RetryCountTotal { get; set; }

    [JsonPropertyName("dead_letter_count")]
    public long DeadLetterCount { get; set; }
}

public sealed class HttpWorkerSchedulerSnapshot
{
    [JsonPropertyName("instance_id")]
    public string InstanceId { get; set; } = string.Empty;

    [JsonPropertyName("started_at")]
    public DateTimeOffset StartedAt { get; set; }

    [JsonPropertyName("heartbeat_at")]
    public DateTimeOffset HeartbeatAt { get; set; }

    [JsonPropertyName("ownership_mode")]
    public string OwnershipMode { get; set; } = "shadow";

    [JsonPropertyName("enabled_periodic_tasks")]
    public int EnabledPeriodicTasks { get; set; }

    [JsonPropertyName("status")]
    public string Status { get; set; } = "disabled";

    [JsonPropertyName("note")]
    public string Note { get; set; } = string.Empty;
}

public sealed class HttpWorkerPerformanceSnapshot
{
    [JsonPropertyName("completed_jobs_tracked")]
    public int CompletedJobsTracked { get; set; }

    [JsonPropertyName("latency_p50_ms")]
    public double? LatencyP50Ms { get; set; }

    [JsonPropertyName("latency_p95_ms")]
    public double? LatencyP95Ms { get; set; }

    [JsonPropertyName("latency_p99_ms")]
    public double? LatencyP99Ms { get; set; }

    [JsonPropertyName("drain_rate_per_minute")]
    public double DrainRatePerMinute { get; set; }
}

public sealed class HttpWorkerStatusResponse
{
    [JsonPropertyName("status")]
    public string Status { get; set; } = "ok";

    [JsonPropertyName("schema_version")]
    public string SchemaVersion { get; set; } = string.Empty;

    [JsonPropertyName("redis_connected")]
    public bool RedisConnected { get; set; }

    [JsonPropertyName("queue_depth")]
    public long QueueDepth { get; set; }

    [JsonPropertyName("worker_online")]
    public bool WorkerOnline { get; set; }

    [JsonPropertyName("worker_heartbeat_age_seconds")]
    public double? WorkerHeartbeatAgeSeconds { get; set; }

    [JsonPropertyName("worker")]
    public HttpWorkerWorkerSnapshot? Worker { get; set; }

    [JsonPropertyName("database_connected")]
    public bool DatabaseConnected { get; set; }

    [JsonPropertyName("scheduler_heartbeat_age_seconds")]
    public double? SchedulerHeartbeatAgeSeconds { get; set; }

    [JsonPropertyName("scheduler")]
    public HttpWorkerSchedulerSnapshot? Scheduler { get; set; }

    [JsonPropertyName("performance")]
    public HttpWorkerPerformanceSnapshot? Performance { get; set; }

    [JsonPropertyName("build_version")]
    public string BuildVersion { get; set; } = string.Empty;

    [JsonPropertyName("service_started_at")]
    public DateTimeOffset ServiceStartedAt { get; set; }
}
