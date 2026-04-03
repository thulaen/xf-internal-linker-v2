using System.Text.Json.Serialization;

namespace HttpWorker.Core.Contracts.V1;

/// <summary>
/// Payload for a GSC Search Outcome Attribution job.
/// Processed by the C# Statistical Brain.
/// </summary>
public sealed class GSCAttributionJobPayload
{
    [JsonPropertyName("suggestion_id")]
    public Guid SuggestionId { get; set; }

    [JsonPropertyName("page_url")]
    public string PageUrl { get; set; } = string.Empty;

    [JsonPropertyName("property_url")]
    public string PropertyUrl { get; set; } = string.Empty;

    [JsonPropertyName("apply_date")]
    public DateTimeOffset ApplyDate { get; set; }

    [JsonPropertyName("window_days")]
    public int WindowDays { get; set; } = 28;
}

/// <summary>
/// Result of a GSC attribution calculation.
/// </summary>
public sealed class GSCAttributionResult
{
    [JsonPropertyName("suggestion_id")]
    public Guid SuggestionId { get; set; }

    [JsonPropertyName("baseline_clicks")]
    public int BaselineClicks { get; set; }

    [JsonPropertyName("post_clicks")]
    public int PostClicks { get; set; }

    [JsonPropertyName("lift_clicks_pct")]
    public double LiftClicksPct { get; set; }

    [JsonPropertyName("probability_of_uplift")]
    public double ProbabilityOfUplift { get; set; }

    [JsonPropertyName("reward_label")]
    public string RewardLabel { get; set; } = "inconclusive";
}

/// <summary>
/// Internal aggregate row for GSC performance data.
/// </summary>
public sealed class GSCDailyMetrics
{
    public DateTime Date { get; set; }
    public int Impressions { get; set; }
    public int Clicks { get; set; }
}
