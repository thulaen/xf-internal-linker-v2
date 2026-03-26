using System.Text.Json.Serialization;

namespace HttpWorker.Core.Contracts.V1;

public sealed class HealthCheckRequest
{
    [JsonPropertyName("urls")]
    public List<string>? Urls { get; set; }

    [JsonPropertyName("timeout_seconds")]
    public int TimeoutSeconds { get; set; }

    [JsonPropertyName("max_concurrency")]
    public int MaxConcurrency { get; set; }
}

public sealed class HealthCheckResponse
{
    [JsonPropertyName("checked")]
    public List<HealthCheckItem> Checked { get; set; } = [];

    [JsonPropertyName("total_checked")]
    public int TotalChecked { get; set; }

    [JsonPropertyName("total_unreachable")]
    public int TotalUnreachable { get; set; }
}

public sealed class HealthCheckItem
{
    [JsonPropertyName("url")]
    public string Url { get; set; } = string.Empty;

    [JsonPropertyName("reachable")]
    public bool Reachable { get; set; }

    [JsonPropertyName("http_status")]
    public int HttpStatus { get; set; }

    [JsonPropertyName("latency_ms")]
    public long LatencyMs { get; set; }

    [JsonPropertyName("error")]
    public string? Error { get; set; }

    [JsonPropertyName("checked_at")]
    public DateTimeOffset CheckedAt { get; set; }
}
