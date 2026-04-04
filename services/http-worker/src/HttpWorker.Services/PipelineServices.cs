using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;

namespace HttpWorker.Services;

public class ImportContentService(IPostgresRuntimeStore runtimeStore) : IImportContentService
{
    public async Task<ImportContentResult> ExecuteAsync(string jobId, ImportContentRequest request, CancellationToken cancellationToken)
    {
        // TODO: Full C# import orchestration (fetching from APIs, basic text normalization).
        return new ImportContentResult { ItemsSynced = 0, ItemsUpdated = 0 };
    }
}

public class RunPipelineService(IPostgresRuntimeStore runtimeStore) : IRunPipelineService
{
    public async Task<RunPipelineResult> ExecuteAsync(string jobId, RunPipelineRequest request, CancellationToken cancellationToken)
    {
        // TODO: Full C# pipeline orchestration (retrieval, candidate filters, diversity logic, suggestion generation, native P/Invoke C++ interop).
        return new RunPipelineResult { SuggestionsCreated = 0, ItemsInScope = 0, DurationSeconds = 0.0 };
    }
}
