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
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly IDatabase _database;
    private readonly string _workerStateKey;

    public RedisRuntimeTelemetryService(
        ConnectionMultiplexer connection,
        IOptions<HttpWorkerOptions> options)
    {
        _database = connection.GetDatabase();
        _workerStateKey = $"{GetRuntimePrefix(options.Value.Redis.JobQueueKey)}:runtime:worker";
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

        if (retryCountDelta.GetValueOrDefault() > 0)
        {
            _ = transaction.HashIncrementAsync(_workerStateKey, "retry_count_total", retryCountDelta.Value);
        }

        if (deadLetterDelta.GetValueOrDefault() > 0)
        {
            _ = transaction.HashIncrementAsync(_workerStateKey, "dead_letter_count", deadLetterDelta.Value);
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
}
