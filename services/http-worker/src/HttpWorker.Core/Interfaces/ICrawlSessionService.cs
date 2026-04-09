using HttpWorker.Core.Contracts.V1;

namespace HttpWorker.Core.Interfaces;

/// <summary>
/// Executes a web crawl session: fetches pages from a site, extracts SEO
/// metadata and internal links, and writes results to PostgreSQL in batches.
/// </summary>
public interface ICrawlSessionService
{
    /// <summary>
    /// Run (or resume) a crawl session.  The session respects politeness
    /// rules, checkpoints to Redis, and streams progress via the progress
    /// stream service.
    /// </summary>
    Task<CrawlSessionResponse> ExecuteAsync(
        CrawlSessionRequest request,
        string jobId,
        CancellationToken cancellationToken);
}
