using HttpWorker.Core.Contracts.V1;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Npgsql;

namespace HttpWorker.Services.Analytics;

/// <summary>
/// Collects the four FR-018 signals from Postgres:
///   GscLift          – average causal click-lift from analytics_gscimpactsnapshot
///   Ga4Ctr           – GA4 click-through rate (clicks / impressions) for suggested destinations
///   ReviewApproval   – fraction of reviewed suggestions that were approved
///   MatomoClickRate  – per-suggestion CTR from Matomo; falls back to GA4 if unavailable
/// </summary>
public sealed class WeightTunerDataCollector
{
    private readonly string _connectionString;
    private readonly ILogger<WeightTunerDataCollector> _logger;

    public WeightTunerDataCollector(
        IOptions<HttpWorkerOptions> options,
        ILogger<WeightTunerDataCollector> logger)
    {
        _connectionString = options.Value.Postgres.ConnectionString;
        _logger = logger;
    }

    public async Task<WeightTuneSignals> CollectAsync(int lookbackDays, CancellationToken cancellationToken)
    {
        await using var conn = new NpgsqlConnection(_connectionString);
        await conn.OpenAsync(cancellationToken);

        var cutoff = DateTime.UtcNow.AddDays(-lookbackDays).Date;

        var gscLift = await GetGscLiftAsync(conn, cutoff, cancellationToken);
        var ga4Ctr = await GetGa4CtrAsync(conn, cutoff, cancellationToken);
        var reviewApproval = await GetReviewApprovalRateAsync(conn, cutoff, cancellationToken);
        var matomoRate = await GetMatomoClickRateAsync(conn, cutoff, cancellationToken);

        // Fall back to GA4 click rate if Matomo has no data.
        double effectiveClickRate = matomoRate >= 0 ? matomoRate : await GetGa4ClickRateAsync(conn, cutoff, cancellationToken);
        string clickRateSource = matomoRate >= 0 ? "matomo" : "ga4";

        // Count applied suggestions from the source of truth (suggestions table),
        // not from telemetry — avoids gating on Matomo availability.
        var appliedCount = await GetAppliedSuggestionCountAsync(conn, cutoff, cancellationToken);

        _logger.LogInformation(
            "[WeightTuner] Signals collected (lookback={Days}d): GscLift={G:F4} Ga4Ctr={D:F4} ReviewApproval={R:F4} ClickRate={C:F4} (source={Src}) AppliedCount={N}",
            lookbackDays, gscLift, ga4Ctr, reviewApproval, effectiveClickRate, clickRateSource, appliedCount);

        return new WeightTuneSignals
        {
            GscLift = gscLift,
            Ga4Ctr = ga4Ctr,
            ReviewApprovalRate = reviewApproval,
            MatomoClickRate = effectiveClickRate,
            AppliedSuggestionCount = appliedCount,
        };
    }

    // Average causal lift from GSC impact snapshots for applied suggestions.
    private static async Task<double> GetGscLiftAsync(NpgsqlConnection conn, DateTime cutoff, CancellationToken ct)
    {
        const string sql = """
            SELECT COALESCE(AVG(lift_clicks_pct), 0.0)
            FROM analytics_gscimpactsnapshot
            WHERE created_at >= @cutoff
              AND reward_label IN ('positive', 'neutral')
            """;
        await using var cmd = new NpgsqlCommand(sql, conn);
        cmd.Parameters.AddWithValue("cutoff", cutoff);
        var result = await cmd.ExecuteScalarAsync(ct);
        return result is DBNull or null ? 0.0 : Convert.ToDouble(result);
    }

    // Average GA4 click-through rate (clicks / impressions) for destination pages reached via suggestions.
    private static async Task<double> GetGa4CtrAsync(NpgsqlConnection conn, DateTime cutoff, CancellationToken ct)
    {
        const string sql = """
            SELECT COALESCE(
                SUM(clicks)::float / NULLIF(SUM(impressions), 0),
                0.0
            )
            FROM analytics_suggestiontelemetrydaily
            WHERE telemetry_source = 'ga4'
              AND date >= @cutoff
            """;
        await using var cmd = new NpgsqlCommand(sql, conn);
        cmd.Parameters.AddWithValue("cutoff", cutoff);
        var result = await cmd.ExecuteScalarAsync(ct);
        return result is DBNull or null ? 0.0 : Convert.ToDouble(result);
    }

    // Fraction of reviewed suggestions (approved or rejected) that were approved.
    private static async Task<double> GetReviewApprovalRateAsync(NpgsqlConnection conn, DateTime cutoff, CancellationToken ct)
    {
        const string sql = """
            SELECT
                COUNT(*) FILTER (WHERE status = 'approved') AS approved,
                COUNT(*) FILTER (WHERE status IN ('approved', 'rejected')) AS reviewed
            FROM suggestions_suggestion
            WHERE updated_at >= @cutoff
            """;
        await using var cmd = new NpgsqlCommand(sql, conn);
        cmd.Parameters.AddWithValue("cutoff", cutoff);
        await using var reader = await cmd.ExecuteReaderAsync(ct);
        if (await reader.ReadAsync(ct))
        {
            long approved = reader.GetInt64(0);
            long reviewed = reader.GetInt64(1);
            return reviewed > 0 ? (double)approved / reviewed : 0.5; // neutral prior if no data
        }
        return 0.5;
    }

    // Matomo per-suggestion CTR. Returns -1 if no Matomo rows exist in the window.
    private static async Task<double> GetMatomoClickRateAsync(
        NpgsqlConnection conn, DateTime cutoff, CancellationToken ct)
    {
        const string sql = """
            SELECT COALESCE(SUM(clicks)::float / NULLIF(SUM(impressions), 0), -1.0) AS rate
            FROM analytics_suggestiontelemetrydaily
            WHERE telemetry_source = 'matomo'
              AND date >= @cutoff
            """;
        await using var cmd = new NpgsqlCommand(sql, conn);
        cmd.Parameters.AddWithValue("cutoff", cutoff);
        var result = await cmd.ExecuteScalarAsync(ct);
        return result is DBNull or null ? -1.0 : Convert.ToDouble(result);
    }

    // Count applied suggestions from the suggestions table (source-agnostic).
    // This avoids gating the tuner on Matomo telemetry availability.
    private static async Task<int> GetAppliedSuggestionCountAsync(
        NpgsqlConnection conn, DateTime cutoff, CancellationToken ct)
    {
        const string sql = """
            SELECT COUNT(*)
            FROM suggestions_suggestion
            WHERE status = 'applied'
              AND updated_at >= @cutoff
            """;
        await using var cmd = new NpgsqlCommand(sql, conn);
        cmd.Parameters.AddWithValue("cutoff", cutoff);
        var result = await cmd.ExecuteScalarAsync(ct);
        return result is DBNull or null ? 0 : Convert.ToInt32(result);
    }

    // GA4 click rate fallback when Matomo has no data.
    private static async Task<double> GetGa4ClickRateAsync(NpgsqlConnection conn, DateTime cutoff, CancellationToken ct)
    {
        const string sql = """
            SELECT COALESCE(
                SUM(clicks)::float / NULLIF(SUM(impressions), 0),
                0.0
            )
            FROM analytics_suggestiontelemetrydaily
            WHERE telemetry_source = 'ga4'
              AND date >= @cutoff
            """;
        await using var cmd = new NpgsqlCommand(sql, conn);
        cmd.Parameters.AddWithValue("cutoff", cutoff);
        var result = await cmd.ExecuteScalarAsync(ct);
        return result is DBNull or null ? 0.0 : Convert.ToDouble(result);
    }
}
