using System.Text.Json.Serialization;

namespace HttpWorker.Core.Contracts.V1;

public sealed class SitemapCrawlRequest
{
    [JsonPropertyName("sitemap_url")]
    public string SitemapUrl { get; set; } = string.Empty;

    [JsonPropertyName("headers")]
    public Dictionary<string, string>? Headers { get; set; }

    [JsonPropertyName("timeout_seconds")]
    public int TimeoutSeconds { get; set; }

    [JsonPropertyName("max_urls")]
    public int MaxUrls { get; set; }
}

public sealed class SitemapCrawlResponse
{
    [JsonPropertyName("sitemap_url")]
    public string SitemapUrl { get; set; } = string.Empty;

    [JsonPropertyName("discovered_urls")]
    public List<SitemapDiscoveredUrl> DiscoveredUrls { get; set; } = [];

    [JsonPropertyName("total_discovered")]
    public int TotalDiscovered { get; set; }

    [JsonPropertyName("truncated")]
    public bool Truncated { get; set; }
}

public sealed class SitemapDiscoveredUrl
{
    [JsonPropertyName("url")]
    public string Url { get; set; } = string.Empty;

    [JsonPropertyName("lastmod")]
    public string? Lastmod { get; set; }

    [JsonPropertyName("changefreq")]
    public string? Changefreq { get; set; }

    [JsonPropertyName("priority")]
    public double? Priority { get; set; }
}
