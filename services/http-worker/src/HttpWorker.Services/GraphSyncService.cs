using System.Text.RegularExpressions;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;

namespace HttpWorker.Services;

public sealed class GraphSyncService(IGraphSyncStore graphSyncStore) : IGraphSyncService
{
    public async Task<GraphSyncResponse> SyncContentAsync(
        GraphSyncContentRequest request,
        CancellationToken cancellationToken)
    {
        Validate(request);
        var trackedAt = request.TrackedAt ?? DateTimeOffset.UtcNow;
        var command = await BuildCommandAsync(
            new GraphSyncSourceContent
            {
                ContentItemPk = request.ContentItemPk,
                ContentId = request.ContentId,
                ContentType = request.ContentType.Trim(),
                RawBbcode = request.RawBbcode ?? string.Empty,
            },
            request.ForumDomains,
            request.AllowDisappearance,
            trackedAt,
            cancellationToken);
        await graphSyncStore.PersistAsync(command, cancellationToken);
        return ToResponse(command, refreshedItems: 1);
    }

    public async Task<GraphSyncResponse> RefreshAsync(
        GraphSyncRefreshRequest request,
        CancellationToken cancellationToken)
    {
        var trackedAt = request.TrackedAt ?? DateTimeOffset.UtcNow;
        var response = new GraphSyncResponse();
        var sources = await graphSyncStore.LoadRefreshSourcesAsync(
            request.ContentItemPks?.Distinct().OrderBy(static value => value).ToList(),
            cancellationToken);

        foreach (var source in sources)
        {
            var command = await BuildCommandAsync(
                source,
                request.ForumDomains,
                allowDisappearance: true,
                trackedAt,
                cancellationToken);
            await graphSyncStore.PersistAsync(command, cancellationToken);
            response.RefreshedItems += 1;
            response.ActiveLinks += command.ActiveLinks;
            response.CreatedLinks += command.NewLinks.Count;
            response.UpdatedLinks += command.UpdatedLinks.Count;
            response.DeletedLinks += command.DeletedLinkIds.Count;
            response.CreatedFreshnessEdges += command.NewFreshnessEdges.Count;
            response.UpdatedFreshnessEdges += command.UpdatedFreshnessEdges.Count;
        }

        return response;
    }

    private async Task<GraphSyncPersistenceCommand> BuildCommandAsync(
        GraphSyncSourceContent source,
        IReadOnlyCollection<string> forumDomains,
        bool allowDisappearance,
        DateTimeOffset trackedAt,
        CancellationToken cancellationToken)
    {
        var pending = GraphLinkParser.FindPendingLinks(
            source.RawBbcode,
            source.ContentId,
            source.ContentType,
            forumDomains);
        var fallbackUrlTargets = await graphSyncStore.LoadDestinationsByUrlAsync(
            pending
                .Where(static item => item.TargetContentId is null && !string.IsNullOrEmpty(item.NormalizedUrl))
                .Select(static item => item.NormalizedUrl)
                .Distinct(StringComparer.Ordinal)
                .ToList(),
            cancellationToken);
        var resolvedLinks = GraphLinkParser.ResolveLinks(
            source.ContentId,
            source.ContentType,
            pending,
            fallbackUrlTargets);
        var destinations = await graphSyncStore.LoadDestinationsAsync(
            resolvedLinks
                .Select(static item => (item.ToContentId, item.ToContentType))
                .Distinct()
                .ToList(),
            cancellationToken);
        var sourceState = await graphSyncStore.LoadSourceStateAsync(source.ContentItemPk, cancellationToken);
        return GraphSyncPlanner.Build(
            source.ContentItemPk,
            resolvedLinks,
            destinations,
            sourceState,
            allowDisappearance,
            trackedAt);
    }

    private static GraphSyncResponse ToResponse(GraphSyncPersistenceCommand command, int refreshedItems)
    {
        return new GraphSyncResponse
        {
            RefreshedItems = refreshedItems,
            ActiveLinks = command.ActiveLinks,
            CreatedLinks = command.NewLinks.Count,
            UpdatedLinks = command.UpdatedLinks.Count,
            DeletedLinks = command.DeletedLinkIds.Count,
            CreatedFreshnessEdges = command.NewFreshnessEdges.Count,
            UpdatedFreshnessEdges = command.UpdatedFreshnessEdges.Count,
        };
    }

    private static void Validate(GraphSyncContentRequest request)
    {
        if (request is null)
        {
            throw new ValidationException("request body is required");
        }

        if (request.ContentItemPk <= 0)
        {
            throw new ValidationException("content_item_pk must be a positive integer");
        }

        if (request.ContentId <= 0)
        {
            throw new ValidationException("content_id must be a positive integer");
        }

        if (string.IsNullOrWhiteSpace(request.ContentType))
        {
            throw new ValidationException("content_type is required");
        }
    }
}

internal sealed class PendingGraphLink
{
    public string NormalizedUrl { get; set; } = string.Empty;

    public int? TargetContentId { get; set; }

    public string? TargetContentType { get; set; }

    public string AnchorText { get; set; } = string.Empty;

    public string ExtractionMethod { get; set; } = string.Empty;

    public string ContextClass { get; set; } = string.Empty;
}

internal sealed class ResolvedGraphLink
{
    public int ToContentId { get; set; }

    public string ToContentType { get; set; } = string.Empty;

    public string AnchorText { get; set; } = string.Empty;

    public string ExtractionMethod { get; set; } = string.Empty;

    public int LinkOrdinal { get; set; }

    public int SourceInternalLinkCount { get; set; }

    public string ContextClass { get; set; } = string.Empty;
}

internal static class GraphSyncPlanner
{
    public static GraphSyncPersistenceCommand Build(
        int fromContentItemPk,
        IReadOnlyList<ResolvedGraphLink> resolvedLinks,
        IReadOnlyDictionary<(int ContentId, string ContentType), GraphSyncDestination> destinations,
        GraphSyncSourceState sourceState,
        bool allowDisappearance,
        DateTimeOffset trackedAt)
    {
        var command = new GraphSyncPersistenceCommand
        {
            ActiveLinks = resolvedLinks.Count,
        };
        var currentMap = sourceState.ExistingLinks
            .GroupBy(static row => (row.ToContentId, row.ToContentType), StringTupleComparer.Instance)
            .ToDictionary(
                static group => group.Key,
                static group => group.OrderBy(static row => row.Id).ToList(),
                StringTupleComparer.Instance);
        var targetKeys = new HashSet<(int ContentId, string ContentType)>(StringTupleComparer.Instance);

        foreach (var link in resolvedLinks)
        {
            var key = (link.ToContentId, link.ToContentType);
            targetKeys.Add(key);

            if (currentMap.TryGetValue(key, out var currentRows) && currentRows.Count > 0)
            {
                var primary = currentRows[0];
                foreach (var duplicate in currentRows.Skip(1))
                {
                    command.DeletedLinkIds.Add(duplicate.Id);
                }

                if (primary.AnchorText != link.AnchorText ||
                    primary.ExtractionMethod != link.ExtractionMethod ||
                    primary.LinkOrdinal != link.LinkOrdinal ||
                    primary.SourceInternalLinkCount != link.SourceInternalLinkCount ||
                    primary.ContextClass != link.ContextClass)
                {
                    command.UpdatedLinks.Add(new GraphSyncExistingLinkUpdate
                    {
                        Id = primary.Id,
                        AnchorText = link.AnchorText,
                        ExtractionMethod = link.ExtractionMethod,
                        LinkOrdinal = link.LinkOrdinal,
                        SourceInternalLinkCount = link.SourceInternalLinkCount,
                        ContextClass = link.ContextClass,
                    });
                }

                continue;
            }

            if (!destinations.TryGetValue(key, out var destination))
            {
                continue;
            }

            command.NewLinks.Add(new GraphSyncExistingLinkInsert
            {
                FromContentItemPk = fromContentItemPk,
                ToContentItemPk = destination.ContentItemPk,
                AnchorText = link.AnchorText,
                ExtractionMethod = link.ExtractionMethod,
                LinkOrdinal = link.LinkOrdinal,
                SourceInternalLinkCount = link.SourceInternalLinkCount,
                ContextClass = link.ContextClass,
                DiscoveredAt = trackedAt,
            });
        }

        if (allowDisappearance)
        {
            foreach (var entry in currentMap)
            {
                if (targetKeys.Contains(entry.Key))
                {
                    continue;
                }

                foreach (var row in entry.Value)
                {
                    command.DeletedLinkIds.Add(row.Id);
                }
            }
        }

        var freshnessMap = sourceState.FreshnessEdges
            .ToDictionary(static row => (row.ToContentId, row.ToContentType), static row => row, StringTupleComparer.Instance);

        foreach (var link in resolvedLinks)
        {
            var key = (link.ToContentId, link.ToContentType);
            if (!destinations.TryGetValue(key, out var destination))
            {
                continue;
            }

            if (!freshnessMap.TryGetValue(key, out var existing))
            {
                command.NewFreshnessEdges.Add(new GraphSyncFreshnessInsert
                {
                    FromContentItemPk = fromContentItemPk,
                    ToContentItemPk = destination.ContentItemPk,
                    FirstSeenAt = trackedAt,
                    LastSeenAt = trackedAt,
                    IsActive = true,
                });
                continue;
            }

            if (existing.LastSeenAt != trackedAt || !existing.IsActive || existing.LastDisappearedAt is not null)
            {
                command.UpdatedFreshnessEdges.Add(new GraphSyncFreshnessUpdate
                {
                    Id = existing.Id,
                    FirstSeenAt = existing.FirstSeenAt,
                    LastSeenAt = trackedAt,
                    LastDisappearedAt = null,
                    IsActive = true,
                });
            }
        }

        if (allowDisappearance)
        {
            foreach (var entry in freshnessMap)
            {
                if (targetKeys.Contains(entry.Key) || !entry.Value.IsActive)
                {
                    continue;
                }

                command.UpdatedFreshnessEdges.Add(new GraphSyncFreshnessUpdate
                {
                    Id = entry.Value.Id,
                    FirstSeenAt = entry.Value.FirstSeenAt,
                    LastSeenAt = entry.Value.LastSeenAt,
                    LastDisappearedAt = trackedAt,
                    IsActive = false,
                });
            }
        }

        command.DeletedLinkIds.Sort();
        return command;
    }
}

internal static class GraphLinkParser
{
    private static readonly Regex XfThreadRegex = new(@"/threads/(?:[^/]*\.)?(\d+)(?:/|$)", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex XfResourceRegex = new(@"/resources/(?:[^/]*\.)?(\d+)(?:/|$)", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex BbcodeUrlRegex = new(@"\[URL=([^\]]+)\](.*?)\[/URL\]", RegexOptions.IgnoreCase | RegexOptions.Compiled | RegexOptions.Singleline);
    private static readonly Regex HtmlLinkRegex = new(@"<a\b[^>]*href=[""']([^""']+)[""'][^>]*>(.*?)</a>", RegexOptions.IgnoreCase | RegexOptions.Compiled | RegexOptions.Singleline);
    private static readonly Regex BareUrlRegex = new(@"https?://[^\s\[\]<>""']+", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex HtmlTagRegex = new(@"<[^>]+>", RegexOptions.Compiled);
    private static readonly Regex BbcodeTagRegex = new(@"\[[^\]]+\]", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex ContextTokenRegex = new(@"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", RegexOptions.Compiled);
    private static readonly HashSet<string> AllowedSchemes = ["http", "https"];
    private const int ContextWindowChars = 80;

    public static IReadOnlyList<PendingGraphLink> FindPendingLinks(
        string rawBbcode,
        int fromContentId,
        string fromContentType,
        IReadOnlyCollection<string> forumDomains)
    {
        rawBbcode ??= string.Empty;
        var matches = FindUrls(rawBbcode);
        if (matches.Count == 0)
        {
            return [];
        }

        var normalizedDomains = new HashSet<string>(
            forumDomains
                .Where(static value => !string.IsNullOrWhiteSpace(value))
                .Select(static value => value.Trim().ToLowerInvariant()),
            StringComparer.Ordinal);
        var pending = new List<PendingGraphLink>(matches.Count);

        foreach (var match in matches)
        {
            var normalizedUrl = HttpWorker.Core.Text.UrlNormalizer.NormalizeInternalUrl(match.Url);
            if (string.IsNullOrEmpty(normalizedUrl))
            {
                continue;
            }

            if (!TryResolveTarget(normalizedUrl, normalizedDomains, out var targetContentId, out var targetContentType))
            {
                targetContentId = null;
                targetContentType = null;
            }

            if (targetContentId == fromContentId && string.Equals(targetContentType, fromContentType, StringComparison.Ordinal))
            {
                continue;
            }

            pending.Add(new PendingGraphLink
            {
                NormalizedUrl = normalizedUrl,
                TargetContentId = targetContentId,
                TargetContentType = targetContentType,
                AnchorText = match.AnchorText.Trim(),
                ExtractionMethod = match.ExtractionMethod,
                ContextClass = ClassifyContext(rawBbcode, match.Start, match.End),
            });
        }

        return pending;
    }

    public static IReadOnlyList<ResolvedGraphLink> ResolveLinks(
        int fromContentId,
        string fromContentType,
        IReadOnlyList<PendingGraphLink> pending,
        IReadOnlyDictionary<string, GraphSyncDestination> fallbackTargets)
    {
        var resolved = new List<ResolvedGraphLink>(pending.Count);
        var seen = new HashSet<(int ContentId, string ContentType)>(StringTupleComparer.Instance);

        foreach (var item in pending)
        {
            var contentId = item.TargetContentId;
            var contentType = item.TargetContentType;
            if (contentId is null || string.IsNullOrEmpty(contentType))
            {
                if (!fallbackTargets.TryGetValue(item.NormalizedUrl, out var destination))
                {
                    continue;
                }

                contentId = destination.ContentId;
                contentType = destination.ContentType;
            }

            if (contentId == fromContentId && string.Equals(contentType, fromContentType, StringComparison.Ordinal))
            {
                continue;
            }

            var key = (contentId.Value, contentType!);
            if (!seen.Add(key))
            {
                continue;
            }

            resolved.Add(new ResolvedGraphLink
            {
                ToContentId = contentId.Value,
                ToContentType = contentType!,
                AnchorText = item.AnchorText,
                ExtractionMethod = item.ExtractionMethod,
                ContextClass = item.ContextClass,
            });
        }

        for (var index = 0; index < resolved.Count; index++)
        {
            resolved[index].LinkOrdinal = index;
            resolved[index].SourceInternalLinkCount = resolved.Count;
        }

        return resolved;
    }

    private static List<MatchedLink> FindUrls(string rawBbcode)
    {
        if (string.IsNullOrEmpty(rawBbcode))
        {
            return [];
        }

        var found = new List<MatchedLink>();
        var occupied = new List<(int Start, int End)>();

        foreach (Match match in BbcodeUrlRegex.Matches(rawBbcode))
        {
            occupied.Add((match.Index, match.Index + match.Length));
            found.Add(new MatchedLink(
                match.Groups[1].Value,
                StripMarkup(match.Groups[2].Value),
                "bbcode_anchor",
                match.Index,
                match.Index + match.Length));
        }

        foreach (Match match in HtmlLinkRegex.Matches(rawBbcode))
        {
            if (Overlaps(match.Index, match.Index + match.Length, occupied))
            {
                continue;
            }

            occupied.Add((match.Index, match.Index + match.Length));
            found.Add(new MatchedLink(
                match.Groups[1].Value,
                StripMarkup(match.Groups[2].Value),
                "html_anchor",
                match.Index,
                match.Index + match.Length));
        }

        foreach (Match match in BareUrlRegex.Matches(rawBbcode))
        {
            if (Overlaps(match.Index, match.Index + match.Length, occupied))
            {
                continue;
            }

            found.Add(new MatchedLink(
                match.Value,
                string.Empty,
                "bare_url",
                match.Index,
                match.Index + match.Length));
        }

        found.Sort(static (left, right) =>
        {
            var startComparison = left.Start.CompareTo(right.Start);
            if (startComparison != 0)
            {
                return startComparison;
            }

            var endComparison = left.End.CompareTo(right.End);
            if (endComparison != 0)
            {
                return endComparison;
            }

            return string.CompareOrdinal(left.ExtractionMethod, right.ExtractionMethod);
        });
        return found;
    }

    private static bool TryResolveTarget(
        string normalizedUrl,
        HashSet<string> forumDomains,
        out int? contentId,
        out string? contentType)
    {
        contentId = null;
        contentType = null;
        if (!Uri.TryCreate(normalizedUrl, UriKind.Absolute, out var uri))
        {
            return false;
        }

        if (forumDomains.Count > 0 && !forumDomains.Contains(uri.Host, StringComparer.Ordinal))
        {
            return false;
        }

        var threadMatch = XfThreadRegex.Match(uri.AbsolutePath);
        if (threadMatch.Success && int.TryParse(threadMatch.Groups[1].Value, out var threadId))
        {
            contentId = threadId;
            contentType = "thread";
            return true;
        }

        var resourceMatch = XfResourceRegex.Match(uri.AbsolutePath);
        if (resourceMatch.Success && int.TryParse(resourceMatch.Groups[1].Value, out var resourceId))
        {
            contentId = resourceId;
            contentType = "resource";
            return true;
        }

        return false;
    }

    private static string StripMarkup(string value)
    {
        var cleaned = System.Net.WebUtility.HtmlDecode(value ?? string.Empty);
        cleaned = HtmlTagRegex.Replace(cleaned, string.Empty);
        cleaned = BbcodeTagRegex.Replace(cleaned, string.Empty);
        return cleaned.Trim();
    }

    private static bool Overlaps(int start, int end, List<(int Start, int End)> occupied)
    {
        foreach (var span in occupied)
        {
            if (start < span.End && end > span.Start)
            {
                return true;
            }
        }

        return false;
    }

    private static string ClassifyContext(string rawBbcode, int start, int end)
    {
        var leftStart = Math.Max(0, start - ContextWindowChars);
        var rightEnd = Math.Min(rawBbcode.Length, end + ContextWindowChars);
        var left = CleanContextWindow(rawBbcode[leftStart..start]);
        var right = CleanContextWindow(rawBbcode[end..rightEnd]);
        var hasLeft = ContextTokenRegex.IsMatch(left);
        var hasRight = ContextTokenRegex.IsMatch(right);
        if (hasLeft && hasRight)
        {
            return "contextual";
        }

        if (hasLeft || hasRight)
        {
            return "weak_context";
        }

        return "isolated";
    }

    private static string CleanContextWindow(string value)
    {
        var cleaned = System.Net.WebUtility.HtmlDecode(value ?? string.Empty);
        cleaned = HtmlTagRegex.Replace(cleaned, " ");
        cleaned = BbcodeTagRegex.Replace(cleaned, " ");
        cleaned = BareUrlRegex.Replace(cleaned, " ");
        return Regex.Replace(cleaned, @"\s+", " ").Trim();
    }

    private sealed record MatchedLink(string Url, string AnchorText, string ExtractionMethod, int Start, int End);
}

internal sealed class StringTupleComparer : IEqualityComparer<(int ContentId, string ContentType)>
{
    public static readonly StringTupleComparer Instance = new();

    public bool Equals((int ContentId, string ContentType) left, (int ContentId, string ContentType) right)
    {
        return left.ContentId == right.ContentId &&
            string.Equals(left.ContentType, right.ContentType, StringComparison.Ordinal);
    }

    public int GetHashCode((int ContentId, string ContentType) value)
    {
        return HashCode.Combine(value.ContentId, value.ContentType);
    }
}
