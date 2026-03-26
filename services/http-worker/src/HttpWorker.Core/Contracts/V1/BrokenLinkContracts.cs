using System.Text.Json.Serialization;

namespace HttpWorker.Core.Contracts.V1;

public sealed class BrokenLinkCheckRequest
{
    [JsonPropertyName("urls")]
    public List<BrokenLinkUrlRequest>? Urls { get; set; }

    [JsonPropertyName("user_agent")]
    public string? UserAgent { get; set; }

    [JsonPropertyName("timeout_seconds")]
    public int TimeoutSeconds { get; set; }

    [JsonPropertyName("max_concurrency")]
    public int MaxConcurrency { get; set; }
}

public sealed class BrokenLinkUrlRequest
{
    [JsonPropertyName("url")]
    public string Url { get; set; } = string.Empty;

    [JsonPropertyName("source_content_id")]
    public int SourceContentId { get; set; }
}

public sealed class BrokenLinkCheckResponse
{
    [JsonPropertyName("checked")]
    public List<BrokenLinkCheckItem> Checked { get; set; } = [];

    [JsonPropertyName("total_checked")]
    public int TotalChecked { get; set; }

    [JsonPropertyName("total_flagged")]
    public int TotalFlagged { get; set; }
}

public sealed class BrokenLinkCheckItem
{
    [JsonPropertyName("url")]
    public string Url { get; set; } = string.Empty;

    [JsonPropertyName("source_content_id")]
    public int SourceContentId { get; set; }

    [JsonPropertyName("http_status")]
    public int HttpStatus { get; set; }

    [JsonPropertyName("redirect_url")]
    public string RedirectUrl { get; set; } = string.Empty;

    [JsonPropertyName("error")]
    public string? Error { get; set; }

    [JsonPropertyName("checked_at")]
    public DateTimeOffset CheckedAt { get; set; }
}
