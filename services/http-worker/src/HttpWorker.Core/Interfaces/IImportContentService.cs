using HttpWorker.Core.Contracts.V1;

namespace HttpWorker.Core.Interfaces;

public interface IImportContentService
{
    Task<ImportContentResult> ExecuteAsync(string jobId, ImportContentRequest request, CancellationToken cancellationToken);
}
