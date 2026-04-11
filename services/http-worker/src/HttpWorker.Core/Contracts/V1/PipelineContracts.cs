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

public class ImportContentResult
{
    [JsonPropertyName("items_synced")]
    public int ItemsSynced { get; set; }
    
    [JsonPropertyName("items_updated")]
    public int ItemsUpdated { get; set; }

    [JsonPropertyName("updated_pks")]
    public List<int> UpdatedPks { get; set; } = new();
}

