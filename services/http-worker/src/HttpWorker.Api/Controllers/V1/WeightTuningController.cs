using HttpWorker.Core.Contracts.V1;
using HttpWorker.Services.Analytics;
using Microsoft.AspNetCore.Mvc;

namespace HttpWorker.Api.Controllers.V1;

/// <summary>
/// POST /api/v1/weight-tuning/run
///
/// Triggers a full FR-018 auto-tune run synchronously:
///   collect signals → optimise → POST challenger to Django.
///
/// Django calls this via the existing http-worker job mechanism
/// (job_type = "weight_tune") or directly when the user clicks
/// "Run Auto-Tune" in the Settings UI.
/// </summary>
[ApiController]
[Route("api/v1/weight-tuning")]
public sealed class WeightTuningController(WeightTunerService tunerService) : ControllerBase
{
    [HttpPost("run")]
    public async Task<IActionResult> RunAsync(
        [FromBody] WeightTuneRequest? request,
        CancellationToken cancellationToken = default)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.RunId))
        {
            return BadRequest(new { error = "run_id is required." });
        }

        if (request.LookbackDays is < 7 or > 365)
        {
            return BadRequest(new { error = "lookback_days must be between 7 and 365." });
        }

        var result = await tunerService.RunAsync(request, cancellationToken);

        return result.Status switch
        {
            "submitted"          => Ok(result),
            "no_change"          => Ok(result),
            "insufficient_data"  => Ok(result),
            _                    => StatusCode(500, result),
        };
    }
}
