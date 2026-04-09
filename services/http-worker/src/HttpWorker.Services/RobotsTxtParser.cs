namespace HttpWorker.Services;

/// <summary>
/// Minimal robots.txt parser.  Respects Disallow and Crawl-delay for
/// a specific user-agent.  Caches parsed rules per domain.
///
/// Reference: RFC 9309 (Robots Exclusion Protocol).
/// </summary>
internal sealed class RobotsTxtParser
{
    private readonly Dictionary<string, RobotRules> _cache = new(StringComparer.OrdinalIgnoreCase);
    private const string UserAgentName = "XF-Internal-Linker-Crawler";

    /// <summary>Parse robots.txt content and cache it for the domain.</summary>
    public void Parse(string domain, string robotsTxt)
    {
        var rules = new RobotRules();
        bool inRelevantBlock = false;
        bool inWildcardBlock = false;

        foreach (var rawLine in robotsTxt.Split('\n'))
        {
            var line = rawLine.Trim();
            if (line.StartsWith('#') || string.IsNullOrEmpty(line))
                continue;

            var colonIndex = line.IndexOf(':');
            if (colonIndex < 0) continue;

            var directive = line[..colonIndex].Trim().ToLowerInvariant();
            var value = line[(colonIndex + 1)..].Trim();

            if (directive == "user-agent")
            {
                inRelevantBlock = value.Equals(UserAgentName, StringComparison.OrdinalIgnoreCase)
                    || value == "*";
                inWildcardBlock = value == "*";
            }
            else if (inRelevantBlock || inWildcardBlock)
            {
                switch (directive)
                {
                    case "disallow" when !string.IsNullOrEmpty(value):
                        rules.DisallowedPaths.Add(value);
                        break;
                    case "allow" when !string.IsNullOrEmpty(value):
                        rules.AllowedPaths.Add(value);
                        break;
                    case "crawl-delay" when double.TryParse(value, out var delay):
                        rules.CrawlDelaySeconds = Math.Max(rules.CrawlDelaySeconds, delay);
                        break;
                    case "sitemap" when !string.IsNullOrEmpty(value):
                        rules.SitemapUrls.Add(value);
                        break;
                }
            }
        }

        _cache[domain] = rules;
    }

    /// <summary>Check if a URL path is allowed by robots.txt.</summary>
    public bool IsAllowed(string domain, string urlPath)
    {
        if (!_cache.TryGetValue(domain, out var rules))
            return true; // No robots.txt loaded = allow everything.

        // Check Allow rules first (more specific wins, per RFC 9309).
        foreach (var allowed in rules.AllowedPaths)
        {
            if (urlPath.StartsWith(allowed, StringComparison.OrdinalIgnoreCase))
                return true;
        }

        foreach (var disallowed in rules.DisallowedPaths)
        {
            if (urlPath.StartsWith(disallowed, StringComparison.OrdinalIgnoreCase))
                return false;
        }

        return true;
    }

    /// <summary>Get the crawl delay for a domain (0 if not specified).</summary>
    public double GetCrawlDelay(string domain) =>
        _cache.TryGetValue(domain, out var rules) ? rules.CrawlDelaySeconds : 0;

    /// <summary>Get sitemap URLs discovered in robots.txt.</summary>
    public IReadOnlyList<string> GetSitemapUrls(string domain) =>
        _cache.TryGetValue(domain, out var rules) ? rules.SitemapUrls : [];

    /// <summary>Check if rules have been loaded for a domain.</summary>
    public bool HasRules(string domain) => _cache.ContainsKey(domain);
}

internal sealed class RobotRules
{
    public List<string> DisallowedPaths { get; } = [];
    public List<string> AllowedPaths { get; } = [];
    public List<string> SitemapUrls { get; } = [];
    public double CrawlDelaySeconds { get; set; }
}
