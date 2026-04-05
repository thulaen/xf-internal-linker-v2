using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Options;

namespace HttpWorker.Services;

public sealed class GraphCandidateService : IGraphCandidateService
{
    private readonly HttpWorkerOptions _options;

    public GraphCandidateService(IOptions<HttpWorkerOptions> options)
    {
        _options = options.Value;
    }

    public async Task<IReadOnlyList<PipelineSuggestion>> GenerateGraphCandidatesAsync(
        int sourceArticleId,
        KnowledgeGraphData graphData,
        Dictionary<int, float> trafficMetrics,
        CancellationToken cancellationToken)
    {
        if (graphData.Edges.Count == 0) return [];

        // 1. Build Adjacency Lists
        var articleToEntities = new Dictionary<int, List<(int EntityId, float Weight)>>();
        var entityToArticles = new Dictionary<int, List<(int ArticleId, float Weight)>>();

        foreach (var edge in graphData.Edges)
        {
            if (!articleToEntities.TryGetValue(edge.ArticleId, out var entities))
            {
                entities = [];
                articleToEntities[edge.ArticleId] = entities;
            }
            entities.Add((edge.EntityId, edge.Weight));

            if (!entityToArticles.TryGetValue(edge.EntityId, out var articles))
            {
                articles = [];
                entityToArticles[edge.EntityId] = articles;
            }
            articles.Add((edge.ArticleId, edge.Weight));
        }

        // 2. Pixie Walk
        var visitCounts = new Dictionary<int, int>();
        var random = new Random();

        if (!articleToEntities.TryGetValue(sourceArticleId, out var startEntities))
        {
            return [];
        }

        int totalWalks = _options.Pipeline.PixieWalkCount;
        int maxSteps = _options.Pipeline.PixieMaxSteps;
        float backtrackProb = _options.Pipeline.PixieBacktrackProbability;

        for (int i = 0; i < totalWalks; i++)
        {
            // Pick a random starting entity from the source article
            var currentEntityId = WeightedChoice(startEntities, random);
            int steps = 0;

            while (steps < maxSteps)
            {
                // Entity -> Article
                if (!entityToArticles.TryGetValue(currentEntityId, out var potentialArticles)) break;
                var currentArticleId = WeightedChoice(potentialArticles, random);

                // Count visit (skip source)
                if (currentArticleId != sourceArticleId)
                {
                    visitCounts[currentArticleId] = visitCounts.GetValueOrDefault(currentArticleId) + 1;
                }

                // Article -> Entity
                if (!articleToEntities.TryGetValue(currentArticleId, out var potentialEntities)) break;
                currentEntityId = WeightedChoice(potentialEntities, random);

                steps++;

                // Backtrack?? (Reset to source entities)
                if (random.NextDouble() < backtrackProb)
                {
                    currentEntityId = WeightedChoice(startEntities, random);
                }
            }
        }

        // 3. Score and Filter Top 50
        var suggestions = new List<PipelineSuggestion>();
        var topHits = visitCounts.OrderByDescending(x => x.Value).Take(50);

        foreach (var hit in topHits)
        {
            float pixieRelevance = (float)Math.Sqrt(hit.Value);
            float trafficValue = trafficMetrics.GetValueOrDefault(hit.Key, 0f);

            var (valueScore, diagJson) = CalculateValueScore(pixieRelevance, trafficValue, hit.Key, graphData);

            suggestions.Add(new PipelineSuggestion
            {
                HostContentId = sourceArticleId,
                DestinationContentId = hit.Key,
                CandidateOrigin = "graph_walk",
                ValueScore = valueScore,
                ValueModelDiagnostics = diagJson,
                CompositeScore = valueScore
            });
        }

        return suggestions;
    }

    private int WeightedChoice(List<(int Id, float Weight)> items, Random random)
    {
        if (items.Count == 1) return items[0].Id;

        double totalWeight = 0;
        foreach (var item in items) totalWeight += item.Weight;

        double choice = random.NextDouble() * totalWeight;
        double sum = 0;
        foreach (var item in items)
        {
            sum += item.Weight;
            if (choice <= sum) return item.Id;
        }
        return items[^1].Id;
    }

    private (float Score, string Diagnostics) CalculateValueScore(float pixieRelevance, float traffic, int articleId, KnowledgeGraphData graphData)
    {
        // Normalization (Instagram-style signals)
        // relevance is sqrt(hits) -> 2000 walks, average hits 10-50 per top node. sqrt(50) ~ 7.
        float normRel = Math.Min(pixieRelevance / 10f, 1.0f);
        
        // Traffic normalization (Clicks over lookback window)
        // High traffic pages might have 10k clicks. Low might have 0.
        float normTraff = (float)(Math.Log10(traffic + 1) / 4.0); // Log scale, maxing around 10k clicks
        normTraff = Math.Clamp(normTraff, 0f, 1f);

        var p = _options.Pipeline;
        float score = (p.WeightRelevance * normRel) + (p.WeightTraffic * normTraff);
        
        // Loading real Authority (PageRank) and Freshness
        float normAuth = 0.5f; 
        float normFresh = 0.5f;

        if (graphData.ArticleMetrics.TryGetValue(articleId, out var metrics))
        {
            normAuth = metrics.PageRank;
            normFresh = metrics.Freshness;
        }

        score += (p.WeightAuthority * normAuth);
        score += (p.WeightFreshness * normFresh);

        var diagnostics = new
        {
            pixie_hits_sqrt = pixieRelevance,
            traffic_raw = traffic,
            norm_relevance = normRel,
            norm_traffic = normTraff,
            norm_authority = normAuth,
            norm_freshness = normFresh,
            w_rel = p.WeightRelevance,
            w_traff = p.WeightTraffic,
            w_auth = p.WeightAuthority,
            w_fresh = p.WeightFreshness
        };

        return (score, System.Text.Json.JsonSerializer.Serialize(diagnostics));
    }
}
