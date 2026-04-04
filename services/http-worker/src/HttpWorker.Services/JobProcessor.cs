using System.Text.Json;
using System.Text.Json.Nodes;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services.Analytics;
using Microsoft.Extensions.Options;

namespace HttpWorker.Services;

public sealed class JobProcessor(
    IBrokenLinkService brokenLinkService,
    IBrokenLinkScanService brokenLinkScanService,
    IUrlFetchService urlFetchService,
    IHealthCheckService healthCheckService,
    ISitemapService sitemapService,
    GSCAttributionService gscAttributionService,
    IImportContentService importContentService,
    IRunPipelineService runPipelineService,
    WeightTunerService weightTunerService,
    IOptions<HttpWorkerOptions> options)
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly HttpWorkerOptions _options = options.Value;

    public async Task<JobResult> ProcessAsync(JobRequest request, CancellationToken cancellationToken)
    {
        ValidateJobRequest(request);

        try
        {
            JsonNode? results = request.JobType switch
            {
                "broken_link_scan" => JsonSerializer.SerializeToNode(
                    await brokenLinkScanService.ExecuteAsync(
                        request.JobId,
                        DeserializePayload<BrokenLinkScanRequest>(request.Payload),
                        cancellationToken),
                    JsonOptions),
                "broken_link_check" => JsonSerializer.SerializeToNode(
                    await brokenLinkService.CheckAsync(
                        DeserializePayload<BrokenLinkCheckRequest>(request.Payload),
                        cancellationToken),
                    JsonOptions),
                "url_fetch" => JsonSerializer.SerializeToNode(
                    await urlFetchService.FetchAsync(
                        DeserializePayload<UrlFetchRequest>(request.Payload),
                        cancellationToken),
                    JsonOptions),
                "health_check" => JsonSerializer.SerializeToNode(
                    await healthCheckService.CheckAsync(
                        DeserializePayload<HealthCheckRequest>(request.Payload),
                        cancellationToken),
                    JsonOptions),
                "sitemap_crawl" => JsonSerializer.SerializeToNode(
                    await sitemapService.CrawlAsync(
                        DeserializePayload<SitemapCrawlRequest>(request.Payload),
                        cancellationToken),
                    JsonOptions),
                "gsc_attribution" => JsonSerializer.SerializeToNode(
                    await gscAttributionService.AnalyzeUpliftAsync(
                        DeserializePayload<GSCAttributionJobPayload>(request.Payload),
                        cancellationToken),
                    JsonOptions),
                "import_content" => JsonSerializer.SerializeToNode(
                    await importContentService.ExecuteAsync(
                         request.JobId,
                         DeserializePayload<ImportContentRequest>(request.Payload),
                         cancellationToken),
                    JsonOptions),
                "run_pipeline" => JsonSerializer.SerializeToNode(
                    await runPipelineService.ExecuteAsync(
                         request.JobId,
                         DeserializePayload<RunPipelineRequest>(request.Payload),
                         cancellationToken),
                    JsonOptions),
                "weight_tune" => JsonSerializer.SerializeToNode(
                    await weightTunerService.RunAsync(
                         DeserializePayload<WeightTuneRequest>(request.Payload),
                         cancellationToken),
                    JsonOptions),
                _ => throw new Exception("unknown job_type"),
            };

            return new JobResult
            {
                SchemaVersion = _options.SchemaVersion,
                JobId = request.JobId,
                JobType = request.JobType,
                CompletedAt = DateTimeOffset.UtcNow,
                Success = true,
                Error = null,
                Results = results,
            };
        }
        catch (BlockedUrlException)
        {
            return Failure(request, "blocked url");
        }
        catch (MalformedSitemapException)
        {
            return Failure(request, "malformed sitemap xml");
        }
        catch (Exception ex)
        {
            return Failure(request, ex.Message);
        }
    }

    public void ValidateJobRequest(JobRequest? request)
    {
        if (request is null)
        {
            throw new Exception("request body is required");
        }

        if (!string.Equals(request.SchemaVersion, _options.SchemaVersion, StringComparison.Ordinal))
        {
            throw new Exception("unknown schema_version");
        }

        if (string.IsNullOrWhiteSpace(request.JobId) || !Guid.TryParse(request.JobId, out _))
        {
            throw new Exception("job_id must be a valid uuid");
        }

        if (request.CreatedAt == default)
        {
            throw new Exception("created_at is required");
        }

        if (request.Payload.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
        {
            throw new Exception("payload is required");
        }

        if (request.JobType is not ("broken_link_scan" or "broken_link_check" or "url_fetch" or "health_check" or "sitemap_crawl" or "gsc_attribution" or "import_content" or "run_pipeline" or "weight_tune"))
        {
            throw new Exception("unknown job_type");
        }
    }

    private static T DeserializePayload<T>(JsonElement payload)
    {
        return payload.Deserialize<T>(JsonOptions) ?? throw new Exception("payload is required");
    }

    private JobResult Failure(JobRequest request, string error)
    {
        return new JobResult
        {
            SchemaVersion = _options.SchemaVersion,
            JobId = request.JobId,
            JobType = request.JobType,
            CompletedAt = DateTimeOffset.UtcNow,
            Success = false,
            Error = error,
            Results = null,
        };
    }
}
