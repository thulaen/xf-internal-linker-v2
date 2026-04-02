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

public sealed class BrokenLinkScanRequest
{
    [JsonPropertyName("allowed_domains")]
    public List<string> AllowedDomains { get; set; } = [];

    [JsonPropertyName("scan_cap")]
    public int ScanCap { get; set; } = 10000;

    [JsonPropertyName("batch_size")]
    public int BatchSize { get; set; } = 250;

    [JsonPropertyName("user_agent")]
    public string UserAgent { get; set; } = "XF Internal Linker V2 Broken Link Scanner";

    [JsonPropertyName("timeout_seconds")]
    public int TimeoutSeconds { get; set; } = 10;

    [JsonPropertyName("max_concurrency")]
    public int MaxConcurrency { get; set; } = 50;
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

public sealed class BrokenLinkScanResponse
{
    [JsonPropertyName("scanned_urls")]
    public int ScannedUrls { get; set; }

    [JsonPropertyName("flagged_urls")]
    public int FlaggedUrls { get; set; }

    [JsonPropertyName("fixed_urls")]
    public int FixedUrls { get; set; }

    [JsonPropertyName("hit_scan_cap")]
    public bool HitScanCap { get; set; }

    [JsonPropertyName("probe_backend")]
    public string ProbeBackend { get; set; } = "csharp_http_worker";
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
