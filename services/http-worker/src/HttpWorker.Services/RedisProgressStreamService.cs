using System.Text.Json;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Options;
using StackExchange.Redis;

namespace HttpWorker.Services;

public sealed class RedisProgressStreamService : IProgressStreamService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly IDatabase _database;
    private readonly HttpWorkerOptions _options;

    public RedisProgressStreamService(
        ConnectionMultiplexer connection,
        IOptions<HttpWorkerOptions> options)
    {
        _database = connection.GetDatabase();
        _options = options.Value;
    }

    public async Task PublishAsync(
        string jobId,
        object payload,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(jobId))
        {
            return;
        }

        var streamKey = $"{_options.Progress.StreamPrefix}:{jobId}";
        var jsonPayload = JsonSerializer.Serialize(payload, JsonOptions);
        await _database.StreamAddAsync(
            streamKey,
            [new NameValueEntry("payload", jsonPayload)],
            maxLength: _options.Progress.MaxLen,
            useApproximateMaxLength: true);
        await _database.KeyExpireAsync(streamKey, TimeSpan.FromSeconds(_options.Progress.StreamTtlSeconds));
    }
}
