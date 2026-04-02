using System.Net;
using System.Text.RegularExpressions;

namespace HttpWorker.Services;

internal static class BrokenLinkUrlExtractor
{
    private static readonly Regex BbCodeUrlRegex = new(
        @"\[URL=([^\]]+)\](.*?)\[/URL\]",
        RegexOptions.IgnoreCase | RegexOptions.Singleline | RegexOptions.Compiled);

    private static readonly Regex HtmlLinkRegex = new(
        "<a\\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        RegexOptions.IgnoreCase | RegexOptions.Singleline | RegexOptions.Compiled);

    private static readonly Regex BareUrlRegex = new(
        "https?://[^\\s\\[\\]<>\\\"']+",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    public static IReadOnlyList<string> ExtractUrls(
        string rawBbcode,
        IReadOnlyCollection<string>? allowedDomains)
    {
        if (string.IsNullOrWhiteSpace(rawBbcode))
        {
            return [];
        }

        var normalizedDomains = allowedDomains?
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .Select(static value => value.Trim().ToLowerInvariant())
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        if (normalizedDomains is not null && normalizedDomains.Count == 0)
        {
            normalizedDomains = null;
        }

        var urls = new List<string>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var occupiedSpans = new List<(int Start, int End)>();

        AddMatches(BbCodeUrlRegex.Matches(rawBbcode), occupiedSpans, urls, seen, normalizedDomains, static match => match.Groups[1].Value);
        AddMatches(HtmlLinkRegex.Matches(rawBbcode), occupiedSpans, urls, seen, normalizedDomains, static match => match.Groups[1].Value, checkOverlap: true);
        AddMatches(BareUrlRegex.Matches(rawBbcode), occupiedSpans, urls, seen, normalizedDomains, static match => match.Value, checkOverlap: true);

        return urls;
    }

    private static void AddMatches(
        MatchCollection matches,
        List<(int Start, int End)> occupiedSpans,
        List<string> urls,
        HashSet<string> seen,
        HashSet<string>? allowedDomains,
        Func<Match, string> valueSelector,
        bool checkOverlap = false)
    {
        foreach (Match match in matches)
        {
            if (!match.Success)
            {
                continue;
            }

            var span = (match.Index, match.Index + match.Length);
            if (checkOverlap && SpansOverlap(span, occupiedSpans))
            {
                continue;
            }

            occupiedSpans.Add(span);

            var normalizedUrl = NormalizeUrl(valueSelector(match));
            if (string.IsNullOrEmpty(normalizedUrl))
            {
                continue;
            }

            if (allowedDomains is not null)
            {
                var host = new Uri(normalizedUrl).Host.ToLowerInvariant();
                if (!allowedDomains.Contains(host))
                {
                    continue;
                }
            }

            if (seen.Add(normalizedUrl))
            {
                urls.Add(normalizedUrl);
            }
        }
    }

    private static bool SpansOverlap(
        (int Start, int End) candidate,
        IReadOnlyCollection<(int Start, int End)> occupiedSpans)
    {
        foreach (var span in occupiedSpans)
        {
            if (candidate.Start < span.End && candidate.End > span.Start)
            {
                return true;
            }
        }

        return false;
    }

    private static string NormalizeUrl(string rawUrl)
    {
        if (string.IsNullOrWhiteSpace(rawUrl) ||
            !Uri.TryCreate(WebUtility.HtmlDecode(rawUrl.Trim()), UriKind.Absolute, out var uri) ||
            (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
        {
            return string.Empty;
        }

        var builder = new UriBuilder(uri)
        {
            Scheme = uri.Scheme.ToLowerInvariant(),
            Host = uri.Host.ToLowerInvariant(),
            Fragment = string.Empty,
            Query = string.Empty,
        };

        if (builder.Path.Length > 1 && builder.Path.EndsWith('/'))
        {
            builder.Path = builder.Path.TrimEnd('/');
        }

        if ((builder.Scheme == Uri.UriSchemeHttp && builder.Port == 80) ||
            (builder.Scheme == Uri.UriSchemeHttps && builder.Port == 443))
        {
            builder.Port = -1;
        }

        return builder.Uri.ToString();
    }
}
