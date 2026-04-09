using System.Text.Json;
using HttpWorker.Api.Controllers.V1;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using HttpWorker.Services.Analytics;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using NSubstitute;
using Xunit;

namespace HttpWorker.Tests;

public sealed class JobsControllerTests
{
    private static readonly JsonSerializerOptions JsonOpts = new(JsonSerializerDefaults.Web);

    private static JobRequest ValidRequest(string jobType = "health_check") => new()
    {
        SchemaVersion = "v1",
        JobId = Guid.NewGuid().ToString(),
        JobType = jobType,
        CreatedAt = DateTimeOffset.UtcNow,
        Payload = JsonSerializer.SerializeToElement(new { urls = Array.Empty<string>(), timeout_seconds = 5, max_concurrency = 1 }, JsonOpts),
    };

    private static JobProcessor CreateJobProcessor(
        IHealthCheckService? healthCheckService = null,
        IGraphSyncService? graphSyncService = null)
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
            healthCheckService ?? Substitute.For<IHealthCheckService>(),
            Substitute.For<ISitemapService>(),
            Substitute.For<ICrawlSessionService>(),
            gscService,
            Substitute.For<IImportContentService>(),
            Substitute.For<IRunPipelineService>(),
            weightTuner,
            graphSyncService ?? Substitute.For<IGraphSyncService>(),
            options);
    }

    [Fact]
    public async Task SubmitAsync_DefaultAsync_QueuesJobAndReturns202()
    {
        var queue = Substitute.For<IJobQueueService>();
        var controller = new JobsController(queue, CreateJobProcessor());
        var request = ValidRequest();

        var action = await controller.SubmitAsync(request, sync: false, CancellationToken.None);

        Assert.IsType<AcceptedResult>(action);
        await queue.Received(1).QueueJobAsync(request, Arg.Any<CancellationToken>());
    }

    [Fact]
    public async Task SubmitAsync_SyncTrue_ProcessesInlineAndReturns200()
    {
        var healthCheck = Substitute.For<IHealthCheckService>();
        healthCheck.CheckAsync(Arg.Any<HealthCheckRequest>(), Arg.Any<CancellationToken>())
            .Returns(new HealthCheckResponse { Checked = [], TotalChecked = 0 });

        var queue = Substitute.For<IJobQueueService>();
        var controller = new JobsController(queue, CreateJobProcessor(healthCheck));
        var request = ValidRequest("health_check");

        var action = await controller.SubmitAsync(request, sync: true, CancellationToken.None);

        var ok = Assert.IsType<OkObjectResult>(action);
        var result = Assert.IsType<JobResult>(ok.Value);
        Assert.True(result.Success);
        Assert.Equal("health_check", result.JobType);
        await queue.DidNotReceive().QueueJobAsync(Arg.Any<JobRequest>(), Arg.Any<CancellationToken>());
    }

    [Fact]
    public async Task SubmitAsync_InvalidRequest_Returns500()
    {
        var queue = Substitute.For<IJobQueueService>();
        var controller = new JobsController(queue, CreateJobProcessor());

        var action = await controller.SubmitAsync(null, sync: false, CancellationToken.None);

        var status = Assert.IsType<ObjectResult>(action);
        Assert.Equal(500, status.StatusCode);
    }
}
