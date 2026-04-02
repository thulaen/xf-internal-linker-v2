using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace HttpWorker.Worker;

public sealed class SchedulerWorker(
    IPostgresRuntimeStore postgresRuntimeStore,
    IRuntimeTelemetryService runtimeTelemetryService,
    IOptions<HttpWorkerOptions> options,
    ILogger<SchedulerWorker> logger) : BackgroundService
{
    private readonly HttpWorkerOptions _options = options.Value;
    private readonly string _instanceId = Guid.NewGuid().ToString("N");
    private readonly DateTimeOffset _startedAt = DateTimeOffset.UtcNow;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_options.Scheduler.Enabled)
        {
            await TryWriteHeartbeatAsync(
                enabledPeriodicTasks: 0,
                status: "disabled",
                note: "C# scheduler lane is disabled.",
                stoppingToken);
            return;
        }

        await TryWriteHeartbeatAsync(
            enabledPeriodicTasks: 0,
            status: "starting",
            note: "C# scheduler lane is starting.",
            stoppingToken);

        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(Math.Max(5, _options.Scheduler.PollSeconds)));
        try
        {
            while (await timer.WaitForNextTickAsync(stoppingToken))
            {
                var databaseConnected = await postgresRuntimeStore.CanConnectAsync(stoppingToken);
                if (!databaseConnected)
                {
                    await TryWriteHeartbeatAsync(
                        enabledPeriodicTasks: 0,
                        status: "failed",
                        note: "PostgreSQL is unreachable, so the C# scheduler lane cannot watch schedules yet.",
                        stoppingToken);
                    continue;
                }

                var enabledPeriodicTasks = await postgresRuntimeStore.GetEnabledPeriodicTaskCountAsync(stoppingToken);
                var mode = string.Equals(_options.Scheduler.OwnershipMode, "active", StringComparison.OrdinalIgnoreCase)
                    ? "active"
                    : "shadow";
                var note = mode == "active"
                    ? $"C# scheduler lane is active and sees {enabledPeriodicTasks} enabled periodic task(s)."
                    : $"C# scheduler lane is in shadow mode and sees {enabledPeriodicTasks} enabled django_celery_beat task(s).";

                await TryWriteHeartbeatAsync(enabledPeriodicTasks, mode, note, stoppingToken);
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
        }
    }

    private async Task TryWriteHeartbeatAsync(
        int enabledPeriodicTasks,
        string status,
        string note,
        CancellationToken cancellationToken)
    {
        try
        {
            await runtimeTelemetryService.WriteSchedulerHeartbeatAsync(
                _instanceId,
                _startedAt,
                _options.Scheduler.OwnershipMode,
                status,
                enabledPeriodicTasks,
                note,
                cancellationToken);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "HttpWorker scheduler heartbeat write failed");
        }
    }
}
