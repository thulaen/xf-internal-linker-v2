using HttpWorker.Core.Contracts.V1;

namespace HttpWorker.Core.Interfaces;

public interface IGraphCandidateService
{
    Task<IReadOnlyList<PipelineSuggestion>> GenerateGraphCandidatesAsync(
        int sourceArticleId,
        KnowledgeGraphData graphData,
        Dictionary<int, float> trafficMetrics,
        CancellationToken cancellationToken);
}
