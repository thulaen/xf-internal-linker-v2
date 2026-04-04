using HttpWorker.Core.Contracts.V1;

namespace HttpWorker.Core.Interfaces;

public interface IPostgresRuntimeStore
{
    Task<bool> CanConnectAsync(CancellationToken cancellationToken);

    Task<BrokenLinkScanWorkload> LoadBrokenLinkScanWorkloadAsync(
        BrokenLinkScanRequest request,
        CancellationToken cancellationToken);

    Task<Dictionary<(int SourceContentId, string Url), BrokenLinkExistingRecord>> LoadExistingBrokenLinkRecordsAsync(
        IReadOnlyList<BrokenLinkUrlRequest> items,
        CancellationToken cancellationToken);

    Task PersistBrokenLinkBatchAsync(
        IReadOnlyList<BrokenLinkBatchMutation> mutations,
        CancellationToken cancellationToken);

    Task<int> GetEnabledPeriodicTaskCountAsync(CancellationToken cancellationToken);

    Task<IReadOnlyList<PeriodicTaskRecord>> LoadEnabledPeriodicTasksAsync(CancellationToken cancellationToken);

    Task MarkPeriodicTaskTriggeredAsync(int periodicTaskId, DateTimeOffset triggeredAt, CancellationToken cancellationToken);
    
    Task<List<GSCDailyMetrics>> GetPagePerformanceAsync(string pageUrl, DateTime startDate, DateTime endDate, CancellationToken cancellationToken);
    
    Task<List<GSCDailyMetrics>> GetGlobalPerformanceAsync(DateTime startDate, DateTime endDate, string propertyUrl, CancellationToken cancellationToken);

    Task PersistImportNodesAsync(IReadOnlyList<ImportContentMutation> mutations, CancellationToken cancellationToken);
    
    Task<IReadOnlyList<HostNode>> GetHostNodesAsync(List<int> scopeIds, CancellationToken cancellationToken);
    
    Task<IReadOnlyList<DestinationNode>> GetDestinationNodesAsync(List<int> destScopeIds, CancellationToken cancellationToken);
    
    Task PersistPipelineSuggestionsAsync(string runId, IReadOnlyList<PipelineSuggestion> suggestions, CancellationToken cancellationToken);
}
