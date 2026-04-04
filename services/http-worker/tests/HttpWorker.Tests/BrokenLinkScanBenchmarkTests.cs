using System.Diagnostics;
using System.Text.Json;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using Xunit;

namespace HttpWorker.Tests;

public sealed class BrokenLinkScanBenchmarkTests
{
    [Fact]
    public async Task ReportsBenchmarkMetricsForBrokenLinkScan()
    {
        if (!string.Equals(
            Environment.GetEnvironmentVariable("HTTPWORKER_RUN_BENCHMARKS"),
            "1",
            StringComparison.Ordinal))
        {
            return;
        }

        const int datasetSize = 1000;
        var workload = new BrokenLinkScanWorkload();
        var existingRecords = new Dictionary<(int SourceContentId, string Url), BrokenLinkExistingRecord>();

        for (var index = 0; index < datasetSize; index++)
        {
            string url;
            if (index < 100)
            {
                url = $"https://forum.example.com/broken/{index}";
            }
            else if (index < 200)
            {
                url = $"https://forum.example.com/redirect/{index}";
            }
            else if (index < 300)
            {
                url = $"https://forum.example.com/fixed/{index}";
            }
            else
            {
                url = $"https://forum.example.com/ok/{index}";
            }

            workload.Items.Add(new BrokenLinkUrlRequest
            {
                SourceContentId = 7700,
                Url = url,
            });

            if (index is >= 200 and < 300)
            {
                existingRecords[(7700, url)] = new BrokenLinkExistingRecord
                {
                    BrokenLinkId = Guid.NewGuid(),
                    SourceContentId = 7700,
                    Url = url,
                    Status = "open",
                    Notes = "benchmark existing issue",
                };
            }
        }

        var store = new BenchmarkPostgresRuntimeStore(workload, existingRecords);
        var progress = new BenchmarkProgressStreamService();
        var service = new BrokenLinkScanService(new BenchmarkBrokenLinkService(), store, progress);

        var stopwatch = Stopwatch.StartNew();
        var result = await service.ExecuteAsync(
            "benchmark-csharp-broken-links",
            new BrokenLinkScanRequest
            {
                AllowedDomains = ["forum.example.com"],
                BatchSize = 250,
                TimeoutSeconds = 10,
                MaxConcurrency = 40,
            },
            CancellationToken.None);
        stopwatch.Stop();

        var metrics = new
        {
            lane = "broken_link_scan",
            owner = "csharp_http_worker",
            dataset_size = datasetSize,
            wall_time_ms = Math.Round(stopwatch.Elapsed.TotalMilliseconds, 2),
            peak_working_set_bytes = Process.GetCurrentProcess().PeakWorkingSet64,
            throughput_urls_per_second = Math.Round(datasetSize / Math.Max(stopwatch.Elapsed.TotalSeconds, 0.001), 2),
            scanned_urls = result.ScannedUrls,
            flagged_urls = result.FlaggedUrls,
            fixed_urls = result.FixedUrls,
        };
        Console.WriteLine($"BROKEN_LINK_BENCHMARK_JSON:{JsonSerializer.Serialize(metrics)}");

        Assert.Equal(datasetSize, result.ScannedUrls);
        Assert.Equal(200, result.FlaggedUrls);
        Assert.Equal(100, result.FixedUrls);
        Assert.Equal(200, store.Mutations.Count(static mutation => mutation.Status == "open" || mutation.Status == "ignored"));
        Assert.Equal(100, store.Mutations.Count(static mutation => mutation.Status == "fixed"));
        Assert.NotEmpty(progress.Payloads);
    }
}

internal sealed class BenchmarkBrokenLinkService : IBrokenLinkService
{
    public Task<BrokenLinkCheckResponse> CheckAsync(BrokenLinkCheckRequest request, CancellationToken cancellationToken)
    {
        var response = new BrokenLinkCheckResponse
        {
            Checked = request.Urls?.Select(static item =>
            {
                var (httpStatus, redirectUrl) = ResolveResult(item.Url);
                return new BrokenLinkCheckItem
                {
                    SourceContentId = item.SourceContentId,
                    Url = item.Url,
                    HttpStatus = httpStatus,
                    RedirectUrl = redirectUrl,
                    CheckedAt = DateTimeOffset.UtcNow,
                };
            }).ToList() ?? [],
        };
        response.TotalChecked = response.Checked.Count;
        response.TotalFlagged = response.Checked.Count(static item =>
            item.HttpStatus == 0 ||
            item.HttpStatus >= 400 ||
            !string.IsNullOrEmpty(item.RedirectUrl));
        return Task.FromResult(response);
    }

    private static (int HttpStatus, string RedirectUrl) ResolveResult(string url)
    {
        if (url.Contains("/broken/", StringComparison.Ordinal))
        {
            return (404, string.Empty);
        }

        if (url.Contains("/redirect/", StringComparison.Ordinal))
        {
            return (301, url.Replace("/redirect/", "/redirected/", StringComparison.Ordinal));
        }

        return (200, string.Empty);
    }
}

internal sealed class BenchmarkPostgresRuntimeStore(
    BrokenLinkScanWorkload workload,
    Dictionary<(int SourceContentId, string Url), BrokenLinkExistingRecord> existingRecords)
    : IPostgresRuntimeStore
{
    public List<BrokenLinkBatchMutation> Mutations { get; } = [];

    public Task<bool> CanConnectAsync(CancellationToken cancellationToken) => Task.FromResult(true);

    public Task<BrokenLinkScanWorkload> LoadBrokenLinkScanWorkloadAsync(
        BrokenLinkScanRequest request,
        CancellationToken cancellationToken)
    {
        return Task.FromResult(workload);
    }

    public Task<Dictionary<(int SourceContentId, string Url), BrokenLinkExistingRecord>> LoadExistingBrokenLinkRecordsAsync(
        IReadOnlyList<BrokenLinkUrlRequest> items,
        CancellationToken cancellationToken)
    {
        return Task.FromResult(existingRecords);
    }

    public Task PersistBrokenLinkBatchAsync(
        IReadOnlyList<BrokenLinkBatchMutation> mutations,
        CancellationToken cancellationToken)
    {
        Mutations.AddRange(mutations);
        return Task.CompletedTask;
    }

    public Task<int> GetEnabledPeriodicTaskCountAsync(CancellationToken cancellationToken) => Task.FromResult(0);

    public Task<IReadOnlyList<PeriodicTaskRecord>> LoadEnabledPeriodicTasksAsync(CancellationToken cancellationToken)
        => Task.FromResult<IReadOnlyList<PeriodicTaskRecord>>([]);

    public Task MarkPeriodicTaskTriggeredAsync(int periodicTaskId, DateTimeOffset triggeredAt, CancellationToken cancellationToken)
        => Task.CompletedTask;

    public Task<List<GSCDailyMetrics>> GetPagePerformanceAsync(string pageUrl, DateTime startDate, DateTime endDate, CancellationToken cancellationToken)
        => Task.FromResult(new List<GSCDailyMetrics>());

    public Task<List<GSCDailyMetrics>> GetGlobalPerformanceAsync(DateTime startDate, DateTime endDate, string propertyUrl, CancellationToken cancellationToken)
        => Task.FromResult(new List<GSCDailyMetrics>());

    public Task<IReadOnlyList<int>> PersistImportNodesAsync(IReadOnlyList<ImportContentMutation> mutations, CancellationToken cancellationToken)
        => Task.FromResult<IReadOnlyList<int>>([]);

    public Task<List<(int ScopePk, int ExternalScopeId, string ScopeType)>> GetScopesAsync(IReadOnlyList<int> scopePks, CancellationToken cancellationToken)
        => Task.FromResult(new List<(int ScopePk, int ExternalScopeId, string ScopeType)>());

    public Task<IReadOnlyList<HostNode>> GetHostNodesAsync(List<int> scopeIds, CancellationToken cancellationToken)
        => Task.FromResult<IReadOnlyList<HostNode>>([]);

    public Task<IReadOnlyList<DestinationNode>> GetDestinationNodesAsync(List<int> destScopeIds, CancellationToken cancellationToken)
        => Task.FromResult<IReadOnlyList<DestinationNode>>([]);

    public Task PersistPipelineSuggestionsAsync(string runId, IReadOnlyList<PipelineSuggestion> suggestions, CancellationToken cancellationToken)
        => Task.CompletedTask;
}

internal sealed class BenchmarkProgressStreamService : IProgressStreamService
{
    public List<JsonElement> Payloads { get; } = [];

    public Task PublishAsync(string jobId, object payload, CancellationToken cancellationToken)
    {
        Payloads.Add(JsonSerializer.SerializeToElement(payload));
        return Task.CompletedTask;
    }
}
