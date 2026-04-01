using HttpWorker.Core.Contracts.V1;

namespace HttpWorker.Core.Interfaces;

public interface IRuntimeTelemetryService
{
    Task WriteHeartbeatAsync(
        string instanceId,
        DateTimeOffset startedAt,
        CancellationToken cancellationToken);

    Task RecordResultAsync(
        string instanceId,
        DateTimeOffset startedAt,
        JobResult result,
        int retryCount,
        CancellationToken cancellationToken);

    Task RecordDeadLetterAsync(
        string instanceId,
        DateTimeOffset startedAt,
        DeadLetterRecord deadLetter,
        int retryCount,
        CancellationToken cancellationToken);

    Task<HttpWorkerWorkerSnapshot?> GetWorkerSnapshotAsync(CancellationToken cancellationToken);
}
