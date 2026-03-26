using HttpWorker.Core.Contracts.V1;

namespace HttpWorker.Core.Interfaces;

public interface IJobQueueService
{
    Task QueueJobAsync(JobRequest request, CancellationToken cancellationToken);
    Task<string?> PopRawJobAsync(CancellationToken cancellationToken);
    Task<JobResult?> GetResultAsync(string jobId, CancellationToken cancellationToken);
    Task<DeadLetterRecord?> GetDeadLetterAsync(string jobId, CancellationToken cancellationToken);
    Task<bool> HasQueuedMarkerAsync(string jobId, CancellationToken cancellationToken);
    Task WriteResultAsync(JobResult result, CancellationToken cancellationToken);
    Task WriteDeadLetterAsync(DeadLetterRecord deadLetter, CancellationToken cancellationToken);
    Task DeleteQueuedMarkerAsync(string jobId, CancellationToken cancellationToken);
    Task<bool> IsRedisConnectedAsync(CancellationToken cancellationToken);
}
