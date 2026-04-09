using System.Text.Json.Serialization;

namespace HttpWorker.Core.Contracts.V1;

// ---------------------------------------------------------------------------
// Request / Response for the crawl_session job type
// ---------------------------------------------------------------------------

public sealed class CrawlSessionRequest
{
    [JsonPropertyName("session_id")]
    public string SessionId { get; set; } = string.Empty;

    [JsonPropertyName("site_domain")]
    public string SiteDomain { get; set; } = string.Empty;

    [JsonPropertyName("sitemap_urls")]
    public List<string> SitemapUrls { get; set; } = [];

    [JsonPropertyName("base_url")]
    public string BaseUrl { get; set; } = string.Empty;

    [JsonPropertyName("rate_limit")]
    public int RateLimit { get; set; } = 4;

    [JsonPropertyName("max_depth")]
    public int MaxDepth { get; set; } = 5;

    [JsonPropertyName("timeout_hours")]
    public double TimeoutHours { get; set; } = 2.0;

    [JsonPropertyName("excluded_paths")]
    public List<string> ExcludedPaths { get; set; } = [];

    [JsonPropertyName("resume_frontier_key")]
    public string? ResumeFrontierKey { get; set; }
}

public sealed class CrawlSessionResponse
{
    [JsonPropertyName("session_id")]
    public string SessionId { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("pages_crawled")]
    public int PagesCrawled { get; set; }

    [JsonPropertyName("pages_changed")]
    public int PagesChanged { get; set; }

    [JsonPropertyName("pages_skipped_304")]
    public int PagesSkipped304 { get; set; }

    [JsonPropertyName("new_pages_discovered")]
    public int NewPagesDiscovered { get; set; }

    [JsonPropertyName("broken_links_found")]
    public int BrokenLinksFound { get; set; }

    [JsonPropertyName("bytes_downloaded")]
    public long BytesDownloaded { get; set; }

    [JsonPropertyName("elapsed_seconds")]
    public double ElapsedSeconds { get; set; }

    [JsonPropertyName("frontier_key")]
    public string? FrontierKey { get; set; }

    [JsonPropertyName("error")]
    public string? Error { get; set; }
}

// ---------------------------------------------------------------------------
// Per-page crawl result (written to PostgreSQL in batches)
// ---------------------------------------------------------------------------

public sealed class CrawledPageResult
{
    [JsonPropertyName("url")]
    public string Url { get; set; } = string.Empty;

    [JsonPropertyName("normalized_url")]
    public string NormalizedUrl { get; set; } = string.Empty;

    [JsonPropertyName("http_status")]
    public int HttpStatus { get; set; }

    [JsonPropertyName("response_time_ms")]
    public int ResponseTimeMs { get; set; }

    [JsonPropertyName("content_type")]
    public string ContentType { get; set; } = string.Empty;

    [JsonPropertyName("content_length")]
    public int ContentLength { get; set; }

    // SEO metadata
    [JsonPropertyName("title")]
    public string Title { get; set; } = string.Empty;

    [JsonPropertyName("meta_description")]
    public string MetaDescription { get; set; } = string.Empty;

    [JsonPropertyName("canonical_url")]
    public string CanonicalUrl { get; set; } = string.Empty;

    [JsonPropertyName("robots_meta")]
    public string RobotsMeta { get; set; } = string.Empty;

    [JsonPropertyName("has_viewport")]
    public bool HasViewport { get; set; }

    [JsonPropertyName("h1_text")]
    public string H1Text { get; set; } = string.Empty;

    [JsonPropertyName("h1_count")]
    public int H1Count { get; set; }

    [JsonPropertyName("heading_structure")]
    public List<HeadingInfo> HeadingStructure { get; set; } = [];

    [JsonPropertyName("og_title")]
    public string OgTitle { get; set; } = string.Empty;

    [JsonPropertyName("og_description")]
    public string OgDescription { get; set; } = string.Empty;

    [JsonPropertyName("structured_data_types")]
    public List<string> StructuredDataTypes { get; set; } = [];

    // Content
    [JsonPropertyName("word_count")]
    public int WordCount { get; set; }

    [JsonPropertyName("extracted_text")]
    public string ExtractedText { get; set; } = string.Empty;

    [JsonPropertyName("content_hash")]
    public string ContentHash { get; set; } = string.Empty;

    [JsonPropertyName("content_to_html_ratio")]
    public double ContentToHtmlRatio { get; set; }

    // Images
    [JsonPropertyName("img_total")]
    public int ImgTotal { get; set; }

    [JsonPropertyName("img_missing_alt")]
    public int ImgMissingAlt { get; set; }

    // Links
    [JsonPropertyName("internal_links")]
    public List<CrawledLinkInfo> InternalLinks { get; set; } = [];

    [JsonPropertyName("external_link_count")]
    public int ExternalLinkCount { get; set; }

    [JsonPropertyName("nofollow_link_count")]
    public int NofollowLinkCount { get; set; }

    // Depth + caching
    [JsonPropertyName("crawl_depth")]
    public int CrawlDepth { get; set; }

    [JsonPropertyName("etag")]
    public string Etag { get; set; } = string.Empty;

    [JsonPropertyName("last_modified")]
    public string LastModified { get; set; } = string.Empty;

    [JsonPropertyName("redirect_chain")]
    public List<RedirectHop> RedirectChain { get; set; } = [];
}

public sealed class HeadingInfo
{
    [JsonPropertyName("level")]
    public int Level { get; set; }

    [JsonPropertyName("text")]
    public string Text { get; set; } = string.Empty;
}

public sealed class CrawledLinkInfo
{
    [JsonPropertyName("url")]
    public string Url { get; set; } = string.Empty;

    [JsonPropertyName("anchor_text")]
    public string AnchorText { get; set; } = string.Empty;

    [JsonPropertyName("context")]
    public string Context { get; set; } = "content";

    [JsonPropertyName("is_nofollow")]
    public bool IsNofollow { get; set; }
}

public sealed class RedirectHop
{
    [JsonPropertyName("url")]
    public string Url { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public int Status { get; set; }
}
