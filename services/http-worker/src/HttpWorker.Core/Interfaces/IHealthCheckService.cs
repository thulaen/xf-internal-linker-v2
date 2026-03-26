using HttpWorker.Core.Contracts.V1;

namespace HttpWorker.Core.Interfaces;

public interface IHealthCheckService
{
    Task<HealthCheckResponse> CheckAsync(HealthCheckRequest request, CancellationToken cancellationToken);
}
