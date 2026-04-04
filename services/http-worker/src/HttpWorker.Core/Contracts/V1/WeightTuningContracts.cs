using System.Text.Json.Serialization;

namespace HttpWorker.Core.Contracts.V1;

// ── Payload sent from Django to C# to kick off a tune run ─────────────────
public sealed class WeightTuneRequest
{
    /// <summary>Opaque run identifier (GUID) minted by Django and passed through.</summary>
    [JsonPropertyName("run_id")]
    public string RunId { get; set; } = string.Empty;

    /// <summary>How many days of history to use for signal aggregation.</summary>
    [JsonPropertyName("lookback_days")]
    public int LookbackDays { get; set; } = 90;
}

// ── Raw signal data collected from Postgres ────────────────────────────────
public sealed class WeightTuneSignals
{
    /// <summary>Average GSC causal lift across applied suggestions in the window.</summary>
    public double GscLift { get; set; }

    /// <summary>Average GA4 dwell-time engagement rate for destination pages.</summary>
    public double Ga4Dwell { get; set; }

    /// <summary>Fraction of reviewed suggestions that were approved.</summary>
    public double ReviewApprovalRate { get; set; }

    /// <summary>Average Matomo click-rate per suggestion (falls back to GA4 if no Matomo rows).</summary>
    public double MatomoClickRate { get; set; }

    /// <summary>Number of applied suggestions in the lookback window (data quality indicator).</summary>
    public int AppliedSuggestionCount { get; set; }
}

// ── Result returned from the C# tune run ──────────────────────────────────
public sealed class WeightTuneResult
{
    [JsonPropertyName("run_id")]
    public string RunId { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty; // "submitted" | "insufficient_data" | "no_change" | "error"

    [JsonPropertyName("candidate_weights")]
    public Dictionary<string, double>? CandidateWeights { get; set; }

    [JsonPropertyName("baseline_weights")]
    public Dictionary<string, double>? BaselineWeights { get; set; }

    [JsonPropertyName("predicted_quality_score")]
    public double? PredictedQualityScore { get; set; }

    [JsonPropertyName("champion_quality_score")]
    public double? ChampionQualityScore { get; set; }

    [JsonPropertyName("detail")]
    public string Detail { get; set; } = string.Empty;
}
