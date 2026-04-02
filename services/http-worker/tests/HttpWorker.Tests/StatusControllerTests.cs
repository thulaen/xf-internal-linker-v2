using HttpWorker.Api.Controllers.V1;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;
using Xunit;

namespace HttpWorker.Tests;

public sealed class StatusControllerTests
{
    [Fact]
    public async Task ReturnsHealthyQueueProofWhenWorkerHeartbeatIsFresh()
    {
        var controller = CreateController(
            queueDepth: 7,
            workerSnapshot: new HttpWorkerWorkerSnapshot
            {
                InstanceId = "worker-a",
                StartedAt = DateTimeOffset.UtcNow.AddMinutes(-3),
                HeartbeatAt = DateTimeOffset.UtcNow.AddSeconds(-4),
                RetryCountTotal = 2,
                DeadLetterCount = 1,
                LastCompleted = new HttpWorkerTaskSnapshot
                {
                    JobType = "broken_link_scan",
                    RecordedAt = DateTimeOffset.UtcNow.AddSeconds(-8),
                },
            });

        var action = await controller.GetAsync(CancellationToken.None);

        var ok = Assert.IsType<OkObjectResult>(action.Result);
        var payload = Assert.IsType<HttpWorkerStatusResponse>(ok.Value);
        Assert.Equal("ok", payload.Status);
        Assert.True(payload.RedisConnected);
        Assert.Equal(7, payload.QueueDepth);
        Assert.True(payload.WorkerOnline);
        Assert.NotNull(payload.Worker);
        Assert.Equal("worker-a", payload.Worker!.InstanceId);
        Assert.Equal(2, payload.Worker.RetryCountTotal);
        Assert.Equal(1, payload.Worker.DeadLetterCount);
    }

    [Fact]
    public async Task MarksWorkerOfflineWhenHeartbeatIsStale()
    {
        var controller = CreateController(
            queueDepth: 3,
            workerSnapshot: new HttpWorkerWorkerSnapshot
            {
                InstanceId = "worker-b",
                StartedAt = DateTimeOffset.UtcNow.AddMinutes(-10),
                HeartbeatAt = DateTimeOffset.UtcNow.AddSeconds(-40),
            });

        var action = await controller.GetAsync(CancellationToken.None);

        var ok = Assert.IsType<OkObjectResult>(action.Result);
        var payload = Assert.IsType<HttpWorkerStatusResponse>(ok.Value);
        Assert.Equal("degraded", payload.Status);
        Assert.True(payload.RedisConnected);
        Assert.False(payload.WorkerOnline);
        Assert.NotNull(payload.WorkerHeartbeatAgeSeconds);
        Assert.True(payload.WorkerHeartbeatAgeSeconds > 15);
    }

    private static StatusController CreateController(
        long queueDepth,
        HttpWorkerWorkerSnapshot? workerSnapshot)
    {
        return new StatusController(
            new FakeJobQueueService
            {
                RedisConnected = true,
                QueueDepth = queueDepth,
            },
            new FakePostgresRuntimeStore
            {
                DatabaseConnected = true,
            },
            new FakeRuntimeTelemetryService
            {
                Snapshot = workerSnapshot,
            },
            Options.Create(new HttpWorkerOptions
            {
                SchemaVersion = "v1",
            }));
    }
}

internal sealed class FakeJobQueueService : IJobQueueService
{
    public bool RedisConnected { get; set; }

    public long QueueDepth { get; set; }

    public Task QueueJobAsync(JobRequest request, CancellationToken cancellationToken) => Task.CompletedTask;

    public Task<string?> PopRawJobAsync(CancellationToken cancellationToken) => Task.FromResult<string?>(null);

    public Task<JobResult?> GetResultAsync(string jobId, CancellationToken cancellationToken) => Task.FromResult<JobResult?>(null);

    public Task<DeadLetterRecord?> GetDeadLetterAsync(string jobId, CancellationToken cancellationToken) => Task.FromResult<DeadLetterRecord?>(null);

    public Task<bool> HasQueuedMarkerAsync(string jobId, CancellationToken cancellationToken) => Task.FromResult(false);

    public Task WriteResultAsync(JobResult result, CancellationToken cancellationToken) => Task.CompletedTask;

    public Task WriteDeadLetterAsync(DeadLetterRecord deadLetter, CancellationToken cancellationToken) => Task.CompletedTask;

    public Task DeleteQueuedMarkerAsync(string jobId, CancellationToken cancellationToken) => Task.CompletedTask;

    public Task<bool> IsRedisConnectedAsync(CancellationToken cancellationToken) => Task.FromResult(RedisConnected);

    public Task<long> GetQueueDepthAsync(CancellationToken cancellationToken) => Task.FromResult(QueueDepth);
}

internal sealed class FakeRuntimeTelemetryService : IRuntimeTelemetryService
{
    public HttpWorkerWorkerSnapshot? Snapshot { get; set; }

    public Task WriteHeartbeatAsync(string instanceId, DateTimeOffset startedAt, CancellationToken cancellationToken) => Task.CompletedTask;

    public Task RecordResultAsync(string instanceId, DateTimeOffset startedAt, JobResult result, int retryCount, CancellationToken cancellationToken) => Task.CompletedTask;

    public Task RecordDeadLetterAsync(string instanceId, DateTimeOffset startedAt, DeadLetterRecord deadLetter, int retryCount, CancellationToken cancellationToken) => Task.CompletedTask;

    public Task<HttpWorkerWorkerSnapshot?> GetWorkerSnapshotAsync(CancellationToken cancellationToken) => Task.FromResult(Snapshot);

    public Task WriteSchedulerHeartbeatAsync(string instanceId, DateTimeOffset startedAt, string ownershipMode, string status, int enabledPeriodicTasks, string note, CancellationToken cancellationToken) => Task.CompletedTask;

    public Task<HttpWorkerSchedulerSnapshot?> GetSchedulerSnapshotAsync(CancellationToken cancellationToken) => Task.FromResult<HttpWorkerSchedulerSnapshot?>(null);

    public Task<HttpWorkerPerformanceSnapshot> GetPerformanceSnapshotAsync(CancellationToken cancellationToken) => Task.FromResult(new HttpWorkerPerformanceSnapshot());
}

internal sealed class FakePostgresRuntimeStore : IPostgresRuntimeStore
{
    public bool DatabaseConnected { get; set; }

    public Task<bool> CanConnectAsync(CancellationToken cancellationToken) => Task.FromResult(DatabaseConnected);

    public Task<BrokenLinkScanWorkload> LoadBrokenLinkScanWorkloadAsync(BrokenLinkScanRequest request, CancellationToken cancellationToken) => Task.FromResult(new BrokenLinkScanWorkload());

    public Task<Dictionary<(int SourceContentId, string Url), BrokenLinkExistingRecord>> LoadExistingBrokenLinkRecordsAsync(IReadOnlyList<BrokenLinkUrlRequest> items, CancellationToken cancellationToken) => Task.FromResult(new Dictionary<(int SourceContentId, string Url), BrokenLinkExistingRecord>());

    public Task PersistBrokenLinkBatchAsync(IReadOnlyList<BrokenLinkBatchMutation> mutations, CancellationToken cancellationToken) => Task.CompletedTask;

    public Task<int> GetEnabledPeriodicTaskCountAsync(CancellationToken cancellationToken) => Task.FromResult(0);

    public Task<IReadOnlyList<PeriodicTaskRecord>> LoadEnabledPeriodicTasksAsync(CancellationToken cancellationToken)
        => Task.FromResult<IReadOnlyList<PeriodicTaskRecord>>([]);

    public Task MarkPeriodicTaskTriggeredAsync(int periodicTaskId, DateTimeOffset triggeredAt, CancellationToken cancellationToken)
        => Task.CompletedTask;
}
