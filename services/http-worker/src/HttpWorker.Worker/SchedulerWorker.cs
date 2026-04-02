using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using System.Globalization;

namespace HttpWorker.Worker;

public sealed class SchedulerWorker(
    IPostgresRuntimeStore postgresRuntimeStore,
    ISchedulerDispatchService schedulerDispatchService,
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
                    ? await DispatchDueTasksAsync(enabledPeriodicTasks, stoppingToken)
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

    private async Task<string> DispatchDueTasksAsync(int enabledPeriodicTasks, CancellationToken cancellationToken)
    {
        var nowUtc = DateTimeOffset.UtcNow;
        IReadOnlyList<PeriodicTaskRecord> periodicTasks;
        try
        {
            periodicTasks = await postgresRuntimeStore.LoadEnabledPeriodicTasksAsync(cancellationToken);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "C# scheduler failed to load enabled periodic tasks");
            return "C# scheduler lane is active, but it could not read periodic tasks from PostgreSQL.";
        }

        var dueTasks = periodicTasks
            .Where(task => IsDue(task, nowUtc))
            .ToList();

        var dispatchedCount = 0;
        foreach (var task in dueTasks)
        {
            var dispatched = await schedulerDispatchService.DispatchAsync(task, cancellationToken);
            if (!dispatched)
            {
                continue;
            }

            await postgresRuntimeStore.MarkPeriodicTaskTriggeredAsync(task.Id, nowUtc, cancellationToken);
            dispatchedCount += 1;
        }

        return $"C# scheduler lane is active, sees {enabledPeriodicTasks} enabled periodic task(s), and dispatched {dispatchedCount} due task(s) this tick.";
    }

    public static bool IsDue(PeriodicTaskRecord task, DateTimeOffset nowUtc)
    {
        if (task.OneOff && task.LastRunAt is not null)
        {
            return false;
        }

        var currentMinute = new DateTimeOffset(
            nowUtc.Year,
            nowUtc.Month,
            nowUtc.Day,
            nowUtc.Hour,
            nowUtc.Minute,
            0,
            TimeSpan.Zero);

        if (task.LastRunAt is DateTimeOffset lastRunAt)
        {
            var lastMinute = new DateTimeOffset(
                lastRunAt.UtcDateTime.Year,
                lastRunAt.UtcDateTime.Month,
                lastRunAt.UtcDateTime.Day,
                lastRunAt.UtcDateTime.Hour,
                lastRunAt.UtcDateTime.Minute,
                0,
                TimeSpan.Zero);
            if (lastMinute >= currentMinute)
            {
                return false;
            }
        }

        return MatchesField(task.Minute, nowUtc.Minute, 0, 59)
            && MatchesField(task.Hour, nowUtc.Hour, 0, 23)
            && MatchesField(task.DayOfMonth, nowUtc.Day, 1, 31)
            && MatchesField(task.MonthOfYear, nowUtc.Month, 1, 12)
            && MatchesDayOfWeek(task.DayOfWeek, nowUtc);
    }

    public static bool MatchesDayOfWeek(string expression, DateTimeOffset nowUtc)
    {
        var normalized = (int)nowUtc.DayOfWeek;
        return MatchesField(expression, normalized, 0, 7, normalizeDayOfWeek: true);
    }

    public static bool MatchesField(
        string expression,
        int value,
        int minValue,
        int maxValue,
        bool normalizeDayOfWeek = false)
    {
        var normalizedExpression = string.IsNullOrWhiteSpace(expression) ? "*" : expression.Trim();
        foreach (var part in normalizedExpression.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            if (PartMatches(part, value, minValue, maxValue, normalizeDayOfWeek))
            {
                return true;
            }
        }

        return false;
    }

    private static bool PartMatches(string part, int value, int minValue, int maxValue, bool normalizeDayOfWeek)
    {
        if (part == "*")
        {
            return true;
        }

        var step = 1;
        var rangeExpression = part;
        var slashIndex = part.IndexOf('/');
        if (slashIndex >= 0)
        {
            rangeExpression = part[..slashIndex];
            if (!int.TryParse(part[(slashIndex + 1)..], NumberStyles.Integer, CultureInfo.InvariantCulture, out step) || step <= 0)
            {
                return false;
            }
        }

        var (start, end) = ParseRange(rangeExpression, minValue, maxValue, normalizeDayOfWeek);
        if (start is null || end is null)
        {
            return false;
        }

        var normalizedValue = normalizeDayOfWeek && value == 0 ? 7 : value;
        return normalizedValue >= start && normalizedValue <= end && ((normalizedValue - start.Value) % step == 0);
    }

    private static (int? Start, int? End) ParseRange(string expression, int minValue, int maxValue, bool normalizeDayOfWeek)
    {
        if (string.IsNullOrWhiteSpace(expression) || expression == "*")
        {
            return (normalizeDayOfWeek && minValue == 0 ? 1 : minValue, maxValue);
        }

        var dashIndex = expression.IndexOf('-');
        if (dashIndex >= 0)
        {
            var start = ParseToken(expression[..dashIndex], minValue, maxValue, normalizeDayOfWeek);
            var end = ParseToken(expression[(dashIndex + 1)..], minValue, maxValue, normalizeDayOfWeek);
            return (start, end);
        }

        var value = ParseToken(expression, minValue, maxValue, normalizeDayOfWeek);
        return (value, value);
    }

    private static int? ParseToken(string token, int minValue, int maxValue, bool normalizeDayOfWeek)
    {
        if (!int.TryParse(token, NumberStyles.Integer, CultureInfo.InvariantCulture, out var value))
        {
            return null;
        }

        if (normalizeDayOfWeek && value == 0)
        {
            value = 7;
        }

        return value < minValue || value > maxValue ? null : value;
    }
}
