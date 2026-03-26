using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.AspNetCore.Mvc;

namespace HttpWorker.Api.Controllers.V1;

[ApiController]
[Route("api/v1/sitemaps")]
public sealed class SitemapController(ISitemapService sitemapService) : ControllerBase
{
    [HttpPost("crawl")]
    public async Task<ActionResult<SitemapCrawlResponse>> CrawlAsync(
        [FromBody] SitemapCrawlRequest? request,
        CancellationToken cancellationToken)
    {
        var result = await sitemapService.CrawlAsync(request!, cancellationToken);
        return Ok(result);
    }
}
