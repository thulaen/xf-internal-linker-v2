using System.Diagnostics;
using System.Text.Json;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using Xunit;

namespace HttpWorker.Tests;

public sealed class GraphSyncBenchmarkTests
{
    [Fact]
    public async Task ReportsBenchmarkMetricsForGraphSyncRefresh()
    {
        if (!string.Equals(
            Environment.GetEnvironmentVariable("HTTPWORKER_RUN_BENCHMARKS"),
            "1",
            StringComparison.Ordinal))
        {
            return;
        }

        const int sourceCount = 250;
        const int linksPerSource = 4;
        var runs = new List<double>();
        var peakWorkingSetBytes = 0L;

        for (var iteration = 0; iteration < 3; iteration++)
        {
            var store = BuildBenchmarkStore(sourceCount, linksPerSource);
            var service = new GraphSyncService(store);
            var stopwatch = Stopwatch.StartNew();
            var result = await service.RefreshAsync(
                new GraphSyncRefreshRequest
                {
                    ForumDomains = ["forum.example.com"],
                },
                CancellationToken.None);
            stopwatch.Stop();

            runs.Add(Math.Round(stopwatch.Elapsed.TotalMilliseconds, 2));
            peakWorkingSetBytes = Math.Max(peakWorkingSetBytes, Process.GetCurrentProcess().PeakWorkingSet64);
            Assert.Equal(sourceCount, result.RefreshedItems);
            Assert.Equal(sourceCount * linksPerSource, result.ActiveLinks);
            Assert.Equal(sourceCount * linksPerSource, result.CreatedLinks);
            Assert.Equal(sourceCount * linksPerSource, result.CreatedFreshnessEdges);
        }

        var sorted = runs.OrderBy(static value => value).ToArray();
        var metrics = new
        {
            lane = "graph_sync",
            owner = "csharp_http_worker",
            dataset_sources = sourceCount,
            links_per_source = linksPerSource,
            wall_time_ms_runs = runs,
            median_wall_time_ms = sorted[1],
            peak_working_set_bytes = peakWorkingSetBytes,
            throughput_links_per_second = Math.Round(
                (sourceCount * linksPerSource) / Math.Max(sorted[1] / 1000.0, 0.001),
                2),
        };
        Console.WriteLine($"GRAPH_SYNC_BENCHMARK_JSON:{JsonSerializer.Serialize(metrics)}");
    }

    private static BenchmarkGraphSyncStore BuildBenchmarkStore(int sourceCount, int linksPerSource)
    {
        var store = new BenchmarkGraphSyncStore();
        for (var destinationId = 1; destinationId <= sourceCount * linksPerSource; destinationId++)
        {
            store.Destinations[(destinationId, "thread")] = new GraphSyncDestination
            {
                ContentItemPk = 10_000 + destinationId,
                ContentId = destinationId,
                ContentType = "thread",
                Url = $"https://forum.example.com/threads/target.{destinationId}",
            };
        }

        for (var sourceIndex = 1; sourceIndex <= sourceCount; sourceIndex++)
        {
            var links = new List<string>();
            for (var offset = 0; offset < linksPerSource; offset++)
            {
                var destinationId = ((sourceIndex - 1) * linksPerSource) + offset + 1;
                links.Add($"[URL=https://forum.example.com/threads/target.{destinationId}/]Target {destinationId}[/URL]");
            }

            store.Sources.Add(new GraphSyncSourceContent
            {
                ContentItemPk = sourceIndex,
                ContentId = 100_000 + sourceIndex,
                ContentType = "thread",
                RawBbcode = string.Join(" ", links),
            });
        }

        return store;
    }
}

internal sealed class BenchmarkGraphSyncStore : IGraphSyncStore
{
    public List<GraphSyncSourceContent> Sources { get; } = [];

    public Dictionary<(int ContentId, string ContentType), GraphSyncDestination> Destinations { get; } = [];

    public Task<IReadOnlyList<GraphSyncSourceContent>> LoadRefreshSourcesAsync(
        IReadOnlyList<int>? contentItemPks,
        CancellationToken cancellationToken)
    {
        return Task.FromResult<IReadOnlyList<GraphSyncSourceContent>>(Sources);
    }

    public Task<Dictionary<(int ContentId, string ContentType), GraphSyncDestination>> LoadDestinationsAsync(
        IReadOnlyCollection<(int ContentId, string ContentType)> keys,
        CancellationToken cancellationToken)
    {
        var selected = new Dictionary<(int ContentId, string ContentType), GraphSyncDestination>();
        foreach (var key in keys)
        {
            if (Destinations.TryGetValue(key, out var destination))
            {
                selected[key] = destination;
            }
        }

        return Task.FromResult(selected);
    }

    public Task<Dictionary<string, GraphSyncDestination>> LoadDestinationsByUrlAsync(
        IReadOnlyCollection<string> normalizedUrls,
        CancellationToken cancellationToken)
    {
        return Task.FromResult(new Dictionary<string, GraphSyncDestination>(StringComparer.Ordinal));
    }

    public Task<GraphSyncSourceState> LoadSourceStateAsync(
        int contentItemPk,
        CancellationToken cancellationToken)
    {
        return Task.FromResult(new GraphSyncSourceState());
    }

    public Task PersistAsync(GraphSyncPersistenceCommand command, CancellationToken cancellationToken)
    {
        return Task.CompletedTask;
    }
}
