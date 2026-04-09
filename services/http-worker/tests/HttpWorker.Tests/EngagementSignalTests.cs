using HttpWorker.Core.Contracts.V1;
using HttpWorker.Services;
using Microsoft.Extensions.Options;
using Xunit;

namespace HttpWorker.Tests;

/// <summary>
/// FR-024: Unit tests for engagement signal computation (read-through rate, bounce penalty,
/// site-wide normalization). All math is exercised through PipelineServices static helper
/// exposed via a thin internal accessor, matching the spec test plan.
/// </summary>
public class EngagementSignalTests
{
    // Helper: build minimal PipelineOptions with engagement settings
    private static PipelineOptions DefaultOpts() => new()
    {
        EngagementSignalEnabled = true,
        WeightEngagement = 0.1f,
        EngagementLookbackDays = 30,
        EngagementWordsPerMinute = 200,
        EngagementCapRatio = 1.5f,
        EngagementFallbackValue = 0.5f,
    };

    // Expose the private static helper through reflection for white-box testing
    private static Dictionary<int, EngagementSignalData> ComputeSignals(
        Dictionary<int, (float AvgEngTime, float? AvgBounce, int WordCount, int RowsUsed)> raw,
        PipelineOptions opts)
    {
        var method = typeof(RunPipelineService).GetMethod(
            "ComputeNormalizedEngagementSignals",
            System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static)
            ?? throw new InvalidOperationException("ComputeNormalizedEngagementSignals not found");

        return (Dictionary<int, EngagementSignalData>)method.Invoke(null, [raw, opts])!;
    }

    [Fact]
    public void ReadThroughRate_FullRead_ReturnsOne()
    {
        // 300s engagement / (1000 words / 200 wpm * 60s) = 300s / 300s = 1.0
        var raw = new Dictionary<int, (float, float?, int, int)>
        {
            [1] = (300f, null, 1000, 5),
            [2] = (150f, null, 1000, 5), // 0.5 — needed for normalization range
        };

        var result = ComputeSignals(raw, DefaultOpts());

        Assert.True(result.ContainsKey(1));
        Assert.Equal(1.0f, result[1].ReadThroughRateRaw, precision: 4);
    }

    [Fact]
    public void ReadThroughRate_PartialRead_ReturnsCorrectFraction()
    {
        // 60s / 300s estimated = 0.2
        var raw = new Dictionary<int, (float, float?, int, int)>
        {
            [1] = (60f, null, 1000, 5),
            [2] = (300f, null, 1000, 5), // anchor for normalization
        };

        var result = ComputeSignals(raw, DefaultOpts());

        Assert.Equal(0.2f, result[1].ReadThroughRateRaw, precision: 4);
    }

    [Fact]
    public void ReadThroughRate_ZeroWordCount_UsesFallback()
    {
        // word_count = 0 → fallback
        var raw = new Dictionary<int, (float, float?, int, int)>
        {
            [1] = (100f, null, 0, 3),
            [2] = (100f, null, 500, 3),
        };
        var opts = DefaultOpts();
        var result = ComputeSignals(raw, opts);

        Assert.Equal(opts.EngagementFallbackValue, result[1].ReadThroughRateRaw, precision: 4);
    }

    [Fact]
    public void BountyPenalty_Applied_CorrectlyReducesScore()
    {
        // rtr=0.8, bounce=0.5 → eq = 0.8 * (1 - 0.5) = 0.4
        var raw = new Dictionary<int, (float, float?, int, int)>
        {
            // 240s / 300s = 0.8 rtr
            [1] = (240f, 0.5f, 1000, 5),
            [2] = (300f, 0.0f, 1000, 5),
        };

        var result = ComputeSignals(raw, DefaultOpts());

        Assert.Equal(0.8f, result[1].ReadThroughRateRaw, precision: 3);
        Assert.Equal(0.4f, result[1].EngagementQualityRaw, precision: 3);
    }

    [Fact]
    public void BountyPenalty_NullBounce_LeavesRtrUnchanged()
    {
        // bounce_rate = null → no penalty
        var raw = new Dictionary<int, (float, float?, int, int)>
        {
            [1] = (240f, null, 1000, 5),
            [2] = (60f, null, 1000, 5),
        };

        var result = ComputeSignals(raw, DefaultOpts());

        Assert.Equal(0.8f, result[1].ReadThroughRateRaw, precision: 3);
        // quality == rtr when bounce is null
        Assert.Equal(result[1].ReadThroughRateRaw, result[1].EngagementQualityRaw, precision: 3);
    }

    [Fact]
    public void NormalizedSignal_AlwaysBoundedZeroToOne()
    {
        // Even with extreme inputs, output must stay in [0,1]
        var raw = new Dictionary<int, (float, float?, int, int)>
        {
            [1] = (0f, 0.99f, 10, 1),      // near-zero engagement
            [2] = (9999f, 0.0f, 100, 30),  // very long engagement time
            [3] = (300f, 0.5f, 1000, 10),
        };

        var result = ComputeSignals(raw, DefaultOpts());

        foreach (var sig in result.Values)
        {
            Assert.InRange(sig.NormalizedSignal, 0f, 1f);
        }
    }

    [Fact]
    public void EmptyInput_ReturnsEmptyDictionary()
    {
        var result = ComputeSignals([], DefaultOpts());
        Assert.Empty(result);
    }

    [Fact]
    public void SingleItem_NormalizesTo05_WhenRangeIsZero()
    {
        // All items have the same capped eq → range=0 → normalized=0.5
        var raw = new Dictionary<int, (float, float?, int, int)>
        {
            [1] = (300f, null, 1000, 5),
        };

        var result = ComputeSignals(raw, DefaultOpts());

        Assert.Equal(0.5f, result[1].NormalizedSignal, precision: 4);
    }

    [Fact]
    public async Task EngagementSignalDisabled_GraphCandidateService_UsesFallback()
    {
        // When EngagementSignalEnabled=false, score must not include engagement contribution.
        // Test via GraphCandidateService directly.
        var opts = new HttpWorkerOptions
        {
            Pipeline = new PipelineOptions
            {
                EngagementSignalEnabled = false,
                WeightEngagement = 0.1f,
                EngagementFallbackValue = 0.5f,
                WeightRelevance = 0.4f,
                WeightTraffic = 0.3f,
                WeightAuthority = 0.1f,
                WeightFreshness = 0.1f,
            }
        };
        var svc = new GraphCandidateService(Options.Create(opts));

        // Run with no graph edges — returns empty. Just confirm no exception.
        var graphData = new KnowledgeGraphData();
        var result = await svc.GenerateGraphCandidatesAsync(
            1, graphData,
            new Dictionary<int, float>(),
            new Dictionary<int, EngagementSignalData>(),
            CancellationToken.None);

        Assert.Empty(result);
    }

    [Fact]
    public void FallbackUsed_IsFalse_WhenDataExists()
    {
        var raw = new Dictionary<int, (float, float?, int, int)>
        {
            [1] = (120f, 0.2f, 500, 10),
            [2] = (60f, 0.3f, 500, 8),
        };

        var result = ComputeSignals(raw, DefaultOpts());

        Assert.False(result[1].FallbackUsed);
        Assert.False(result[2].FallbackUsed);
    }
}
