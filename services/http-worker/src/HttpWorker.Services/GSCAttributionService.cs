using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using MathNet.Numerics.Distributions;
using Microsoft.Extensions.Logging;

namespace HttpWorker.Services;

public sealed class GSCAttributionService
{
    private readonly IPostgresRuntimeStore _store;
    private readonly ILogger<GSCAttributionService> _logger;
    private const int MonteCarloSamples = 10000;

    public GSCAttributionService(IPostgresRuntimeStore store, ILogger<GSCAttributionService> logger)
    {
        _store = store;
        _logger = logger;
    }

    public async Task<GSCAttributionResult> AnalyzeUpliftAsync(GSCAttributionJobPayload payload, CancellationToken cancellationToken)
    {
        _logger.LogInformation("Starting GSC Attribution for suggestion {SuggestionId} on {PageUrl}", payload.SuggestionId, payload.PageUrl);

        var applyDate = payload.ApplyDate.Date;
        var beforeStart = applyDate.AddDays(-payload.WindowDays);
        var beforeEnd = applyDate.AddDays(-1);
        var postStart = applyDate;
        var postEnd = applyDate.AddDays(payload.WindowDays);

        // 1. Fetch Performance Data
        var pageMetrics = await _store.GetPagePerformanceAsync(payload.PageUrl, beforeStart, postEnd, cancellationToken);
        var globalMetrics = await _store.GetGlobalPerformanceAsync(beforeStart, postEnd, payload.PropertyUrl, cancellationToken);

        // 2. Aggregate into Before/Post buckets
        var baseline = Aggregate(pageMetrics, beforeStart, beforeEnd);
        var post = Aggregate(pageMetrics, postStart, postEnd);
        var globalBaseline = Aggregate(globalMetrics, beforeStart, beforeEnd);
        var globalPost = Aggregate(globalMetrics, postStart, postEnd);

        _logger.LogDebug("Aggregated: Baseline Clicks={B}, Post Clicks={P}", baseline.Clicks, post.Clicks);

        // 3. Simple Check: Inconclusive if no traffic
        if (baseline.Impressions < 100 && post.Impressions < 100)
        {
            return new GSCAttributionResult
            {
                SuggestionId = payload.SuggestionId,
                RewardLabel = "inconclusive"
            };
        }

        // 4. Bayesian Smoothing (Hierarchical Prior)
        // We use the Global Site CTR as the prior to smooth out low-traffic noise.
        // We scale the prior to have a strength of '100' observations to avoid washing out real signal.
        double priorStrength = 100.0;
        double globalCtrBaseline = (double)globalBaseline.Clicks / Math.Max(1, globalBaseline.Impressions);
        double globalCtrPost = (double)globalPost.Clicks / Math.Max(1, globalPost.Impressions);

        double alpha0_baseline = globalCtrBaseline * priorStrength;
        double beta0_baseline = (1.0 - globalCtrBaseline) * priorStrength;
        
        double alpha0_post = globalCtrPost * priorStrength;
        double beta0_post = (1.0 - globalCtrPost) * priorStrength;

        // 5. Build Beta Distributions (Posterior)
        var baselineDist = new Beta(baseline.Clicks + alpha0_baseline, (baseline.Impressions - baseline.Clicks) + beta0_baseline);
        var postDist = new Beta(post.Clicks + alpha0_post, (post.Impressions - post.Clicks) + beta0_post);

        // 6. Monte Carlo Simulation for Probability of Uplift
        int wins = 0;
        var rnd = new Random();
        for (int i = 0; i < MonteCarloSamples; i++)
        {
            double sampleBaseline = baselineDist.Sample();
            double samplePost = postDist.Sample();
            
            // We want to see if Post is better than Baseline
            if (samplePost > sampleBaseline)
            {
                wins++;
            }
        }

        double probSuccess = (double)wins / MonteCarloSamples;
        double liftPct = ((double)post.Clicks / Math.Max(1, post.Impressions)) / ((double)baseline.Clicks / Math.Max(1, baseline.Impressions)) - 1.0;

        _logger.LogInformation("GSC Results for {Id}: ProbSuccess={Prob:P1}, Lift={Lift:P1}", payload.SuggestionId, probSuccess, liftPct);

        return new GSCAttributionResult
        {
            SuggestionId = payload.SuggestionId,
            BaselineClicks = baseline.Clicks,
            PostClicks = post.Clicks,
            LiftClicksPct = liftPct,
            ProbabilityOfUplift = probSuccess,
            RewardLabel = AssignLabel(probSuccess, liftPct, post.Impressions)
        };
    }

    private static GSCDailyMetrics Aggregate(IEnumerable<GSCDailyMetrics> metrics, DateTime start, DateTime end)
    {
        var result = new GSCDailyMetrics { Date = start };
        foreach (var m in metrics.Where(x => x.Date >= start && x.Date <= end))
        {
            result.Impressions += m.Impressions;
            result.Clicks += m.Clicks;
        }
        return result;
    }

    private static string AssignLabel(double probability, double lift, int postImpressions)
    {
        if (postImpressions < 50) return "inconclusive";
        
        if (probability > 0.95) return "positive";
        if (probability < 0.05) return "negative";
        
        return "neutral";
    }
}
