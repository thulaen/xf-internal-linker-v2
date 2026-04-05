using HttpWorker.Core.Contracts.V1;
using Microsoft.Extensions.Logging;

namespace HttpWorker.Services.Analytics;

public sealed class TrafficDecayService(ILogger<TrafficDecayService> logger)
{
    public Dictionary<int, float> ComputeDecayedScores(
        Dictionary<int, List<GSCDailyMetrics>> dailyMetrics,
        HttpWorkerOptions options)
    {
        var rawScores = new Dictionary<int, float>();
        var now = DateTime.UtcNow.Date;

        foreach (var kvp in dailyMetrics)
        {
            float totalHotScore = 0f;
            foreach (var day in kvp.Value)
            {
                // Formula: hot_score = log10(max(traffic_volume, 1)) - gravity * age_in_days
                float volume = (day.Clicks * options.Pipeline.HotClicksWeight) + (day.Impressions * options.Pipeline.HotImpressionsWeight);
                int age = (now - day.Date.Date).Days;
                
                // Ensure age is non-negative
                if (age < 0) age = 0;

                float dailyHot = (float)Math.Log10(Math.Max(volume, 1)) - (options.Pipeline.HotGravity * age);
                totalHotScore += dailyHot;
            }
            rawScores[kvp.Key] = totalHotScore;
        }

        if (rawScores.Count == 0) return rawScores;

        // Min-Max Normalization (0.0 to 1.0)
        float min = rawScores.Values.Min();
        float max = rawScores.Values.Max();
        float range = max - min;

        var normalized = new Dictionary<int, float>();
        foreach (var kvp in rawScores)
        {
            normalized[kvp.Key] = range > 0.00001f ? (kvp.Value - min) / range : 0.5f;
        }

        logger.LogInformation("Computed decayed traffic scores for {Count} items.", normalized.Count);
        return normalized;
    }
}
