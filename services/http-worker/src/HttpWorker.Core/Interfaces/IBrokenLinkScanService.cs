using HttpWorker.Core.Contracts.V1;

namespace HttpWorker.Core.Interfaces;

public interface IBrokenLinkScanService
{
    Task<BrokenLinkScanResponse> ExecuteAsync(
        string jobId,
        BrokenLinkScanRequest request,
        CancellationToken cancellationToken);
}
