using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.AspNetCore.Mvc;

namespace HttpWorker.Api.Controllers.V1;

[ApiController]
[Route("api/v1/urls")]
public sealed class UrlFetchController(IUrlFetchService urlFetchService) : ControllerBase
{
    [HttpPost("fetch")]
    public async Task<ActionResult<UrlFetchResponse>> FetchAsync(
        [FromBody] UrlFetchRequest? request,
        CancellationToken cancellationToken)
    {
        var result = await urlFetchService.FetchAsync(request!, cancellationToken);
        return Ok(result);
    }
}
