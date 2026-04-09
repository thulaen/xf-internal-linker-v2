using HttpWorker.Core.Text;

namespace HttpWorker.Services;

/// <summary>
/// URL priority queue for the crawler.  Maintains a frontier of URLs to crawl
/// ordered by priority (highest first) and a visited set for dedup.
///
/// RAM budget: ~15 MB for 50K URLs (HashSet + SortedSet).
/// </summary>
internal sealed class CrawlFrontier
{
    private readonly SortedSet<FrontierEntry> _queue = new(FrontierEntryComparer.Instance);
    private readonly HashSet<string> _visited = new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> _enqueued = new(StringComparer.OrdinalIgnoreCase);
    private readonly int _maxDepth;

    public int QueueSize => _queue.Count;
    public int VisitedCount => _visited.Count;

    public CrawlFrontier(int maxDepth = 5)
    {
        _maxDepth = maxDepth;
    }

    /// <summary>Add a URL to the frontier if not already visited or queued.</summary>
    public bool Enqueue(string url, double priority, int depth)
    {
        if (depth > _maxDepth) return false;

        var normalized = UrlNormalizer.NormalizeInternalUrl(url);
        if (string.IsNullOrEmpty(normalized)) return false;
        if (_visited.Contains(normalized)) return false;
        if (!_enqueued.Add(normalized)) return false;

        _queue.Add(new FrontierEntry(normalized, priority, depth));
        return true;
    }

    /// <summary>Seed the frontier from sitemap URLs.</summary>
    public void SeedFromSitemap(IEnumerable<(string url, double priority)> urls)
    {
        foreach (var (url, priority) in urls)
        {
            Enqueue(url, priority, depth: 0);
        }
    }

    /// <summary>Pop the highest-priority URL from the frontier.</summary>
    public FrontierEntry? Dequeue()
    {
        if (_queue.Count == 0) return null;
        var entry = _queue.Max!;
        _queue.Remove(entry);
        _enqueued.Remove(entry.NormalizedUrl);
        _visited.Add(entry.NormalizedUrl);
        return entry;
    }

    /// <summary>Mark a URL as visited without it having been in the queue.</summary>
    public void MarkVisited(string normalizedUrl)
    {
        _visited.Add(normalizedUrl);
    }

    /// <summary>Check if a URL has been visited.</summary>
    public bool IsVisited(string normalizedUrl) => _visited.Contains(normalizedUrl);

    /// <summary>Add discovered links from a crawled page to the frontier.</summary>
    public int AddDiscoveredLinks(
        IEnumerable<string> urls,
        int parentDepth,
        double basePriority = 0.5)
    {
        int added = 0;
        foreach (var url in urls)
        {
            double depthPenalty = (parentDepth + 1) * 0.05;
            if (Enqueue(url, basePriority - depthPenalty, parentDepth + 1))
                added++;
        }
        return added;
    }
}

internal sealed record FrontierEntry(string NormalizedUrl, double Priority, int Depth);

/// <summary>Compare by priority descending, then URL for stable ordering.</summary>
internal sealed class FrontierEntryComparer : IComparer<FrontierEntry>
{
    public static readonly FrontierEntryComparer Instance = new();

    public int Compare(FrontierEntry? x, FrontierEntry? y)
    {
        if (ReferenceEquals(x, y)) return 0;
        if (x is null) return -1;
        if (y is null) return 1;

        int cmp = x.Priority.CompareTo(y.Priority);
        if (cmp != 0) return cmp;
        return string.Compare(x.NormalizedUrl, y.NormalizedUrl, StringComparison.Ordinal);
    }
}
