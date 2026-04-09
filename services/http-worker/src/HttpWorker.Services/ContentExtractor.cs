using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using AngleSharp;
using AngleSharp.Dom;
using AngleSharp.Html.Dom;
using HttpWorker.Core.Contracts.V1;
using Microsoft.Extensions.Logging;

namespace HttpWorker.Services;

/// <summary>
/// Extracts main content, SEO metadata, and internal links from raw HTML.
///
/// Uses a 2-stage approach:
///   Stage 1 — Semantic tag extraction (primary, covers 95%+ of CMS pages).
///   Stage 2 — CETR text-density fallback (for pages without semantic tags).
///
/// All patent-free.  AngleSharp (MIT licence) provides the DOM parser.
/// </summary>
internal sealed class ContentExtractor
{
    private readonly ILogger<ContentExtractor> _logger;
    private readonly IBrowsingContext _browsingContext;

    // CSS selectors for the main content area, tried in order.
    private static readonly string[] ContentSelectors =
    [
        // XenForo
        ".p-body-content",
        ".p-body-main",
        // WordPress
        ".entry-content",
        "article .post-content",
        // Generic HTML5 semantic
        "article",
        "main",
        "[role='main']",
    ];

    // Elements stripped from the content subtree before text extraction.
    private static readonly string[] StripSelectors =
    [
        "nav", "header", "footer", "aside", "script", "style", "noscript",
        "svg", "iframe", "form",
        ".sidebar", ".widget-area", "#secondary",
        ".p-body-sidebar", ".p-navSticky", ".p-breadcrumbs", ".p-footer",
        ".site-footer", ".site-header",
        ".menu", ".breadcrumb", ".pagination", ".share-buttons",
        ".related-posts", ".author-box", ".comment-list", ".comments-area",
    ];

    // URL path segments that indicate non-content pages.
    private static readonly HashSet<string> DefaultExcludedPaths = new(StringComparer.OrdinalIgnoreCase)
    {
        "/members/", "/login/", "/register/", "/account/",
        "/search/", "/admin.php", "/help/",
    };

    public ContentExtractor(ILogger<ContentExtractor> logger)
    {
        _logger = logger;
        var config = Configuration.Default;
        _browsingContext = BrowsingContext.New(config);
    }

    /// <summary>
    /// Parse HTML and extract all SEO-relevant data for one page.
    /// </summary>
    public async Task<CrawledPageResult> ExtractAsync(
        string html,
        string pageUrl,
        string normalizedUrl,
        int httpStatus,
        int responseTimeMs,
        string contentType,
        string? etag,
        string? lastModified,
        List<RedirectHop> redirectChain,
        string siteDomain,
        int crawlDepth,
        CancellationToken ct)
    {
        var result = new CrawledPageResult
        {
            Url = pageUrl,
            NormalizedUrl = normalizedUrl,
            HttpStatus = httpStatus,
            ResponseTimeMs = responseTimeMs,
            ContentType = contentType,
            ContentLength = Encoding.UTF8.GetByteCount(html),
            CrawlDepth = crawlDepth,
            Etag = etag ?? string.Empty,
            LastModified = lastModified ?? string.Empty,
            RedirectChain = redirectChain,
        };

        using var document = await _browsingContext.OpenAsync(
            req => req.Content(html),
            ct).ConfigureAwait(false);

        // ── SEO metadata ────────────────────────────────────────────
        result.Title = document.QuerySelector("title")?.TextContent?.Trim() ?? string.Empty;
        result.MetaDescription = GetMetaContent(document, "description");
        result.CanonicalUrl = document.QuerySelector("link[rel='canonical']")
            ?.GetAttribute("href") ?? string.Empty;
        result.RobotsMeta = GetMetaContent(document, "robots");
        result.HasViewport = document.QuerySelector("meta[name='viewport']") is not null;

        // Open Graph
        result.OgTitle = GetMetaProperty(document, "og:title");
        result.OgDescription = GetMetaProperty(document, "og:description");

        // Structured data (JSON-LD)
        result.StructuredDataTypes = ExtractStructuredDataTypes(document);

        // Headings
        ExtractHeadings(document, result);

        // Images (count only, no download)
        var images = document.QuerySelectorAll("img");
        result.ImgTotal = images.Length;
        result.ImgMissingAlt = images.Count(img =>
            string.IsNullOrWhiteSpace(img.GetAttribute("alt")));

        // ── Main content extraction (Stage 1 + Stage 2) ─────────────
        var (extractedText, contentNode) = ExtractMainContent(document);
        result.ExtractedText = extractedText;
        result.WordCount = CountWords(extractedText);
        result.ContentHash = ComputeSha256(extractedText);
        result.ContentToHtmlRatio = html.Length > 0
            ? (double)extractedText.Length / html.Length
            : 0.0;

        // ── Links ───────────────────────────────────────────────────
        ExtractLinks(document, contentNode, siteDomain, result);

        return result;
    }

    // =====================================================================
    // Stage 1: Semantic tag extraction
    // =====================================================================
    private (string text, IElement? contentNode) ExtractMainContent(IDocument document)
    {
        // Try semantic selectors in order.
        IElement? contentNode = null;
        foreach (var selector in ContentSelectors)
        {
            contentNode = document.QuerySelector(selector);
            if (contentNode is not null) break;
        }

        if (contentNode is not null)
        {
            // Remove boilerplate from within the content subtree.
            StripBoilerplate(contentNode);
            // Remove high-link-density blocks.
            RemoveHighLinkDensityBlocks(contentNode);
            var text = CleanText(contentNode.TextContent);
            if (text.Length > 50) // Sanity: content must have some substance.
                return (text, contentNode);
        }

        // Stage 2: CETR fallback.
        return (ExtractViaCetr(document), null);
    }

    // =====================================================================
    // Stage 2: CETR text-density fallback
    // =====================================================================
    private string ExtractViaCetr(IDocument document)
    {
        var body = document.Body;
        if (body is null) return string.Empty;

        StripBoilerplate(body);

        var sb = new StringBuilder();
        foreach (var block in body.QuerySelectorAll("p, div, section, td, li, blockquote, dd"))
        {
            var text = block.TextContent?.Trim() ?? string.Empty;
            var tagCount = block.QuerySelectorAll("*").Length + 1;
            double ratio = text.Length > 0
                ? (double)text.Length / (text.Length + tagCount * 5)
                : 0.0;

            // CETR threshold: blocks with ratio > 0.5 are likely content.
            if (ratio > 0.5 && text.Length > 30)
            {
                sb.AppendLine(text);
            }
        }

        return CleanText(sb.ToString());
    }

    // =====================================================================
    // Link extraction
    // =====================================================================
    private void ExtractLinks(
        IDocument document,
        IElement? contentNode,
        string siteDomain,
        CrawledPageResult result)
    {
        var anchors = document.QuerySelectorAll("a[href]");
        var internalLinks = new List<CrawledLinkInfo>();
        int externalCount = 0;
        int nofollowCount = 0;

        foreach (var anchor in anchors)
        {
            var href = anchor.GetAttribute("href");
            if (string.IsNullOrWhiteSpace(href) || href.StartsWith('#') || href.StartsWith("javascript:"))
                continue;

            var rel = anchor.GetAttribute("rel") ?? string.Empty;
            var isNofollow = rel.Contains("nofollow", StringComparison.OrdinalIgnoreCase)
                          || rel.Contains("ugc", StringComparison.OrdinalIgnoreCase);

            if (isNofollow) nofollowCount++;

            // Resolve relative URL.
            string absoluteUrl;
            try
            {
                absoluteUrl = new Uri(new Uri(result.Url), href).AbsoluteUri;
            }
            catch
            {
                continue;
            }

            // Is this internal?
            if (!IsInternalUrl(absoluteUrl, siteDomain))
            {
                externalCount++;
                continue;
            }

            // Skip excluded paths.
            if (IsExcludedPath(absoluteUrl))
                continue;

            // Classify context.
            var context = ClassifyLinkContext(anchor, contentNode);

            internalLinks.Add(new CrawledLinkInfo
            {
                Url = absoluteUrl,
                AnchorText = CleanText(anchor.TextContent).Truncate(500),
                Context = context,
                IsNofollow = isNofollow,
            });
        }

        result.InternalLinks = internalLinks;
        result.ExternalLinkCount = externalCount;
        result.NofollowLinkCount = nofollowCount;
    }

    private static string ClassifyLinkContext(IElement anchor, IElement? contentNode)
    {
        // Walk up the DOM to find a context container.
        var current = anchor.ParentElement;
        while (current is not null)
        {
            var tag = current.TagName.ToLowerInvariant();
            var classes = current.ClassList;

            if (tag == "nav" || classes.Contains("menu") || classes.Contains("navigation"))
                return "nav";
            if (tag == "footer" || classes.Contains("footer") || classes.Contains("site-footer"))
                return "footer";
            if (tag == "aside" || classes.Contains("sidebar") || classes.Contains("widget-area"))
                return "sidebar";
            if (classes.Contains("breadcrumb") || classes.Contains("breadcrumbs"))
                return "breadcrumb";

            current = current.ParentElement;
        }

        // If the anchor is inside the extracted content node, it's content.
        if (contentNode is not null && contentNode.Contains(anchor))
            return "content";

        return "unknown";
    }

    // =====================================================================
    // Helpers
    // =====================================================================

    private static void StripBoilerplate(IElement root)
    {
        foreach (var selector in StripSelectors)
        {
            foreach (var el in root.QuerySelectorAll(selector).ToList())
            {
                el.Remove();
            }
        }
    }

    private static void RemoveHighLinkDensityBlocks(IElement root)
    {
        foreach (var block in root.QuerySelectorAll("div, section, ul, ol").ToList())
        {
            var text = block.TextContent?.Trim() ?? string.Empty;
            if (text.Length < 20) continue;

            var linkText = string.Join(" ",
                block.QuerySelectorAll("a").Select(a => a.TextContent?.Trim() ?? ""));
            double linkDensity = (double)linkText.Length / text.Length;

            if (linkDensity > 0.5)
                block.Remove();
        }
    }

    private static void ExtractHeadings(IDocument document, CrawledPageResult result)
    {
        var headings = document.QuerySelectorAll("h1, h2, h3, h4, h5, h6");
        var structure = new List<HeadingInfo>();
        int h1Count = 0;
        string h1Text = string.Empty;

        foreach (var h in headings)
        {
            int level = int.Parse(h.TagName[1..]);
            var text = CleanText(h.TextContent).Truncate(500);
            structure.Add(new HeadingInfo { Level = level, Text = text });

            if (level == 1)
            {
                h1Count++;
                if (h1Count == 1) h1Text = text;
            }
        }

        result.H1Text = h1Text;
        result.H1Count = h1Count;
        result.HeadingStructure = structure;
    }

    private static List<string> ExtractStructuredDataTypes(IDocument document)
    {
        var types = new List<string>();
        foreach (var script in document.QuerySelectorAll("script[type='application/ld+json']"))
        {
            try
            {
                var json = script.TextContent?.Trim() ?? "";
                using var doc = JsonDocument.Parse(json);
                var root = doc.RootElement;
                if (root.TryGetProperty("@type", out var typeEl))
                {
                    types.Add(typeEl.GetString() ?? "Unknown");
                }
            }
            catch
            {
                // Malformed JSON-LD — skip.
            }
        }
        return types;
    }

    private static string GetMetaContent(IDocument document, string name) =>
        document.QuerySelector($"meta[name='{name}']")?.GetAttribute("content") ?? string.Empty;

    private static string GetMetaProperty(IDocument document, string property) =>
        document.QuerySelector($"meta[property='{property}']")?.GetAttribute("content") ?? string.Empty;

    private static bool IsInternalUrl(string url, string siteDomain)
    {
        try
        {
            var host = new Uri(url).Host.ToLowerInvariant();
            return host == siteDomain.ToLowerInvariant()
                || host.EndsWith("." + siteDomain.ToLowerInvariant());
        }
        catch { return false; }
    }

    private static bool IsExcludedPath(string url)
    {
        try
        {
            var path = new Uri(url).AbsolutePath;
            return DefaultExcludedPaths.Any(exc =>
                path.Contains(exc, StringComparison.OrdinalIgnoreCase));
        }
        catch { return false; }
    }

    private static string CleanText(string? text)
    {
        if (string.IsNullOrWhiteSpace(text)) return string.Empty;
        // Collapse whitespace to single spaces, trim.
        return System.Text.RegularExpressions.Regex
            .Replace(text.Trim(), @"\s+", " ");
    }

    private static int CountWords(string text) =>
        string.IsNullOrWhiteSpace(text)
            ? 0
            : text.Split(' ', StringSplitOptions.RemoveEmptyEntries).Length;

    private static string ComputeSha256(string text)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(text));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}

// Extension method for string truncation.
internal static class StringExtensions
{
    public static string Truncate(this string value, int maxLength) =>
        value.Length <= maxLength ? value : value[..maxLength];
}
