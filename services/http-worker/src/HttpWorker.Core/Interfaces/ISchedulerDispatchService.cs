using HttpWorker.Core.Contracts.V1;

namespace HttpWorker.Core.Interfaces;

public interface ISchedulerDispatchService
{
    Task<bool> DispatchAsync(PeriodicTaskRecord task, CancellationToken cancellationToken);
}
