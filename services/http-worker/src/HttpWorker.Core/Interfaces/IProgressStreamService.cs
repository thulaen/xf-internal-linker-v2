namespace HttpWorker.Core.Interfaces;

public interface IProgressStreamService
{
    Task PublishAsync(
        string jobId,
        object payload,
        CancellationToken cancellationToken);
}
