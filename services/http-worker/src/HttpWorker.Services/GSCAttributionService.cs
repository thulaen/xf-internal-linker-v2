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

        // Use UtcDateTime and Date to ensure absolute midnight UTC
        var applyDate = payload.ApplyDate.UtcDateTime.Date;
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

        // 5. Gamma-Poisson Conjugacy (Click-Count Rates)
        // Prior: Jeffreys prior (shape=0.5, rate=0.0) for robust low-traffic handling.
        // We use rate=0.0 (uninformative) or a small value like 0.001 to ensure proper Gamma parameters.
        double alphaPrior = 0.5;
        double ratePrior = 0.001;
        
        // 6. Build Distributions for Click Rates (lambda)
        // Baseline: The Gamma posterior for the click rate before the change.
        var baselineDist = new Gamma(baseline.Clicks + alphaPrior, 1.0 + ratePrior);
        
        // Post: The Gamma posterior for the click rate after the change.
        var postDist = new Gamma(post.Clicks + alphaPrior, 1.0 + ratePrior);

        // 7. Monte Carlo Simulation for Causal Lift
        int wins = 0;
        double totalLift = 0;
        var rnd = new Random();
        
        for (int i = 0; i < MonteCarloSamples; i++)
        {
            double lambdaBaseline = baselineDist.Sample();
            double lambdaPost = postDist.Sample();
            
            // Apply Causal Trend: "What would the baseline rate have been if it followed the site trend?"
            double lambdaCounterfactual = lambdaBaseline * controlTrendMultiplier;
            
            if (lambdaPost > lambdaCounterfactual)
            {
                wins++;
            }
            
            // Relative Lift on rates
            double denominator = Math.Max(0.0001, lambdaCounterfactual);
            totalLift += (lambdaPost - lambdaCounterfactual) / denominator;
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
