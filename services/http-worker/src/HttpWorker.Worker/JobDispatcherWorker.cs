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
    IOptions<HttpWorkerOptions> options,
    ILogger<JobDispatcherWorker> logger) : BackgroundService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly HttpWorkerOptions _options = options.Value;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
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
                await jobQueueService.WriteResultAsync(result, cancellationToken);
                return;
            }
            catch (ValidationException ex)
            {
                if (parsedRequest is not null)
                {
                    await jobQueueService.WriteResultAsync(new JobResult
                    {
                        SchemaVersion = _options.SchemaVersion,
                        JobId = parsedRequest.JobId,
                        JobType = parsedRequest.JobType,
                        CompletedAt = DateTimeOffset.UtcNow,
                        Success = false,
                        Error = ex.Message,
                        Results = null,
                    }, cancellationToken);
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

                await jobQueueService.WriteResultAsync(new JobResult
                {
                    SchemaVersion = _options.SchemaVersion,
                    JobId = parsedRequest.JobId,
                    JobType = parsedRequest.JobType,
                    CompletedAt = DateTimeOffset.UtcNow,
                    Success = false,
                    Error = "blocked url",
                    Results = null,
                }, cancellationToken);
                return;
            }
            catch (MalformedSitemapException)
            {
                if (parsedRequest is null)
                {
                    await WriteDeadLetterAsync(rawJob, attempt, "malformed sitemap xml", cancellationToken);
                    return;
                }

                await jobQueueService.WriteResultAsync(new JobResult
                {
                    SchemaVersion = _options.SchemaVersion,
                    JobId = parsedRequest.JobId,
                    JobType = parsedRequest.JobType,
                    CompletedAt = DateTimeOffset.UtcNow,
                    Success = false,
                    Error = "malformed sitemap xml",
                    Results = null,
                }, cancellationToken);
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

        await jobQueueService.WriteDeadLetterAsync(new DeadLetterRecord
        {
            SchemaVersion = parsedRequest?.SchemaVersion ?? _options.SchemaVersion,
            JobId = parsedRequest?.JobId ?? Guid.Empty.ToString(),
            JobType = parsedRequest?.JobType ?? "unknown",
            FailedAt = DateTimeOffset.UtcNow,
            AttemptCount = attemptCount,
            Error = error,
            OriginalRequest = originalRequest,
        }, cancellationToken);
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
}
