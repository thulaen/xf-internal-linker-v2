using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.AspNetCore.Mvc;

namespace HttpWorker.Api.Controllers.V1;

[ApiController]
[Route("api/v1/graph-sync")]
public sealed class GraphSyncController(IGraphSyncService graphSyncService) : ControllerBase
{
    [HttpPost("content")]
    public async Task<ActionResult<GraphSyncResponse>> SyncContentAsync(
        [FromBody] GraphSyncContentRequest? request,
        CancellationToken cancellationToken)
    {
        var result = await graphSyncService.SyncContentAsync(request!, cancellationToken);
        return Ok(result);
    }

    [HttpPost("refresh")]
    public async Task<ActionResult<GraphSyncResponse>> RefreshAsync(
        [FromBody] GraphSyncRefreshRequest? request,
        CancellationToken cancellationToken)
    {
        var result = await graphSyncService.RefreshAsync(request ?? new GraphSyncRefreshRequest(), cancellationToken);
        return Ok(result);
    }
}
