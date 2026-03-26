using System.Xml.Linq;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Options;

namespace HttpWorker.Services;

public sealed class SitemapService(
    IHttpClientFactory httpClientFactory,
    IOptions<HttpWorkerOptions> options) : ISitemapService
{
    private const int ChildFetchCap = 100;
    private readonly HttpWorkerOptions _options = options.Value;
    private readonly HttpRequestSupport _http = new(httpClientFactory, options);

    public async Task<SitemapCrawlResponse> CrawlAsync(SitemapCrawlRequest request, CancellationToken cancellationToken)
    {
        ValidateRequest(request);

        var discovered = new Dictionary<string, SitemapDiscoveredUrl>(StringComparer.OrdinalIgnoreCase);
        var visitedSitemaps = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var childFetchCount = 0;
        var truncated = false;

        await CrawlSitemapAsync(
            request,
            request.SitemapUrl,
            discovered,
            visitedSitemaps,
            isRoot: true,
            childFetchCountRef: new MutableInt(() => childFetchCount, value => childFetchCount = value),
            truncatedRef: new MutableBool(() => truncated, value => truncated = value),
            cancellationToken);

        return new SitemapCrawlResponse
        {
            SitemapUrl = request.SitemapUrl,
            DiscoveredUrls = discovered.Values.ToList(),
            TotalDiscovered = discovered.Count,
            Truncated = truncated,
        };
    }

    private async Task CrawlSitemapAsync(
        SitemapCrawlRequest request,
        string currentUrl,
        Dictionary<string, SitemapDiscoveredUrl> discovered,
        HashSet<string> visitedSitemaps,
        bool isRoot,
        MutableInt childFetchCountRef,
        MutableBool truncatedRef,
        CancellationToken cancellationToken)
    {
        var normalizedCurrent = _http.NormalizeAbsoluteUrl(_http.EnsureAbsoluteHttpUrl(currentUrl));
        if (!isRoot && !visitedSitemaps.Add(normalizedCurrent))
        {
            return;
        }

        var response = await _http.SendAsync(
            HttpMethod.Get,
            currentUrl,
            request.TimeoutSeconds,
            Math.Min(3, _options.Http.MaxRedirectHops),
            request.Headers,
            userAgent: null,
            captureBody: true,
            cancellationToken);

        if (response.IsTransportFailure)
        {
            throw new HttpWorkerException(response.Error ?? "request failed");
        }

        XDocument document;
        try
        {
            document = XDocument.Parse(response.Body, LoadOptions.None);
        }
        catch
        {
            throw new MalformedSitemapException();
        }

        var root = document.Root ?? throw new MalformedSitemapException();
        if (string.Equals(root.Name.LocalName, "urlset", StringComparison.OrdinalIgnoreCase))
        {
            foreach (var urlElement in root.Elements().Where(element =>
                         string.Equals(element.Name.LocalName, "url", StringComparison.OrdinalIgnoreCase)))
            {
                if (discovered.Count >= request.MaxUrls)
                {
                    truncatedRef.Value = true;
                    return;
                }

                var loc = GetChildValue(urlElement, "loc");
                if (string.IsNullOrWhiteSpace(loc))
                {
                    continue;
                }

                var normalized = _http.NormalizeAbsoluteUrl(_http.EnsureAbsoluteHttpUrl(loc));
                if (discovered.ContainsKey(normalized))
                {
                    continue;
                }

                discovered[normalized] = new SitemapDiscoveredUrl
                {
                    Url = normalized,
                    Lastmod = GetChildValue(urlElement, "lastmod"),
                    Changefreq = GetChildValue(urlElement, "changefreq"),
                    Priority = TryParsePriority(GetChildValue(urlElement, "priority")),
                };
            }

            return;
        }

        if (!string.Equals(root.Name.LocalName, "sitemapindex", StringComparison.OrdinalIgnoreCase))
        {
            throw new MalformedSitemapException();
        }

        var childUrls = root.Elements()
            .Where(element => string.Equals(element.Name.LocalName, "sitemap", StringComparison.OrdinalIgnoreCase))
            .Select(element => GetChildValue(element, "loc"))
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .ToList();

        for (var index = 0; index < childUrls.Count; index++)
        {
            if (discovered.Count >= request.MaxUrls)
            {
                truncatedRef.Value = true;
                return;
            }

            if (childFetchCountRef.Value >= ChildFetchCap)
            {
                truncatedRef.Value = true;
                return;
            }

            var childUrl = childUrls[index]!;
            var normalized = _http.NormalizeAbsoluteUrl(_http.EnsureAbsoluteHttpUrl(childUrl));
            if (visitedSitemaps.Contains(normalized))
            {
                continue;
            }

            childFetchCountRef.Value++;
            await CrawlSitemapAsync(
                request,
                childUrl,
                discovered,
                visitedSitemaps,
                isRoot: false,
                childFetchCountRef,
                truncatedRef,
                cancellationToken);
        }
    }

    private static void ValidateRequest(SitemapCrawlRequest? request)
    {
        if (request is null)
        {
            throw new ValidationException("request body is required");
        }

        if (string.IsNullOrWhiteSpace(request.SitemapUrl) ||
            !Uri.TryCreate(request.SitemapUrl, UriKind.Absolute, out var uri) ||
            (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
        {
            throw new ValidationException("sitemap_url must be an absolute http/https url");
        }

        if (request.TimeoutSeconds < 1 || request.TimeoutSeconds > 120)
        {
            throw new ValidationException("timeout_seconds must be between 1 and 120");
        }

        if (request.MaxUrls < 1 || request.MaxUrls > 10000)
        {
            throw new ValidationException("max_urls must be between 1 and 10000");
        }
    }

    private static string? GetChildValue(XElement parent, string name)
    {
        return parent.Elements()
            .FirstOrDefault(element => string.Equals(element.Name.LocalName, name, StringComparison.OrdinalIgnoreCase))
            ?.Value
            ?.Trim();
    }

    private static double? TryParsePriority(string? rawValue)
    {
        return double.TryParse(rawValue, out var value) ? value : null;
    }

    private sealed class MutableInt(Func<int> getter, Action<int> setter)
    {
        public int Value
        {
            get => getter();
            set => setter(value);
        }
    }

    private sealed class MutableBool(Func<bool> getter, Action<bool> setter)
    {
        public bool Value
        {
            get => getter();
            set => setter(value);
        }
    }
}
