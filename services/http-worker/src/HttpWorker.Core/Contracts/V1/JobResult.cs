using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace HttpWorker.Core.Contracts.V1;

public sealed class JobResult
{
    [JsonPropertyName("schema_version")]
    public string SchemaVersion { get; set; } = string.Empty;

    [JsonPropertyName("job_id")]
    public string JobId { get; set; } = string.Empty;

    [JsonPropertyName("job_type")]
    public string JobType { get; set; } = string.Empty;

    [JsonPropertyName("completed_at")]
    public DateTimeOffset CompletedAt { get; set; }

    [JsonPropertyName("duration_ms")]
    public long DurationMs { get; set; }

    [JsonPropertyName("success")]
    public bool Success { get; set; }

    [JsonPropertyName("error")]
    public string? Error { get; set; }

    [JsonPropertyName("results")]
    public JsonNode? Results { get; set; }
}

public sealed class DeadLetterRecord
{
    [JsonPropertyName("schema_version")]
    public string SchemaVersion { get; set; } = string.Empty;

    [JsonPropertyName("job_id")]
    public string JobId { get; set; } = string.Empty;

    [JsonPropertyName("job_type")]
    public string JobType { get; set; } = string.Empty;

    [JsonPropertyName("failed_at")]
    public DateTimeOffset FailedAt { get; set; }

    [JsonPropertyName("attempt_count")]
    public int AttemptCount { get; set; }

    [JsonPropertyName("duration_ms")]
    public long DurationMs { get; set; }

    [JsonPropertyName("error")]
    public string Error { get; set; } = string.Empty;

    [JsonPropertyName("original_request")]
    public JsonNode? OriginalRequest { get; set; }
}

public sealed class QueueSubmitResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("queued_at")]
    public DateTimeOffset QueuedAt { get; set; }
}

public sealed class PendingJobResponse
{
    [JsonPropertyName("job_id")]
    public string JobId { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;
}
