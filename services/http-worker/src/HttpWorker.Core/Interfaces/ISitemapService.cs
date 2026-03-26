using HttpWorker.Core.Contracts.V1;

namespace HttpWorker.Core.Interfaces;

public interface ISitemapService
{
    Task<SitemapCrawlResponse> CrawlAsync(SitemapCrawlRequest request, CancellationToken cancellationToken);
}
