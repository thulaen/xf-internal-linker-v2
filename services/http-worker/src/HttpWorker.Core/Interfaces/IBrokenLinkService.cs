using HttpWorker.Core.Contracts.V1;

namespace HttpWorker.Core.Interfaces;

public interface IBrokenLinkService
{
    Task<BrokenLinkCheckResponse> CheckAsync(BrokenLinkCheckRequest request, CancellationToken cancellationToken);
}
