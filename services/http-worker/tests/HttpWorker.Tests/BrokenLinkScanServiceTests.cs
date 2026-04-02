using System.Text.Json;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using Xunit;

namespace HttpWorker.Tests;

public sealed class BrokenLinkScanServiceTests
{
    [Fact]
    public async Task ExecuteAsyncPersistsCreateAndFixedRowsAndPublishesCompletion()
    {
        var brokenLinkService = new FakeBrokenLinkService
        {
            Response = new BrokenLinkCheckResponse
            {
                Checked =
                [
                    new BrokenLinkCheckItem
                    {
                        SourceContentId = 10,
                        Url = "https://example.com/broken",
                        HttpStatus = 404,
                        CheckedAt = DateTimeOffset.UtcNow,
                    },
                    new BrokenLinkCheckItem
                    {
                        SourceContentId = 20,
                        Url = "https://example.com/fixed",
                        HttpStatus = 200,
                        CheckedAt = DateTimeOffset.UtcNow,
                    },
                ],
            },
        };
        var store = new FakePostgresRuntimeStoreForScan
        {
            Workload = new BrokenLinkScanWorkload
            {
                Items =
                [
                    new BrokenLinkUrlRequest { SourceContentId = 10, Url = "https://example.com/broken" },
                    new BrokenLinkUrlRequest { SourceContentId = 20, Url = "https://example.com/fixed" },
                ],
            },
            ExistingRecords =
            {
                [(20, "https://example.com/fixed")] = new BrokenLinkExistingRecord
                {
                    BrokenLinkId = Guid.NewGuid(),
                    SourceContentId = 20,
                    Url = "https://example.com/fixed",
                    Status = "open",
                },
            },
        };
        var progress = new FakeProgressStreamService();
        var service = new BrokenLinkScanService(brokenLinkService, store, progress);

        var result = await service.ExecuteAsync(
            "scan-job",
            new BrokenLinkScanRequest
            {
                AllowedDomains = ["example.com"],
                BatchSize = 100,
                MaxConcurrency = 5,
                TimeoutSeconds = 10,
            },
            CancellationToken.None);

        Assert.Equal(2, result.ScannedUrls);
        Assert.Equal(1, result.FlaggedUrls);
        Assert.Equal(1, result.FixedUrls);
        Assert.Equal(2, store.Mutations.Count);
        Assert.Contains(store.Mutations, mutation => mutation.Create && mutation.HttpStatus == 404);
        Assert.Contains(store.Mutations, mutation => !mutation.Create && mutation.Status == "fixed");

        Assert.NotEmpty(progress.Payloads);
        var completion = progress.Payloads.Last();
        Assert.Equal("completed", completion.GetProperty("state").GetString());
        Assert.Equal(1, completion.GetProperty("flagged_urls").GetInt32());
        Assert.Equal(1, completion.GetProperty("fixed_urls").GetInt32());
    }
}

internal sealed class FakeBrokenLinkService : IBrokenLinkService
{
    public BrokenLinkCheckResponse Response { get; set; } = new();

    public Task<BrokenLinkCheckResponse> CheckAsync(BrokenLinkCheckRequest request, CancellationToken cancellationToken)
    {
        Response.TotalChecked = Response.Checked.Count;
        Response.TotalFlagged = Response.Checked.Count(item =>
            item.HttpStatus == 0 ||
            item.HttpStatus >= 400 ||
            !string.IsNullOrEmpty(item.RedirectUrl));
        return Task.FromResult(Response);
    }
}

internal sealed class FakePostgresRuntimeStoreForScan : IPostgresRuntimeStore
{
    public BrokenLinkScanWorkload Workload { get; set; } = new();

    public Dictionary<(int SourceContentId, string Url), BrokenLinkExistingRecord> ExistingRecords { get; } = [];

    public List<BrokenLinkBatchMutation> Mutations { get; } = [];

    public Task<bool> CanConnectAsync(CancellationToken cancellationToken) => Task.FromResult(true);

    public Task<BrokenLinkScanWorkload> LoadBrokenLinkScanWorkloadAsync(BrokenLinkScanRequest request, CancellationToken cancellationToken) => Task.FromResult(Workload);

    public Task<Dictionary<(int SourceContentId, string Url), BrokenLinkExistingRecord>> LoadExistingBrokenLinkRecordsAsync(IReadOnlyList<BrokenLinkUrlRequest> items, CancellationToken cancellationToken) => Task.FromResult(ExistingRecords);

    public Task PersistBrokenLinkBatchAsync(IReadOnlyList<BrokenLinkBatchMutation> mutations, CancellationToken cancellationToken)
    {
        Mutations.AddRange(mutations);
        return Task.CompletedTask;
    }

    public Task<int> GetEnabledPeriodicTaskCountAsync(CancellationToken cancellationToken) => Task.FromResult(0);
}

internal sealed class FakeProgressStreamService : IProgressStreamService
{
    public List<JsonElement> Payloads { get; } = [];

    public Task PublishAsync(string jobId, object payload, CancellationToken cancellationToken)
    {
        Payloads.Add(JsonSerializer.SerializeToElement(payload));
        return Task.CompletedTask;
    }
}
