using System.Reflection;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;

namespace HttpWorker.Api.Controllers.V1;

[ApiController]
[Route("api/v1/status")]
public sealed class StatusController(
    IJobQueueService jobQueueService,
    IPostgresRuntimeStore postgresRuntimeStore,
    IRuntimeTelemetryService runtimeTelemetryService,
    IOptions<HttpWorkerOptions> options) : ControllerBase
{
    private static readonly DateTimeOffset ServiceStartedAt = DateTimeOffset.UtcNow;
    private static readonly string BuildVersion =
        Assembly.GetEntryAssembly()?.GetName().Version?.ToString() ?? "dev";
    private static readonly TimeSpan WorkerHeartbeatFreshWindow = TimeSpan.FromSeconds(15);

    [HttpGet]
    public async Task<ActionResult<HttpWorkerStatusResponse>> GetAsync(CancellationToken cancellationToken)
    {
        var response = new HttpWorkerStatusResponse
        {
            Status = "degraded",
            SchemaVersion = options.Value.SchemaVersion,
            BuildVersion = BuildVersion,
            ServiceStartedAt = ServiceStartedAt,
        };

        try
        {
            response.RedisConnected = await jobQueueService.IsRedisConnectedAsync(cancellationToken);
            response.DatabaseConnected = await postgresRuntimeStore.CanConnectAsync(cancellationToken);
            if (response.RedisConnected)
            {
                response.QueueDepth = await jobQueueService.GetQueueDepthAsync(cancellationToken);
                response.Worker = await runtimeTelemetryService.GetWorkerSnapshotAsync(cancellationToken);
                response.Scheduler = await runtimeTelemetryService.GetSchedulerSnapshotAsync(cancellationToken);
                response.Performance = await runtimeTelemetryService.GetPerformanceSnapshotAsync(cancellationToken);

                if (response.Worker is not null)
                {
                    response.WorkerHeartbeatAgeSeconds = Math.Max(
                        0,
                        (DateTimeOffset.UtcNow - response.Worker.HeartbeatAt).TotalSeconds);
                    response.WorkerOnline = response.WorkerHeartbeatAgeSeconds <= WorkerHeartbeatFreshWindow.TotalSeconds;
                }

                if (response.Scheduler is not null)
                {
                    response.SchedulerHeartbeatAgeSeconds = Math.Max(
                        0,
                        (DateTimeOffset.UtcNow - response.Scheduler.HeartbeatAt).TotalSeconds);
                }
            }

            response.DistillationFallbackActive = HttpWorker.Services.Distillation.TextDistiller.IsFallbackActive;

            response.Status = response.RedisConnected &&
                response.DatabaseConnected &&
                response.WorkerOnline
                ? "ok"
                : "degraded";
        }
        catch
        {
            response.Status = "degraded";
            response.RedisConnected = false;
            response.DatabaseConnected = false;
            response.WorkerOnline = false;
        }

        return Ok(response);
    }
}
