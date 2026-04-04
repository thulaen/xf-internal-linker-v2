using System.Net.Http.Json;
using HttpWorker.Core.Contracts.V1;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Npgsql;

namespace HttpWorker.Services.Analytics;

/// <summary>
/// Orchestrates a full FR-018 weight-tuning run:
///   1. Collect signals from Postgres.
///   2. Run the bounded Nelder-Mead optimiser.
///   3. POST the candidate to Django's internal endpoint.
/// </summary>
public sealed class WeightTunerService
{
    private readonly WeightTunerDataCollector _collector;
    private readonly WeightObjectiveFunction _optimizer;
    private readonly IHttpClientFactory _httpFactory;
    private readonly ILogger<WeightTunerService> _logger;
    private readonly string _djangoBaseUrl;
    private readonly string _connectionString;

    // Minimum applied-suggestion count before we consider data sufficient.
    private const int MinAppliedSuggestions = 10;

    public WeightTunerService(
        WeightTunerDataCollector collector,
        IOptions<HttpWorkerOptions> options,
        IHttpClientFactory httpFactory,
        ILogger<WeightTunerService> logger)
    {
        _collector = collector;
        _optimizer = new WeightObjectiveFunction();
        _httpFactory = httpFactory;
        _logger = logger;
        _djangoBaseUrl = options.Value.Scheduler.ControlPlaneBaseUrl.TrimEnd('/');
        _connectionString = options.Value.Postgres.ConnectionString;
    }

    public async Task<WeightTuneResult> RunAsync(WeightTuneRequest request, CancellationToken cancellationToken)
    {
        _logger.LogInformation("[WeightTuner] Starting run {RunId} (lookback={Days}d)", request.RunId, request.LookbackDays);

        // 1. Collect signals.
        WeightTuneSignals signals;
        try
        {
            signals = await _collector.CollectAsync(request.LookbackDays, cancellationToken);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[WeightTuner] Signal collection failed for run {RunId}", request.RunId);
            return Failure(request.RunId, $"Signal collection failed: {ex.Message}");
        }

        if (signals.AppliedSuggestionCount < MinAppliedSuggestions)
        {
            _logger.LogInformation(
                "[WeightTuner] Insufficient data for run {RunId}: only {N} applied suggestions (need {Min}).",
                request.RunId, signals.AppliedSuggestionCount, MinAppliedSuggestions);
            return new WeightTuneResult
            {
                RunId = request.RunId,
                Status = "insufficient_data",
                Detail = $"Only {signals.AppliedSuggestionCount} applied suggestions in lookback window (need {MinAppliedSuggestions}).",
            };
        }

        // 2. Load current champion weights from Postgres (core_appsetting).
        var currentWeights = await LoadCurrentWeightsAsync(cancellationToken);

        // 3. Run optimiser.
        var optResult = _optimizer.Optimise(currentWeights, signals);
        if (optResult is null)
        {
            _logger.LogInformation("[WeightTuner] No improvement found for run {RunId} — no challenger submitted.", request.RunId);
            return new WeightTuneResult
            {
                RunId = request.RunId,
                Status = "no_change",
                Detail = "Optimiser found no improvement over current champion weights.",
            };
        }

        _logger.LogInformation(
            "[WeightTuner] Candidate found for run {RunId}: score {C:F4} vs champion {Ch:F4}",
            request.RunId, optResult.CandidateScore, optResult.BaselineScore);

        // 4. POST candidate to Django.
        var posted = await PostChallengerAsync(request.RunId, optResult, cancellationToken);
        if (!posted)
        {
            return Failure(request.RunId, "Failed to submit challenger to Django.");
        }

        return new WeightTuneResult
        {
            RunId = request.RunId,
            Status = "submitted",
            Detail = "Challenger submitted to Django for evaluation.",
            CandidateWeights = optResult.CandidateWeights,
            BaselineWeights = optResult.BaselineWeights,
            PredictedQualityScore = optResult.CandidateScore,
            ChampionQualityScore = optResult.BaselineScore,
        };
    }

    private async Task<Dictionary<string, double>> LoadCurrentWeightsAsync(CancellationToken ct)
    {
        var weights = new Dictionary<string, double>();
        const string sql = """
            SELECT key, value
            FROM core_appsetting
            WHERE key = ANY(@keys)
            """;

        await using var conn = new NpgsqlConnection(_connectionString);
        await conn.OpenAsync(ct);
        await using var cmd = new NpgsqlCommand(sql, conn);
        cmd.Parameters.AddWithValue("keys", WeightObjectiveFunction.Keys);
        await using var reader = await cmd.ExecuteReaderAsync(ct);
        while (await reader.ReadAsync(ct))
        {
            string key = reader.GetString(0);
            if (double.TryParse(reader.GetString(1), System.Globalization.NumberStyles.Any,
                    System.Globalization.CultureInfo.InvariantCulture, out double val))
            {
                weights[key] = val;
            }
        }

        // Fill in recommended defaults for any missing keys.
        foreach (var kv in WeightObjectiveFunction.RecommendedBaseline)
        {
            weights.TryAdd(kv.Key, kv.Value);
        }

        return weights;
    }

    private async Task<bool> PostChallengerAsync(string runId, OptimisationResult result, CancellationToken ct)
    {
        var payload = new
        {
            run_id = runId,
            candidate_weights = result.CandidateWeights,
            baseline_weights = result.BaselineWeights,
            predicted_quality_score = result.CandidateScore,
            champion_quality_score = result.BaselineScore,
        };

        try
        {
            var client = _httpFactory.CreateClient("http-worker");
            var response = await client.PostAsJsonAsync(
                $"{_djangoBaseUrl}/api/internal/weight-challenger/", payload, ct);

            if (response.IsSuccessStatusCode)
            {
                _logger.LogInformation("[WeightTuner] Challenger {RunId} accepted by Django ({Status}).", runId, (int)response.StatusCode);
                return true;
            }

            var body = await response.Content.ReadAsStringAsync(ct);
            _logger.LogWarning("[WeightTuner] Django rejected challenger {RunId}: {Status} — {Body}", runId, (int)response.StatusCode, body);
            return false;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[WeightTuner] HTTP POST to Django failed for run {RunId}", runId);
            return false;
        }
    }

    private static WeightTuneResult Failure(string runId, string detail) =>
        new() { RunId = runId, Status = "error", Detail = detail };
}
