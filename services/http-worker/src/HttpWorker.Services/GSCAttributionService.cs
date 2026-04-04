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
        var postEnd = applyDate.AddDays(payload.WindowDays - 1);

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
        if (baseline.Impressions < 50 && post.Impressions < 50)
        {
            return new GSCAttributionResult
            {
                SuggestionId = payload.SuggestionId,
                RewardLabel = "inconclusive",
                BaselineClicks = baseline.Clicks,
                PostClicks = post.Clicks
            };
        }

        // 4. Causal Normalization (Market Trend)
        // We calculate how much the site grew/shrank to establish a "Counterfactual" baseline for this page.
        double globalCtrBaseline = (double)globalBaseline.Clicks / Math.Max(1, globalBaseline.Impressions);
        double globalCtrPost = (double)globalPost.Clicks / Math.Max(1, globalPost.Impressions);
        
        // If site grew 10%, our control multiplier is 1.1. 
        // We use this to adjust our "expectations" of the baseline.
        double controlTrendMultiplier = globalCtrPost / Math.Max(0.001, globalCtrBaseline);

        // 5. Bayesian Smoothing (Hierarchical Prior)
        // We use the Global Site CTR as the prior to smooth out low-traffic noise.
        double priorStrength = 100.0;
        // Fix 1: Ensure alpha0 and beta0 are strictly positive to prevent MathNet exceptions
        double alpha0 = Math.Max(0.01, globalCtrBaseline * priorStrength);
        double beta0 = Math.Max(0.01, (1.0 - globalCtrBaseline) * priorStrength);

        // 6. Build Distributions
        // Baseline: The smoothed CTR we observed before the change.
        var baselineDist = new Beta(
            baseline.Clicks + alpha0, 
            Math.Max(0, baseline.Impressions - baseline.Clicks) + beta0);
        
        // Post: The actual CTR we observed after the change.
        var postDist = new Beta(
            post.Clicks + alpha0, 
            Math.Max(0, post.Impressions - post.Clicks) + beta0);

        // 7. Monte Carlo Simulation for Causal Lift
        int wins = 0;
        double totalLift = 0;
        var rnd = new Random();
        
        for (int i = 0; i < MonteCarloSamples; i++)
        {
            double sBaseline = baselineDist.Sample();
            double sPost = postDist.Sample();
            
            // Apply Causal Trend: "What would the baseline have been if it followed the site trend?"
            // Fix 2: Clamp CTR to max 0.999 to prevent impossible >100% target CTR
            double sCounterfactual = Math.Min(0.999, sBaseline * controlTrendMultiplier);
            
            if (sPost > sCounterfactual)
            {
                wins++;
            }
            
            // Fix 3: Avoid extreme volatility on micro-CTRs
            double denominator = Math.Max(0.001, sCounterfactual);
            totalLift += (sPost - sCounterfactual) / denominator;
        }

        double probSuccess = (double)wins / MonteCarloSamples;
        double averageLift = totalLift / MonteCarloSamples;

        _logger.LogInformation("GSC Results for {Id}: ProbSuccess={Prob:P1}, CausalLift={Lift:P1}", payload.SuggestionId, probSuccess, averageLift);

        return new GSCAttributionResult
        {
            SuggestionId = payload.SuggestionId,
            BaselineClicks = baseline.Clicks,
            PostClicks = post.Clicks,
            LiftClicksPct = averageLift,
            ProbabilityOfUplift = probSuccess,
            RewardLabel = AssignLabel(probSuccess, averageLift, post.Impressions)
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
        
        // Positive: 95% confidence AND at least meaningful lift
        if (probability > 0.95 && lift > 0.02) return "positive";
        
        // Negative: 5% confidence (95% sure it dropped) OR severe drop
        if (probability < 0.05 || (probability < 0.2 && lift < -0.2)) return "negative";
        
        return "neutral";
    }
}
