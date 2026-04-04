using HttpWorker.Core.Contracts.V1;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Npgsql;

namespace HttpWorker.Services.Analytics;

/// <summary>
/// Collects the four FR-018 signals from Postgres:
///   GscLift          – average causal click-lift from analytics_gscimpactsnapshot
///   Ga4Dwell         – average engagement rate from analytics_suggestiontelemetrydaily (ga4)
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
        var ga4Dwell = await GetGa4DwellAsync(conn, cutoff, cancellationToken);
        var reviewApproval = await GetReviewApprovalRateAsync(conn, cutoff, cancellationToken);
        var (matomoRate, appliedCount) = await GetMatomoClickRateAsync(conn, cutoff, cancellationToken);

        // Fall back to GA4 click rate if Matomo has no data.
        double effectiveClickRate = matomoRate >= 0 ? matomoRate : await GetGa4ClickRateAsync(conn, cutoff, cancellationToken);

        _logger.LogInformation(
            "[WeightTuner] Signals collected (lookback={Days}d): GscLift={G:F4} Ga4Dwell={D:F4} ReviewApproval={R:F4} ClickRate={C:F4} AppliedCount={N}",
            lookbackDays, gscLift, ga4Dwell, reviewApproval, effectiveClickRate, appliedCount);

        return new WeightTuneSignals
        {
            GscLift = gscLift,
            Ga4Dwell = ga4Dwell,
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

    // Average GA4 engagement rate (clicks / impressions) for destination pages reached via suggestions.
    private static async Task<double> GetGa4DwellAsync(NpgsqlConnection conn, DateTime cutoff, CancellationToken ct)
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
    private static async Task<(double Rate, int AppliedCount)> GetMatomoClickRateAsync(
        NpgsqlConnection conn, DateTime cutoff, CancellationToken ct)
    {
        const string sql = """
            SELECT
                COALESCE(SUM(clicks)::float / NULLIF(SUM(impressions), 0), -1.0) AS rate,
                COUNT(DISTINCT suggestion_id) AS applied_count
            FROM analytics_suggestiontelemetrydaily
            WHERE telemetry_source = 'matomo'
              AND date >= @cutoff
            """;
        await using var cmd = new NpgsqlCommand(sql, conn);
        cmd.Parameters.AddWithValue("cutoff", cutoff);
        await using var reader = await cmd.ExecuteReaderAsync(ct);
        if (await reader.ReadAsync(ct))
        {
            double rate = reader.IsDBNull(0) ? -1.0 : reader.GetDouble(0);
            int count = reader.IsDBNull(1) ? 0 : Convert.ToInt32(reader.GetInt64(1));
            return (rate, count);
        }
        return (-1.0, 0);
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
