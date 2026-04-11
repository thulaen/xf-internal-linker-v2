using HttpWorker.Core.Contracts.V1;
using MathNet.Numerics.Optimization;

namespace HttpWorker.Services.Analytics;

/// <summary>
/// Runs the L-BFGS bounded optimisation for the four core ranking weights.
///
/// Objective (maximise):
///   Score(w) = w_semantic * GscLift
///            + w_keyword  * Ga4Ctr
///            + w_node     * ReviewApprovalRate
///            + w_quality  * MatomoClickRate
///
/// Hard constraints (enforced after every candidate):
///   • All four weights sum to 1.0 (normalised at the end).
///   • Each weight stays within ±0.05 of its baseline (per-run delta cap).
///   • Each weight stays within ±0.20 of the recommended baseline (drift cap).
///   • Each weight is clamped to [0.01, 0.80] so no signal is zeroed out.
/// </summary>
public sealed class WeightObjectiveFunction
{
    // The four keys in a stable order.
    public static readonly string[] Keys = ["w_semantic", "w_keyword", "w_node", "w_quality"];

    // All weight keys active in the live ranker (backend/apps/pipeline/services/ranker.py).
    // The optimiser currently covers only the 4 core weights in Keys[].
    // FR-018 diagnostic: the uncovered keys are tracked here for coverage reporting.
    public static readonly string[] AllLiveRankerWeightKeys =
    [
        "w_semantic", "w_keyword", "w_node", "w_quality",
        "weighted_authority.ranking_weight", "link_freshness.ranking_weight",
        "phrase_matching.ranking_weight", "learned_anchor.ranking_weight",
        "rare_term_propagation.ranking_weight", "field_aware_relevance.ranking_weight",
        "ga4_gsc.ranking_weight", "click_distance.ranking_weight",
    ];

    public static readonly string[] UncoveredWeightKeys =
        AllLiveRankerWeightKeys.Except(Keys).ToArray();

    // Recommended (research) baseline — matches recommended_weights.py.
    public static readonly Dictionary<string, double> RecommendedBaseline = new()
    {
        ["w_semantic"] = 0.40,
        ["w_keyword"]  = 0.25,
        ["w_node"]     = 0.20,
        ["w_quality"]  = 0.15,
    };

    private const double MaxDeltaPerRun    = 0.05;
    private const double MaxDriftFromBase  = 0.20;
    private const double MinWeight         = 0.01;
    private const double MaxWeight         = 0.80;

    /// <summary>
    /// Compute the predicted quality score for a given weight vector against the signals.
    /// This is the objective function value: higher is better.
    /// </summary>
    public static double Score(double[] weights, WeightTuneSignals signals)
    {
        return weights[0] * signals.GscLift
             + weights[1] * signals.Ga4Ctr
             + weights[2] * signals.ReviewApprovalRate
             + weights[3] * signals.MatomoClickRate;
    }

    /// <summary>
    /// Run the optimiser and return a bounded candidate weight vector.
    /// Returns null if optimisation fails or produces no meaningful improvement.
    /// </summary>
    public OptimisationResult? Optimise(
        Dictionary<string, double> currentWeights,
        WeightTuneSignals signals)
    {
        var baseline = Keys.Select(k => currentWeights.GetValueOrDefault(k, RecommendedBaseline[k])).ToArray();
        var recommended = Keys.Select(k => RecommendedBaseline[k]).ToArray();

        double baselineScore = Score(baseline, signals);

        // We use MathNet's BfgsMinimizer (L-BFGS). Since it is unconstrained, we handle 
        // bounds and the sum=1.0 constraint via a multi-stage penalty function.
        // Objective: Minimize -Score(w) + Penalty(w)
        var objectiveFunc = ObjectiveFunction.Gradient(w =>
        {
            var arr = w.ToArray();
            
            // 1. Calculate the raw objective (minimize negative score)
            double score = Score(arr, signals);
            double val = -score;

            // 2. Add penalty for sum != 1.0 (very strong)
            double sum = arr.Sum();
            val += 1000.0 * Math.Pow(sum - 1.0, 2);

            // 3. Add penalties for bound violations (per-run delta and drift)
            for (int i = 0; i < 4; i++)
            {
                double low = Math.Max(MinWeight, Math.Max(baseline[i] - MaxDeltaPerRun, recommended[i] - MaxDriftFromBase));
                double high = Math.Min(MaxWeight, Math.Min(baseline[i] + MaxDeltaPerRun, recommended[i] + MaxDriftFromBase));

                if (arr[i] < low) val += 500.0 * Math.Pow(low - arr[i], 2);
                if (arr[i] > high) val += 500.0 * Math.Pow(arr[i] - high, 2);
            }

            return val;
        }, w =>
        {
            var arr = w.ToArray();
            var grad = new double[4];

            // 1. Partial derivative of -Score(w): d/dw_i = -Signal_i
            double[] sigArr = [signals.GscLift, signals.Ga4Ctr, signals.ReviewApprovalRate, signals.MatomoClickRate];
            for (int i = 0; i < 4; i++) grad[i] = -sigArr[i];

            // 2. Partial derivative of sum penalty: d/dw_i (1000 * (sum-1)^2) = 2000 * (sum-1)
            double sum = arr.Sum();
            double sumGrad = 2000.0 * (sum - 1.0);
            for (int i = 0; i < 4; i++) grad[i] += sumGrad;

            // 3. Partial derivative of bound penalties: d/dw_i (500 * (low-w)^2) = -1000 * (low-w)
            for (int i = 0; i < 4; i++)
            {
                double low = Math.Max(MinWeight, Math.Max(baseline[i] - MaxDeltaPerRun, recommended[i] - MaxDriftFromBase));
                double high = Math.Min(MaxWeight, Math.Min(baseline[i] + MaxDeltaPerRun, recommended[i] + MaxDriftFromBase));

                if (arr[i] < low) grad[i] += -1000.0 * (low - arr[i]);
                if (arr[i] > high) grad[i] += 1000.0 * (arr[i] - high);
            }

            return MathNet.Numerics.LinearAlgebra.Vector<double>.Build.DenseOfArray(grad);
        });

        var initialGuess = MathNet.Numerics.LinearAlgebra.Vector<double>.Build.DenseOfArray(baseline);

        try
        {
            var minimizer = new BfgsMinimizer(1e-7, 1e-7, 1e-7, 100);
            var result = minimizer.FindMinimum(objectiveFunc, initialGuess);
            
            // Final pass through constraints to ensure absolute compliance (handles rounding/floating point jitter)
            var candidate = ApplyConstraints(result.MinimizingPoint.ToArray(), baseline, recommended);
            double candidateScore = Score(candidate, signals);

            // Require at least a small improvement to avoid unnecessary churn.
            if (candidateScore <= baselineScore * 1.001)
            {
                return null;
            }

            var candidateDict = Keys.Zip(candidate).ToDictionary(t => t.First, t => t.Second);
            return new OptimisationResult
            {
                CandidateWeights = candidateDict,
                BaselineWeights = Keys.Zip(baseline).ToDictionary(t => t.First, t => t.Second),
                CandidateScore = candidateScore,
                BaselineScore = baselineScore,
            };
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// Apply all bound constraints to a raw weight vector and normalise to sum=1.
    /// </summary>
    private static double[] ApplyConstraints(double[] raw, double[] baseline, double[] recommended)
    {
        var result = new double[4];

        for (int i = 0; i < 4; i++)
        {
            double v = raw[i];

            // Per-run delta cap.
            v = Math.Max(baseline[i] - MaxDeltaPerRun, Math.Min(baseline[i] + MaxDeltaPerRun, v));
            // Drift-from-recommended cap.
            v = Math.Max(recommended[i] - MaxDriftFromBase, Math.Min(recommended[i] + MaxDriftFromBase, v));
            // Absolute floor/ceiling.
            v = Math.Max(MinWeight, Math.Min(MaxWeight, v));

            result[i] = v;
        }

        // Normalise so weights sum to 1.0.
        double total = result.Sum();
        if (total > 0)
        {
            for (int i = 0; i < 4; i++)
            {
                result[i] = Math.Round(result[i] / total, 4);
            }
        }

        return result;
    }
}

public sealed class OptimisationResult
{
    public Dictionary<string, double> CandidateWeights { get; set; } = new();
    public Dictionary<string, double> BaselineWeights { get; set; } = new();
    public double CandidateScore { get; set; }
    public double BaselineScore { get; set; }
    public string[] UncoveredWeightKeys { get; set; } = WeightObjectiveFunction.UncoveredWeightKeys;
}
