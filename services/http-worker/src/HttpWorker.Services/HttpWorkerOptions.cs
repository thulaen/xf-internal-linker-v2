namespace HttpWorker.Services;

public sealed class HttpWorkerOptions
{
    public string SchemaVersion { get; set; } = "v1";
    public RedisOptions Redis { get; set; } = new();
    public HttpOptions Http { get; set; } = new();
    public PostgresOptions Postgres { get; set; } = new();
    public SchedulerOptions Scheduler { get; set; } = new();
    public ProgressOptions Progress { get; set; } = new();
    public PipelineOptions Pipeline { get; set; } = new();
}

public sealed class RedisOptions
{
    public string ConnectionString { get; set; } = "redis:6379";
    public string JobQueueKey { get; set; } = "http_worker:jobs";
    public int ResultTtlSeconds { get; set; } = 3600;
    public int DeadLetterTtlSeconds { get; set; } = 86400;
}

public sealed class HttpOptions
{
    public int DefaultTimeoutSeconds { get; set; } = 30;
    public int MaxConcurrency { get; set; } = 100;
    public int MaxBodyBytes { get; set; } = 5242880;
    public int MaxRedirectHops { get; set; } = 3;
}

public sealed class PostgresOptions
{
    public string ConnectionString { get; set; } = string.Empty;
}

public sealed class SchedulerOptions
{
    public bool Enabled { get; set; } = false;
    public string OwnershipMode { get; set; } = "shadow";
    public int PollSeconds { get; set; } = 30;
    public string ControlPlaneBaseUrl { get; set; } = "http://backend:8000";
    public string ControlPlaneToken { get; set; } = string.Empty;
}

public sealed class ProgressOptions
{
    public string StreamPrefix { get; set; } = "runtime:progress";
    public int StreamTtlSeconds { get; set; } = 3600;
    public int MaxLen { get; set; } = 512;
}

public sealed class PipelineOptions
{
    public int PixieWalkCount { get; set; } = 2000;
    public int PixieMaxSteps { get; set; } = 6;
    public float PixieBacktrackProbability { get; set; } = 0.5f;

    // Value Model Weights (Instagram-style)
    public float WeightRelevance { get; set; } = 0.4f;
    public float WeightTraffic { get; set; } = 0.3f;
    public float WeightFreshness { get; set; } = 0.1f;
    public float WeightAuthority { get; set; } = 0.2f;
    public float WeightPenalty { get; set; } = 0.1f;

    public int TrafficLookbackDays { get; set; } = 90;
}
