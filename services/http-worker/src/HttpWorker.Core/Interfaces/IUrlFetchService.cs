using HttpWorker.Core.Contracts.V1;

namespace HttpWorker.Core.Interfaces;

public interface IUrlFetchService
{
    Task<UrlFetchResponse> FetchAsync(UrlFetchRequest request, CancellationToken cancellationToken);
}
