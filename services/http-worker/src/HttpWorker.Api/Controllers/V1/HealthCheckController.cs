using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.AspNetCore.Mvc;

namespace HttpWorker.Api.Controllers.V1;

[ApiController]
[Route("api/v1/health")]
public sealed class HealthCheckController(IHealthCheckService healthCheckService) : ControllerBase
{
    [HttpPost("check")]
    public async Task<ActionResult<HealthCheckResponse>> CheckAsync(
        [FromBody] HealthCheckRequest? request,
        CancellationToken cancellationToken)
    {
        var result = await healthCheckService.CheckAsync(request!, cancellationToken);
        return Ok(result);
    }
}
