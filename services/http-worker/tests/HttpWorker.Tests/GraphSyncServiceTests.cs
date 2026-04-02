using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using Xunit;

namespace HttpWorker.Tests;

public sealed class GraphSyncServiceTests
{
    [Fact]
    public async Task SyncContentAsyncCreatesLinkAndFreshnessRows()
    {
        var store = new FakeGraphSyncStore();
        store.Destinations[(2, "thread")] = new GraphSyncDestination
        {
            ContentItemPk = 200,
            ContentId = 2,
            ContentType = "thread",
            Url = "https://forum.example.com/threads/target.2",
        };
        var service = new GraphSyncService(store);

        var result = await service.SyncContentAsync(
            new GraphSyncContentRequest
            {
                ContentItemPk = 100,
                ContentId = 10,
                ContentType = "thread",
                RawBbcode = "[URL=https://forum.example.com/threads/target.2/]Target[/URL]",
                ForumDomains = ["forum.example.com"],
            },
            CancellationToken.None);

        Assert.Equal(1, result.ActiveLinks);
        Assert.Equal(1, result.CreatedLinks);
        Assert.Equal(1, result.CreatedFreshnessEdges);
        Assert.Single(store.Commands);
        Assert.Single(store.Commands[0].NewLinks);
        Assert.Single(store.Commands[0].NewFreshnessEdges);
    }

    [Fact]
    public async Task SyncContentAsyncDeletesMissingLinksAndReactivatesFreshness()
    {
        var store = new FakeGraphSyncStore();
        store.Destinations[(2, "thread")] = new GraphSyncDestination
        {
            ContentItemPk = 200,
            ContentId = 2,
            ContentType = "thread",
            Url = "https://forum.example.com/threads/target.2",
        };
        store.SourceState.ExistingLinks.Add(new GraphSyncExistingLinkRow
        {
            Id = 1,
            ToContentItemPk = 200,
            ToContentId = 2,
            ToContentType = "thread",
            AnchorText = "Old target",
            ExtractionMethod = "bare_url",
            LinkOrdinal = 0,
            SourceInternalLinkCount = 2,
            ContextClass = "isolated",
        });
        store.SourceState.ExistingLinks.Add(new GraphSyncExistingLinkRow
        {
            Id = 2,
            ToContentItemPk = 200,
            ToContentId = 2,
            ToContentType = "thread",
            AnchorText = "Duplicate",
            ExtractionMethod = "bare_url",
            LinkOrdinal = 1,
            SourceInternalLinkCount = 2,
            ContextClass = "isolated",
        });
        store.SourceState.ExistingLinks.Add(new GraphSyncExistingLinkRow
        {
            Id = 3,
            ToContentItemPk = 300,
            ToContentId = 3,
            ToContentType = "thread",
            AnchorText = "Gone",
            ExtractionMethod = "bbcode_anchor",
            LinkOrdinal = 2,
            SourceInternalLinkCount = 2,
            ContextClass = "contextual",
        });
        store.SourceState.FreshnessEdges.Add(new GraphSyncFreshnessRow
        {
            Id = 11,
            ToContentItemPk = 200,
            ToContentId = 2,
            ToContentType = "thread",
            FirstSeenAt = DateTimeOffset.UtcNow.AddDays(-10),
            LastSeenAt = DateTimeOffset.UtcNow.AddDays(-2),
            LastDisappearedAt = DateTimeOffset.UtcNow.AddDays(-1),
            IsActive = false,
        });
        store.SourceState.FreshnessEdges.Add(new GraphSyncFreshnessRow
        {
            Id = 12,
            ToContentItemPk = 300,
            ToContentId = 3,
            ToContentType = "thread",
            FirstSeenAt = DateTimeOffset.UtcNow.AddDays(-9),
            LastSeenAt = DateTimeOffset.UtcNow.AddDays(-3),
            IsActive = true,
        });
        var service = new GraphSyncService(store);

        var result = await service.SyncContentAsync(
            new GraphSyncContentRequest
            {
                ContentItemPk = 100,
                ContentId = 10,
                ContentType = "thread",
                RawBbcode = "[URL=https://forum.example.com/threads/target.2/]Fresh target[/URL]",
                ForumDomains = ["forum.example.com"],
            },
            CancellationToken.None);

        Assert.Equal(1, result.ActiveLinks);
        Assert.Equal(1, result.UpdatedLinks);
        Assert.Equal(2, result.DeletedLinks);
        Assert.Equal(2, result.UpdatedFreshnessEdges);
        Assert.Single(store.Commands);
        Assert.Equal([2L, 3L], store.Commands[0].DeletedLinkIds);
    }
}

internal sealed class FakeGraphSyncStore : IGraphSyncStore
{
    public Dictionary<(int ContentId, string ContentType), GraphSyncDestination> Destinations { get; } =
        [];

    public Dictionary<string, GraphSyncDestination> UrlDestinations { get; } =
        new(StringComparer.Ordinal);

    public GraphSyncSourceState SourceState { get; } = new();

    public List<GraphSyncPersistenceCommand> Commands { get; } = [];

    public Task<IReadOnlyList<GraphSyncSourceContent>> LoadRefreshSourcesAsync(
        IReadOnlyList<int>? contentItemPks,
        CancellationToken cancellationToken)
    {
        return Task.FromResult<IReadOnlyList<GraphSyncSourceContent>>([]);
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
        var selected = new Dictionary<string, GraphSyncDestination>(StringComparer.Ordinal);
        foreach (var url in normalizedUrls)
        {
            if (UrlDestinations.TryGetValue(url, out var destination))
            {
                selected[url] = destination;
            }
        }

        return Task.FromResult(selected);
    }

    public Task<GraphSyncSourceState> LoadSourceStateAsync(
        int contentItemPk,
        CancellationToken cancellationToken)
    {
        return Task.FromResult(SourceState);
    }

    public Task PersistAsync(GraphSyncPersistenceCommand command, CancellationToken cancellationToken)
    {
        Commands.Add(command);
        return Task.CompletedTask;
    }
}
