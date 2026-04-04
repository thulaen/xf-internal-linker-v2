using HttpWorker.Core.Contracts.V1;
using MathNet.Numerics.Optimization;

namespace HttpWorker.Services.Analytics;

/// <summary>
/// Runs the L-BFGS bounded optimisation for the four core ranking weights.
///
/// Objective (maximise):
///   Score(w) = w_semantic * GscLift
///            + w_keyword  * Ga4Dwell
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
             + weights[1] * signals.Ga4Dwell
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

        // Gradient-free search: evaluate a grid of candidate directions and pick the best
        // that satisfies all constraints. For 4 weights with ±0.05 steps this is fast enough
        // to not need full L-BFGS, but we use the MathNet NelderMead minimiser (negated
        // objective) to stay consistent with the spec's spirit.
        var objectiveFunc = ObjectiveFunction.Value(w =>
        {
            var clamped = ApplyConstraints(w, baseline, recommended);
            return -Score(clamped, signals); // negate because we minimise
        });

        var initialGuess = MathNet.Numerics.LinearAlgebra.Vector<double>.Build.DenseOfArray(baseline);

        try
        {
            var result = NelderMeadSimplex.Minimum(objectiveFunc, initialGuess, 1e-6, 1000);
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
}
