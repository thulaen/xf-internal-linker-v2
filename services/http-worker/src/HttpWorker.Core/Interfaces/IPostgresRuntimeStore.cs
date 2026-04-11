using HttpWorker.Core.Contracts.V1;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

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

    Task<IReadOnlyList<int>> PersistImportNodesAsync(IReadOnlyList<ImportContentMutation> mutations, CancellationToken cancellationToken);

    Task<List<(int ScopePk, int ExternalScopeId, string ScopeType)>> GetScopesAsync(IReadOnlyList<int> scopePks, CancellationToken cancellationToken);
    
}
