using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using Microsoft.AspNetCore.Mvc;

namespace HttpWorker.Api.Controllers.V1;

[ApiController]
[Route("api/v1/jobs")]
public sealed class JobsController(
    IJobQueueService jobQueueService,
    JobProcessor jobProcessor) : ControllerBase
{
    [HttpPost]
    public async Task<ActionResult<QueueSubmitResponse>> SubmitAsync(
        [FromBody] JobRequest? request,
        CancellationToken cancellationToken)
    {
        try {
            jobProcessor.ValidateJobRequest(request);
            await jobQueueService.QueueJobAsync(request!, cancellationToken);

            return Accepted(new QueueSubmitResponse
            {
                JobId = request!.JobId,
                Status = "queued",
                QueuedAt = DateTimeOffset.UtcNow,
            });
        } catch (Exception ex) {
            return StatusCode(500, new { error = ex.ToString() });
        }
    }

    [HttpGet("{jobId}/result")]
    public async Task<IActionResult> ResultAsync(string jobId, CancellationToken cancellationToken)
    {
        var result = await jobQueueService.GetResultAsync(jobId, cancellationToken);
        if (result is not null)
        {
            return Ok(result);
        }

        var deadLetter = await jobQueueService.GetDeadLetterAsync(jobId, cancellationToken);
        if (deadLetter is not null)
        {
            return Ok(new JobResult
            {
                SchemaVersion = deadLetter.SchemaVersion,
                JobId = deadLetter.JobId,
                JobType = deadLetter.JobType,
                CompletedAt = deadLetter.FailedAt,
                Success = false,
                Error = deadLetter.Error,
                Results = null,
            });
        }

        if (await jobQueueService.HasQueuedMarkerAsync(jobId, cancellationToken))
        {
            return StatusCode(StatusCodes.Status202Accepted, new PendingJobResponse
            {
                JobId = jobId,
                Status = "pending",
            });
        }

        return NotFound(new { error = "result not found" });
    }
}
