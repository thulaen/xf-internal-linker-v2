using System.Text.Json.Serialization;

namespace HttpWorker.Core.Contracts.V1;

public class ImportContentRequest
{
    [JsonPropertyName("scope_ids")]
    public List<int> ScopeIds { get; set; } = new();

    [JsonPropertyName("mode")]
    public string Mode { get; set; } = "full";

    [JsonPropertyName("source")]
    public string Source { get; set; } = "api";

    [JsonPropertyName("file_path")]
    public string? FilePath { get; set; }
}

public class RunPipelineRequest
{
    [JsonPropertyName("run_id")]
    public string RunId { get; set; } = string.Empty;

    [JsonPropertyName("host_scope")]
    public Dictionary<string, object> HostScope { get; set; } = new();

    [JsonPropertyName("destination_scope")]
    public Dictionary<string, object> DestinationScope { get; set; } = new();

    [JsonPropertyName("rerun_mode")]
    public string RerunMode { get; set; } = "skip_pending";
}

public class ImportContentResult
{
    [JsonPropertyName("items_synced")]
    public int ItemsSynced { get; set; }
    
    [JsonPropertyName("items_updated")]
    public int ItemsUpdated { get; set; }

    [JsonPropertyName("updated_pks")]
    public List<int> UpdatedPks { get; set; } = new();
}

public class RunPipelineResult
{
    [JsonPropertyName("suggestions_created")]
    public int SuggestionsCreated { get; set; }
    
    [JsonPropertyName("items_in_scope")]
    public int ItemsInScope { get; set; }
    
    [JsonPropertyName("duration_seconds")]
    public double DurationSeconds { get; set; }
}
