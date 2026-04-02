using System.Globalization;
using System.Text.Json;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Options;
using StackExchange.Redis;

namespace HttpWorker.Services;

public sealed class RedisRuntimeTelemetryService : IRuntimeTelemetryService
{
    private const int WorkerStateTtlSeconds = 300;
    private const int SchedulerStateTtlSeconds = 300;
    private const int DurationSampleLimit = 512;
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly IDatabase _database;
    private readonly string _workerStateKey;
    private readonly string _schedulerStateKey;
    private readonly string _durationSamplesKey;

    public RedisRuntimeTelemetryService(
        ConnectionMultiplexer connection,
        IOptions<HttpWorkerOptions> options)
    {
        _database = connection.GetDatabase();
        var runtimePrefix = GetRuntimePrefix(options.Value.Redis.JobQueueKey);
        _workerStateKey = $"{runtimePrefix}:runtime:worker";
        _schedulerStateKey = $"{runtimePrefix}:runtime:scheduler";
        _durationSamplesKey = $"{runtimePrefix}:runtime:durations";
    }

    public Task WriteHeartbeatAsync(
        string instanceId,
        DateTimeOffset startedAt,
        CancellationToken cancellationToken)
    {
        return UpdateWorkerStateAsync(
            instanceId,
            startedAt,
            DateTimeOffset.UtcNow,
            lastCompleted: null,
            lastFailed: null,
            retryCountDelta: null,
            deadLetterDelta: null);
    }

    public Task RecordResultAsync(
        string instanceId,
        DateTimeOffset startedAt,
        JobResult result,
        int retryCount,
        CancellationToken cancellationToken)
    {
        var snapshot = new HttpWorkerTaskSnapshot
        {
            JobType = result.JobType,
            RecordedAt = result.CompletedAt,
            Error = result.Error,
            RetryCount = retryCount,
            DurationMs = result.DurationMs,
        };

        return UpdateWorkerStateAsync(
            instanceId,
            startedAt,
            result.CompletedAt,
            lastCompleted: result.Success ? snapshot : null,
            lastFailed: result.Success ? null : snapshot,
            retryCountDelta: retryCount,
            deadLetterDelta: null);
    }

    public Task RecordDeadLetterAsync(
        string instanceId,
        DateTimeOffset startedAt,
        DeadLetterRecord deadLetter,
        int retryCount,
        CancellationToken cancellationToken)
    {
        var snapshot = new HttpWorkerTaskSnapshot
        {
            JobType = deadLetter.JobType,
            RecordedAt = deadLetter.FailedAt,
            Error = deadLetter.Error,
            RetryCount = retryCount,
            DurationMs = deadLetter.DurationMs,
        };

        return UpdateWorkerStateAsync(
            instanceId,
            startedAt,
            deadLetter.FailedAt,
            lastCompleted: null,
            lastFailed: snapshot,
            retryCountDelta: retryCount,
            deadLetterDelta: 1);
    }

    public async Task WriteSchedulerHeartbeatAsync(
        string instanceId,
        DateTimeOffset startedAt,
        string ownershipMode,
        string status,
        int enabledPeriodicTasks,
        string note,
        CancellationToken cancellationToken)
    {
        var fields = new[]
        {
            new HashEntry("instance_id", instanceId),
            new HashEntry("started_at", startedAt.ToString("O", CultureInfo.InvariantCulture)),
            new HashEntry("heartbeat_at", DateTimeOffset.UtcNow.ToString("O", CultureInfo.InvariantCulture)),
            new HashEntry("ownership_mode", ownershipMode),
            new HashEntry("enabled_periodic_tasks", enabledPeriodicTasks),
            new HashEntry("status", status),
            new HashEntry("note", note),
        };

        var transaction = _database.CreateTransaction();
        _ = transaction.HashSetAsync(_schedulerStateKey, fields);
        _ = transaction.KeyExpireAsync(_schedulerStateKey, TimeSpan.FromSeconds(SchedulerStateTtlSeconds));
        await transaction.ExecuteAsync();
    }

    public async Task<HttpWorkerWorkerSnapshot?> GetWorkerSnapshotAsync(CancellationToken cancellationToken)
    {
        var entries = await _database.HashGetAllAsync(_workerStateKey);
        if (entries.Length == 0)
        {
            return null;
        }

        var map = entries.ToDictionary(entry => entry.Name.ToString(), entry => entry.Value);
        if (!map.TryGetValue("instance_id", out var instanceId) || instanceId.IsNullOrEmpty)
        {
            return null;
        }

        return new HttpWorkerWorkerSnapshot
        {
            InstanceId = instanceId.ToString(),
            StartedAt = ParseDateTimeOffset(map, "started_at"),
            HeartbeatAt = ParseDateTimeOffset(map, "heartbeat_at"),
            LastCompleted = ParseSnapshot(map, "last_completed"),
            LastFailed = ParseSnapshot(map, "last_failed"),
            RetryCountTotal = ParseInt64(map, "retry_count_total"),
            DeadLetterCount = ParseInt64(map, "dead_letter_count"),
        };
    }

    public async Task<HttpWorkerSchedulerSnapshot?> GetSchedulerSnapshotAsync(CancellationToken cancellationToken)
    {
        var entries = await _database.HashGetAllAsync(_schedulerStateKey);
        if (entries.Length == 0)
        {
            return null;
        }

        var map = entries.ToDictionary(entry => entry.Name.ToString(), entry => entry.Value);
        if (!map.TryGetValue("instance_id", out var instanceId) || instanceId.IsNullOrEmpty)
        {
            return null;
        }

        return new HttpWorkerSchedulerSnapshot
        {
            InstanceId = instanceId.ToString(),
            StartedAt = ParseDateTimeOffset(map, "started_at"),
            HeartbeatAt = ParseDateTimeOffset(map, "heartbeat_at"),
            OwnershipMode = ParseString(map, "ownership_mode"),
            EnabledPeriodicTasks = (int)ParseInt64(map, "enabled_periodic_tasks"),
            Status = ParseString(map, "status"),
            Note = ParseString(map, "note"),
        };
    }

    public async Task<HttpWorkerPerformanceSnapshot> GetPerformanceSnapshotAsync(CancellationToken cancellationToken)
    {
        var entries = await _database.ListRangeAsync(_durationSamplesKey, 0, DurationSampleLimit - 1);
        if (entries.Length == 0)
        {
            return new HttpWorkerPerformanceSnapshot();
        }

        var samples = entries
            .Select(static value => TryDeserializeSample(value))
            .Where(static sample => sample is not null)
            .Select(static sample => sample!)
            .OrderBy(static sample => sample.DurationMs)
            .ToList();
        if (samples.Count == 0)
        {
            return new HttpWorkerPerformanceSnapshot();
        }

        var oneMinuteAgo = DateTimeOffset.UtcNow.AddMinutes(-1);
        var drainRate = samples.Count(sample => sample.CompletedAt >= oneMinuteAgo);

        return new HttpWorkerPerformanceSnapshot
        {
            CompletedJobsTracked = samples.Count,
            LatencyP50Ms = Percentile(samples, 0.50),
            LatencyP95Ms = Percentile(samples, 0.95),
            LatencyP99Ms = Percentile(samples, 0.99),
            DrainRatePerMinute = drainRate,
        };
    }

    private async Task UpdateWorkerStateAsync(
        string instanceId,
        DateTimeOffset startedAt,
        DateTimeOffset heartbeatAt,
        HttpWorkerTaskSnapshot? lastCompleted,
        HttpWorkerTaskSnapshot? lastFailed,
        int? retryCountDelta,
        int? deadLetterDelta)
    {
        var transaction = _database.CreateTransaction();
        var fields = new List<HashEntry>
        {
            new("instance_id", instanceId),
            new("started_at", startedAt.ToString("O", CultureInfo.InvariantCulture)),
            new("heartbeat_at", heartbeatAt.ToString("O", CultureInfo.InvariantCulture)),
        };

        if (lastCompleted is not null)
        {
            fields.Add(new HashEntry("last_completed", JsonSerializer.Serialize(lastCompleted, JsonOptions)));
        }

        if (lastFailed is not null)
        {
            fields.Add(new HashEntry("last_failed", JsonSerializer.Serialize(lastFailed, JsonOptions)));
        }

        _ = transaction.HashSetAsync(_workerStateKey, fields.ToArray());
        _ = transaction.KeyExpireAsync(_workerStateKey, TimeSpan.FromSeconds(WorkerStateTtlSeconds));

        var retryDelta = retryCountDelta.GetValueOrDefault();
        if (retryDelta > 0)
        {
            _ = transaction.HashIncrementAsync(_workerStateKey, "retry_count_total", retryDelta);
        }

        var deadLetterIncrement = deadLetterDelta.GetValueOrDefault();
        if (deadLetterIncrement > 0)
        {
            _ = transaction.HashIncrementAsync(_workerStateKey, "dead_letter_count", deadLetterIncrement);
        }

        if (lastCompleted is not null && lastCompleted.DurationMs > 0)
        {
            var sample = JsonSerializer.Serialize(
                new DurationSample(lastCompleted.RecordedAt, lastCompleted.DurationMs),
                JsonOptions);
            _ = transaction.ListLeftPushAsync(_durationSamplesKey, sample);
            _ = transaction.ListTrimAsync(_durationSamplesKey, 0, DurationSampleLimit - 1);
        }

        await transaction.ExecuteAsync();
    }

    private static string GetRuntimePrefix(string jobQueueKey)
    {
        var lastSeparator = jobQueueKey.LastIndexOf(':');
        return lastSeparator > 0 ? jobQueueKey[..lastSeparator] : jobQueueKey;
    }

    private static DateTimeOffset ParseDateTimeOffset(
        IReadOnlyDictionary<string, RedisValue> map,
        string key)
    {
        if (!map.TryGetValue(key, out var value) || value.IsNullOrEmpty)
        {
            return DateTimeOffset.MinValue;
        }

        return DateTimeOffset.Parse(value.ToString(), CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind);
    }

    private static HttpWorkerTaskSnapshot? ParseSnapshot(
        IReadOnlyDictionary<string, RedisValue> map,
        string key)
    {
        if (!map.TryGetValue(key, out var value) || value.IsNullOrEmpty)
        {
            return null;
        }

        return JsonSerializer.Deserialize<HttpWorkerTaskSnapshot>(value!, JsonOptions);
    }

    private static long ParseInt64(
        IReadOnlyDictionary<string, RedisValue> map,
        string key)
    {
        if (!map.TryGetValue(key, out var value) || value.IsNullOrEmpty)
        {
            return 0;
        }

        return long.TryParse(value.ToString(), out var parsedValue) ? parsedValue : 0;
    }

    private static string ParseString(
        IReadOnlyDictionary<string, RedisValue> map,
        string key)
    {
        return map.TryGetValue(key, out var value) && !value.IsNullOrEmpty
            ? value.ToString()
            : string.Empty;
    }

    private static DurationSample? TryDeserializeSample(RedisValue value)
    {
        if (value.IsNullOrEmpty)
        {
            return null;
        }

        try
        {
            return JsonSerializer.Deserialize<DurationSample>(value!, JsonOptions);
        }
        catch
        {
            return null;
        }
    }

    private static double Percentile(
        IReadOnlyList<DurationSample> samples,
        double percentile)
    {
        if (samples.Count == 0)
        {
            return 0;
        }

        var index = Math.Clamp((int)Math.Ceiling(samples.Count * percentile) - 1, 0, samples.Count - 1);
        return samples[index].DurationMs;
    }

    private sealed record DurationSample(DateTimeOffset CompletedAt, long DurationMs);
}
