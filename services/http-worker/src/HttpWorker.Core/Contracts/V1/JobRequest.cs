using System.Text.Json;
using System.Text.Json.Serialization;

namespace HttpWorker.Core.Contracts.V1;

public sealed class JobRequest
{
    [JsonPropertyName("schema_version")]
    public string SchemaVersion { get; set; } = string.Empty;

    [JsonPropertyName("job_id")]
    public string JobId { get; set; } = string.Empty;

    [JsonPropertyName("job_type")]
    public string JobType { get; set; } = string.Empty;

    [JsonPropertyName("created_at")]
    public DateTimeOffset CreatedAt { get; set; }

    [JsonPropertyName("payload")]
    public JsonElement Payload { get; set; }
}
