namespace HttpWorker.Services;

public sealed class HttpWorkerOptions
{
    public string SchemaVersion { get; set; } = "v1";
    public RedisOptions Redis { get; set; } = new();
    public HttpOptions Http { get; set; } = new();
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
