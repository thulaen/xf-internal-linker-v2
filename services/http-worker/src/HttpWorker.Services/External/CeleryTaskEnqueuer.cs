using System;
using System.Text;
using System.Text.Json;
using StackExchange.Redis;

namespace HttpWorker.Services.External;

public class CeleryTaskEnqueuer
{
    private readonly ConnectionMultiplexer _redis;
    private readonly string _queueName;

    public CeleryTaskEnqueuer(ConnectionMultiplexer redis, string queueName = "celery")
    {
        _redis = redis;
        _queueName = queueName;
    }

    public async Task EnqueueClusterItemsAsync(IEnumerable<int> itemIds)
    {
        var taskName = "content.cluster_items";
        var id = Guid.NewGuid().ToString();

        // args = ( [1, 2, 3], ) -> tuple of list
        var args = new object[] { itemIds };
        var kwargs = new { };
        var options = new { };

        // body goes in JSON array: [args, kwargs, options]
        var bodyArray = new object[] { args, kwargs, options };
        var bodyJson = JsonSerializer.Serialize(bodyArray);
        var bodyBase64 = Convert.ToBase64String(Encoding.UTF8.GetBytes(bodyJson));

        var envelope = new
        {
            body = bodyBase64,
            content_encoding = "utf-8",
            content_type = "application/json",
            headers = new
            {
                lang = "py",
                task = taskName,
                id = id,
                root_id = id,
                retries = 0
            },
            properties = new
            {
                correlation_id = id,
                reply_to = Guid.NewGuid().ToString(),
                delivery_mode = 2,
                delivery_info = new { exchange = "", routing_key = _queueName },
                priority = 0,
                body_encoding = "base64",
                delivery_tag = Guid.NewGuid().ToString()
            }
        };

        var envelopeJson = JsonSerializer.Serialize(envelope);
        var db = _redis.GetDatabase();

        // Celery reads from a Redis list typically named 'celery'
        await db.ListLeftPushAsync(_queueName, envelopeJson);
    }
}
