using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.AspNetCore.Mvc;

namespace HttpWorker.Api.Controllers.V1;

[ApiController]
[Route("api/v1/broken-links")]
public sealed class BrokenLinkController(IBrokenLinkService brokenLinkService) : ControllerBase
{
    [HttpPost("check")]
    public async Task<ActionResult<BrokenLinkCheckResponse>> CheckAsync(
        [FromBody] BrokenLinkCheckRequest? request,
        CancellationToken cancellationToken)
    {
        var result = await brokenLinkService.CheckAsync(request!, cancellationToken);
        return Ok(result);
    }
}
