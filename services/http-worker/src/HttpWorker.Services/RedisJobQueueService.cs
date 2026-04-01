using System.Text.Json;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Options;
using StackExchange.Redis;

namespace HttpWorker.Services;

public sealed class RedisJobQueueService : IJobQueueService
{
    private const int QueuedMarkerTtlSeconds = 3600;
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly IDatabase _database;
    private readonly HttpWorkerOptions _options;

    public RedisJobQueueService(
        ConnectionMultiplexer connection,
        IOptions<HttpWorkerOptions> options)
    {
        _options = options.Value;
        _database = connection.GetDatabase();
    }

    public async Task QueueJobAsync(JobRequest request, CancellationToken cancellationToken)
    {
        var payload = JsonSerializer.Serialize(request, JsonOptions);
        await _database.StringSetAsync(GetQueuedMarkerKey(request.JobId), "1", TimeSpan.FromSeconds(QueuedMarkerTtlSeconds));
        await _database.ListLeftPushAsync(_options.Redis.JobQueueKey, payload);
    }

    public async Task<string?> PopRawJobAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            var result = await _database.ExecuteAsync("BRPOP", _options.Redis.JobQueueKey, "5");
            if (result.IsNull)
            {
                continue;
            }

            var values = (RedisResult[])result!;
            if (values.Length == 2)
            {
                return values[1].ToString();
            }
        }

        return null;
    }

    public async Task<JobResult?> GetResultAsync(string jobId, CancellationToken cancellationToken)
    {
        var value = await _database.StringGetAsync(GetResultKey(jobId));
        return value.IsNullOrEmpty ? null : JsonSerializer.Deserialize<JobResult>(value!, JsonOptions);
    }

    public async Task<DeadLetterRecord?> GetDeadLetterAsync(string jobId, CancellationToken cancellationToken)
    {
        var value = await _database.StringGetAsync(GetDeadKey(jobId));
        return value.IsNullOrEmpty ? null : JsonSerializer.Deserialize<DeadLetterRecord>(value!, JsonOptions);
    }

    public Task<bool> HasQueuedMarkerAsync(string jobId, CancellationToken cancellationToken)
    {
        return _database.KeyExistsAsync(GetQueuedMarkerKey(jobId));
    }

    public async Task WriteResultAsync(JobResult result, CancellationToken cancellationToken)
    {
        var payload = JsonSerializer.Serialize(result, JsonOptions);
        var transaction = _database.CreateTransaction();
        _ = transaction.StringSetAsync(
            GetResultKey(result.JobId),
            payload,
            TimeSpan.FromSeconds(_options.Redis.ResultTtlSeconds));
        _ = transaction.KeyDeleteAsync(GetQueuedMarkerKey(result.JobId));
        await transaction.ExecuteAsync();
    }

    public async Task WriteDeadLetterAsync(DeadLetterRecord deadLetter, CancellationToken cancellationToken)
    {
        var payload = JsonSerializer.Serialize(deadLetter, JsonOptions);
        var transaction = _database.CreateTransaction();
        _ = transaction.StringSetAsync(
            GetDeadKey(deadLetter.JobId),
            payload,
            TimeSpan.FromSeconds(_options.Redis.DeadLetterTtlSeconds));
        _ = transaction.KeyDeleteAsync(GetQueuedMarkerKey(deadLetter.JobId));
        await transaction.ExecuteAsync();
    }

    public async Task DeleteQueuedMarkerAsync(string jobId, CancellationToken cancellationToken)
    {
        await _database.KeyDeleteAsync(GetQueuedMarkerKey(jobId));
    }

    public async Task<bool> IsRedisConnectedAsync(CancellationToken cancellationToken)
    {
        var result = await _database.ExecuteAsync("PING");
        return string.Equals(result.ToString(), "PONG", StringComparison.OrdinalIgnoreCase);
    }

    public async Task<long> GetQueueDepthAsync(CancellationToken cancellationToken)
    {
        return await _database.ListLengthAsync(_options.Redis.JobQueueKey);
    }

    private static string GetQueuedMarkerKey(string jobId) => $"http_worker:queued:{jobId}";

    private static string GetResultKey(string jobId) => $"http_worker:results:{jobId}";

    private static string GetDeadKey(string jobId) => $"http_worker:dead:{jobId}";
}
