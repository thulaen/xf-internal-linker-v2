using HttpWorker.Core.Contracts.V1;

namespace HttpWorker.Core.Interfaces;

public interface IGraphSyncService
{
    Task<GraphSyncResponse> SyncContentAsync(
        GraphSyncContentRequest request,
        CancellationToken cancellationToken);

    Task<GraphSyncResponse> RefreshAsync(
        GraphSyncRefreshRequest request,
        CancellationToken cancellationToken);
}

public interface IGraphSyncStore
{
    Task<IReadOnlyList<GraphSyncSourceContent>> LoadRefreshSourcesAsync(
        IReadOnlyList<int>? contentItemPks,
        CancellationToken cancellationToken);

    Task<Dictionary<(int ContentId, string ContentType), GraphSyncDestination>> LoadDestinationsAsync(
        IReadOnlyCollection<(int ContentId, string ContentType)> keys,
        CancellationToken cancellationToken);

    Task<Dictionary<string, GraphSyncDestination>> LoadDestinationsByUrlAsync(
        IReadOnlyCollection<string> normalizedUrls,
        CancellationToken cancellationToken);

    Task<GraphSyncSourceState> LoadSourceStateAsync(
        int contentItemPk,
        CancellationToken cancellationToken);

    Task PersistAsync(
        GraphSyncPersistenceCommand command,
        CancellationToken cancellationToken);
}
