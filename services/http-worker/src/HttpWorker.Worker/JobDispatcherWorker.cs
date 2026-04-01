using System.Text.Json;
using System.Text.Json.Nodes;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace HttpWorker.Worker;

public sealed class JobDispatcherWorker(
    IJobQueueService jobQueueService,
    JobProcessor jobProcessor,
    IRuntimeTelemetryService runtimeTelemetryService,
    IOptions<HttpWorkerOptions> options,
    ILogger<JobDispatcherWorker> logger) : BackgroundService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly HttpWorkerOptions _options = options.Value;
    private readonly string _instanceId = Guid.NewGuid().ToString("N");
    private readonly DateTimeOffset _startedAt = DateTimeOffset.UtcNow;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var heartbeatTask = RunHeartbeatLoopAsync(stoppingToken);
        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                var rawJob = await jobQueueService.PopRawJobAsync(stoppingToken);
                if (string.IsNullOrWhiteSpace(rawJob))
                {
                    continue;
                }

                await ProcessRawJobAsync(rawJob, stoppingToken);
            }
        }
        finally
        {
            await heartbeatTask;
        }
    }

    private async Task ProcessRawJobAsync(string rawJob, CancellationToken cancellationToken)
    {
        JobRequest? parsedRequest = null;

        for (var attempt = 1; attempt <= 4; attempt++)
        {
            try
            {
                parsedRequest ??= JsonSerializer.Deserialize<JobRequest>(rawJob, JsonOptions)
                    ?? throw new ValidationException("request body is required");
                var result = await jobProcessor.ProcessAsync(parsedRequest, cancellationToken);
                await WriteResultAsync(result, attempt - 1, cancellationToken);
                return;
            }
            catch (ValidationException ex)
            {
                if (parsedRequest is not null)
                {
                    await WriteResultAsync(new JobResult
                    {
                        SchemaVersion = _options.SchemaVersion,
                        JobId = parsedRequest.JobId,
                        JobType = parsedRequest.JobType,
                        CompletedAt = DateTimeOffset.UtcNow,
                        Success = false,
                        Error = ex.Message,
                        Results = null,
                    }, attempt - 1, cancellationToken);
                    return;
                }

                await WriteDeadLetterAsync(rawJob, attempt, ex.Message, cancellationToken);
                return;
            }
            catch (BlockedUrlException)
            {
                if (parsedRequest is null)
                {
                    await WriteDeadLetterAsync(rawJob, attempt, "blocked url", cancellationToken);
                    return;
                }

                await WriteResultAsync(new JobResult
                {
                    SchemaVersion = _options.SchemaVersion,
                    JobId = parsedRequest.JobId,
                    JobType = parsedRequest.JobType,
                    CompletedAt = DateTimeOffset.UtcNow,
                    Success = false,
                    Error = "blocked url",
                    Results = null,
                }, attempt - 1, cancellationToken);
                return;
            }
            catch (MalformedSitemapException)
            {
                if (parsedRequest is null)
                {
                    await WriteDeadLetterAsync(rawJob, attempt, "malformed sitemap xml", cancellationToken);
                    return;
                }

                await WriteResultAsync(new JobResult
                {
                    SchemaVersion = _options.SchemaVersion,
                    JobId = parsedRequest.JobId,
                    JobType = parsedRequest.JobType,
                    CompletedAt = DateTimeOffset.UtcNow,
                    Success = false,
                    Error = "malformed sitemap xml",
                    Results = null,
                }, attempt - 1, cancellationToken);
                return;
            }
            catch (Exception ex) when (attempt < 4)
            {
                logger.LogWarning(ex, "Retrying HttpWorker job attempt {Attempt}", attempt);
                await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken);
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "HttpWorker job failed permanently");
                await WriteDeadLetterAsync(rawJob, 4, ex.Message, cancellationToken, parsedRequest);
                return;
            }
        }
    }

    private async Task WriteDeadLetterAsync(
        string rawJob,
        int attemptCount,
        string error,
        CancellationToken cancellationToken,
        JobRequest? parsedRequest = null)
    {
        parsedRequest ??= TryParseFallback(rawJob);
        JsonNode? originalRequest;
        try
        {
            originalRequest = JsonNode.Parse(rawJob);
        }
        catch
        {
            originalRequest = JsonValue.Create(rawJob);
        }

        var deadLetter = new DeadLetterRecord
        {
            SchemaVersion = parsedRequest?.SchemaVersion ?? _options.SchemaVersion,
            JobId = parsedRequest?.JobId ?? Guid.Empty.ToString(),
            JobType = parsedRequest?.JobType ?? "unknown",
            FailedAt = DateTimeOffset.UtcNow,
            AttemptCount = attemptCount,
            Error = error,
            OriginalRequest = originalRequest,
        };

        await jobQueueService.WriteDeadLetterAsync(deadLetter, cancellationToken);

        try
        {
            await runtimeTelemetryService.RecordDeadLetterAsync(
                _instanceId,
                _startedAt,
                deadLetter,
                Math.Max(0, attemptCount - 1),
                cancellationToken);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "HttpWorker telemetry write failed for dead-lettered job");
        }
    }

    private static JobRequest? TryParseFallback(string rawJob)
    {
        try
        {
            return JsonSerializer.Deserialize<JobRequest>(rawJob, JsonOptions);
        }
        catch
        {
            return null;
        }
    }

    private async Task WriteResultAsync(
        JobResult result,
        int retryCount,
        CancellationToken cancellationToken)
    {
        await jobQueueService.WriteResultAsync(result, cancellationToken);

        try
        {
            await runtimeTelemetryService.RecordResultAsync(
                _instanceId,
                _startedAt,
                result,
                retryCount,
                cancellationToken);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "HttpWorker telemetry write failed for completed job");
        }
    }

    private async Task RunHeartbeatLoopAsync(CancellationToken stoppingToken)
    {
        await TryWriteHeartbeatAsync(stoppingToken);

        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(5));
        try
        {
            while (await timer.WaitForNextTickAsync(stoppingToken))
            {
                await TryWriteHeartbeatAsync(stoppingToken);
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
        }
    }

    private async Task TryWriteHeartbeatAsync(CancellationToken cancellationToken)
    {
        try
        {
            await runtimeTelemetryService.WriteHeartbeatAsync(_instanceId, _startedAt, cancellationToken);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "HttpWorker heartbeat write failed");
        }
    }
}
