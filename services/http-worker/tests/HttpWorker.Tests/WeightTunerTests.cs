using HttpWorker.Core.Contracts.V1;
using HttpWorker.Services.Analytics;
using Xunit;

namespace HttpWorker.Tests;

public class WeightTunerTests
{
    [Fact]
    public void Optimise_FindsBetterWeights_WhenSignalsPresence()
    {
        // Arrange
        var optimizer = new WeightObjectiveFunction();
        var currentWeights = new Dictionary<string, double>
        {
            ["w_semantic"] = 0.40,
            ["w_keyword"] = 0.25,
            ["w_node"] = 0.20,
            ["w_quality"] = 0.15,
        };

        // GscLift is high, so w_semantic should increase.
        var signals = new WeightTuneSignals
        {
            GscLift = 5.0,           // High lift for semantic
            Ga4Dwell = 0.1,          // Low dwell for keyword
            ReviewApprovalRate = 0.1, // Low approval for node
            MatomoClickRate = 0.1,    // Low clicks for quality
            AppliedSuggestionCount = 100
        };

        // Act
        var result = optimizer.Optimise(currentWeights, signals);

        // Assert
        Assert.NotNull(result);
        Assert.True(result.CandidateScore > result.BaselineScore);
        Assert.True(result.CandidateWeights["w_semantic"] > currentWeights["w_semantic"]);
        // All four weights must sum to 1.0 (approx due to rounding)
        Assert.InRange(result.CandidateWeights.Values.Sum(), 0.999, 1.001);
    }
}
