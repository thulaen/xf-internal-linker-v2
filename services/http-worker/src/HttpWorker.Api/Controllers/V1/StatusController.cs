using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;

namespace HttpWorker.Api.Controllers.V1;

[ApiController]
[Route("api/v1/status")]
public sealed class StatusController(
    IJobQueueService jobQueueService,
    IOptions<HttpWorkerOptions> options) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> GetAsync(CancellationToken cancellationToken)
    {
        return Ok(new
        {
            status = "ok",
            schema_version = options.Value.SchemaVersion,
            redis_connected = await jobQueueService.IsRedisConnectedAsync(cancellationToken),
        });
    }
}
