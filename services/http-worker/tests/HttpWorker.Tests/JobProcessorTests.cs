using System.Text.Json;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using HttpWorker.Services.Analytics;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using NSubstitute;
using Xunit;

namespace HttpWorker.Tests;

public sealed class JobProcessorTests
{
    private static readonly JsonSerializerOptions JsonOpts = new(JsonSerializerDefaults.Web);

    private static JobProcessor CreateProcessor(IGraphSyncService graphSync)
    {
        var store = Substitute.For<IPostgresRuntimeStore>();
        var gscService = new GSCAttributionService(store, NullLogger<GSCAttributionService>.Instance);
        var options = Options.Create(new HttpWorkerOptions());
        var collector = new WeightTunerDataCollector(options, NullLogger<WeightTunerDataCollector>.Instance);
        var weightTuner = new WeightTunerService(collector, options, Substitute.For<IHttpClientFactory>(), NullLogger<WeightTunerService>.Instance);

        return new JobProcessor(
            Substitute.For<IBrokenLinkService>(),
            Substitute.For<IBrokenLinkScanService>(),
            Substitute.For<IUrlFetchService>(),
            Substitute.For<IHealthCheckService>(),
            Substitute.For<ISitemapService>(),
            gscService,
            Substitute.For<IImportContentService>(),
            Substitute.For<IRunPipelineService>(),
            weightTuner,
            graphSync,
            options);
    }

    [Fact]
    public async Task ProcessAsync_GraphSyncContent_DispatchesToService()
    {
        var graphSync = Substitute.For<IGraphSyncService>();
        graphSync.SyncContentAsync(Arg.Any<GraphSyncContentRequest>(), Arg.Any<CancellationToken>())
            .Returns(new GraphSyncResponse { ActiveLinks = 5 });

        var processor = CreateProcessor(graphSync);
        var request = new JobRequest
        {
            SchemaVersion = "v1",
            JobId = Guid.NewGuid().ToString(),
            JobType = "graph_sync_content",
            CreatedAt = DateTimeOffset.UtcNow,
            Payload = JsonSerializer.SerializeToElement(new GraphSyncContentRequest { ContentId = 1, ContentType = "thread" }, JsonOpts)
        };

        var result = await processor.ProcessAsync(request, CancellationToken.None);

        Assert.True(result.Success);
        Assert.Equal("graph_sync_content", result.JobType);
        await graphSync.Received(1).SyncContentAsync(Arg.Any<GraphSyncContentRequest>(), Arg.Any<CancellationToken>());
    }

    [Fact]
    public async Task ProcessAsync_GraphSyncRefresh_DispatchesToService()
    {
        var graphSync = Substitute.For<IGraphSyncService>();
        graphSync.RefreshAsync(Arg.Any<GraphSyncRefreshRequest>(), Arg.Any<CancellationToken>())
            .Returns(new GraphSyncResponse { RefreshedItems = 10 });

        var processor = CreateProcessor(graphSync);
        var request = new JobRequest
        {
            SchemaVersion = "v1",
            JobId = Guid.NewGuid().ToString(),
            JobType = "graph_sync_refresh",
            CreatedAt = DateTimeOffset.UtcNow,
            Payload = JsonSerializer.SerializeToElement(new GraphSyncRefreshRequest { ContentItemPks = [1, 2, 3] }, JsonOpts)
        };

        var result = await processor.ProcessAsync(request, CancellationToken.None);

        Assert.True(result.Success);
        Assert.Equal("graph_sync_refresh", result.JobType);
        await graphSync.Received(1).RefreshAsync(Arg.Any<GraphSyncRefreshRequest>(), Arg.Any<CancellationToken>());
    }
}
