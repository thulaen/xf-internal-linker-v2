using System.Text.Json.Serialization;

namespace HttpWorker.Core.Contracts.V1;

public sealed class UrlFetchRequest
{
    [JsonPropertyName("urls")]
    public List<UrlFetchItemRequest>? Urls { get; set; }

    [JsonPropertyName("headers")]
    public Dictionary<string, string>? Headers { get; set; }

    [JsonPropertyName("timeout_seconds")]
    public int TimeoutSeconds { get; set; }

    [JsonPropertyName("max_concurrency")]
    public int MaxConcurrency { get; set; }
}

public sealed class UrlFetchItemRequest
{
    [JsonPropertyName("url")]
    public string Url { get; set; } = string.Empty;

    [JsonPropertyName("label")]
    public string? Label { get; set; }
}

public sealed class UrlFetchResponse
{
    [JsonPropertyName("fetched")]
    public List<UrlFetchResultItem> Fetched { get; set; } = [];

    [JsonPropertyName("total_fetched")]
    public int TotalFetched { get; set; }
}

public sealed class UrlFetchResultItem
{
    [JsonPropertyName("url")]
    public string Url { get; set; } = string.Empty;

    [JsonPropertyName("label")]
    public string? Label { get; set; }

    [JsonPropertyName("http_status")]
    public int HttpStatus { get; set; }

    [JsonPropertyName("body")]
    public string Body { get; set; } = string.Empty;

    [JsonPropertyName("content_type")]
    public string ContentType { get; set; } = string.Empty;

    [JsonPropertyName("error")]
    public string? Error { get; set; }

    [JsonPropertyName("fetched_at")]
    public DateTimeOffset FetchedAt { get; set; }
}
