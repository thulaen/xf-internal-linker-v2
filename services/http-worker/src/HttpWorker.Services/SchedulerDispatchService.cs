using System.Net.Http.Json;
using System.Text.Json;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace HttpWorker.Services;

public sealed class SchedulerDispatchService(
    IHttpClientFactory httpClientFactory,
    IOptions<HttpWorkerOptions> options,
    ILogger<SchedulerDispatchService> logger) : ISchedulerDispatchService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly HttpWorkerOptions _options = options.Value;

    public async Task<bool> DispatchAsync(PeriodicTaskRecord task, CancellationToken cancellationToken)
    {
        var baseUrl = (_options.Scheduler.ControlPlaneBaseUrl ?? string.Empty).Trim().TrimEnd('/');
        if (string.IsNullOrWhiteSpace(baseUrl))
        {
            logger.LogWarning("C# scheduler cannot dispatch task {TaskName} because the Django control plane URL is missing", task.Name);
            return false;
        }

        if (string.IsNullOrWhiteSpace(_options.Scheduler.ControlPlaneToken))
        {
            logger.LogWarning("C# scheduler cannot dispatch task {TaskName} because the scheduler control token is missing", task.Name);
            return false;
        }

        Dictionary<string, object?>? kwargs;
        try
        {
            kwargs = JsonSerializer.Deserialize<Dictionary<string, object?>>(task.KwargsJson, JsonOptions) ?? [];
        }
        catch (JsonException ex)
        {
            logger.LogWarning(ex, "C# scheduler could not parse kwargs JSON for periodic task {TaskName}", task.Name);
            return false;
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, $"{baseUrl}/api/system/status/internal/scheduler/dispatch/")
        {
            Content = JsonContent.Create(new
            {
                task = task.Task,
                kwargs,
                periodic_task_id = task.Id,
                periodic_task_name = task.Name,
            }),
        };
        request.Headers.Add("X-Scheduler-Token", _options.Scheduler.ControlPlaneToken);

        var client = httpClientFactory.CreateClient("http-worker");
        using var response = await client.SendAsync(request, cancellationToken);
        if (response.IsSuccessStatusCode)
        {
            return true;
        }

        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        logger.LogWarning(
            "C# scheduler dispatch failed for periodic task {TaskName} with status {StatusCode}: {Body}",
            task.Name,
            (int)response.StatusCode,
            body);
        return false;
    }
}
