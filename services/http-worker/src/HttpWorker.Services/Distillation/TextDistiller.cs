using System.Net.Http.Json;
using System.Text.RegularExpressions;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace HttpWorker.Services.Distillation;

public class TextDistiller : ITextDistiller
{
    private readonly HttpClient _httpClient;
    private readonly string _djangoBaseUrl;
    private readonly ILogger<TextDistiller> _logger;

    private static readonly Regex IntentRegex = new(
        @"\b(?:fix|solve|resolv|solution|workaround|issue|problem|error|bug|crash|install|configur|setup|upgrad|migrat|update|enable|disable|how\s+to|step|guide|tutorial|tip|trick|note|warning|important)\w*\b",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex EntityRegex = new(
        @"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+",
        RegexOptions.Compiled);

    public bool IsFallbackActive { get; private set; }

    public TextDistiller(HttpClient httpClient, IOptions<HttpWorkerOptions> options, ILogger<TextDistiller> logger)
    {
        _httpClient = httpClient;
        _djangoBaseUrl = options.Value.Scheduler.ControlPlaneBaseUrl.TrimEnd('/');
        _logger = logger;
    }

    public async Task<string> DistillBodyAsync(IReadOnlyList<string> sentences, int maxSentences = 5, CancellationToken cancellationToken = default)
    {
        if (sentences == null || sentences.Count == 0) return string.Empty;

        try
        {
            var request = new { sentences, max_sentences = maxSentences };
            var response = await _httpClient.PostAsJsonAsync($"{_djangoBaseUrl}/api/ml/distill/", request, cancellationToken);
            
            if (response.IsSuccessStatusCode)
            {
                var result = await response.Content.ReadFromJsonAsync<DistillResponse>(cancellationToken: cancellationToken);
                if (result?.Distilled != null)
                {
                    IsFallbackActive = false;
                    return result.Distilled;
                }
            }
            
            _logger.LogWarning("Django ML Distill API failed with status {Status}. Falling back to Regex.", response.StatusCode);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to call Django ML Distill API. Falling back to Regex.");
        }

        IsFallbackActive = true;
        // Fallback
        return DistillBodyRegexFallback(sentences, maxSentences);
    }

    private string DistillBodyRegexFallback(IReadOnlyList<string> sentences, int maxSentences)
    {
        var scored = new List<(double Score, int Index, string Text)>(sentences.Count);
        
        for (int i = 0; i < sentences.Count; i++)
        {
            scored.Add((ScoreSentence(sentences[i], i), i, sentences[i]));
        }

        var top = scored.OrderByDescending(x => x.Score)
                        .ThenBy(x => x.Index)
                        .Take(maxSentences)
                        .OrderBy(x => x.Index)
                        .Select(x => x.Text);

        return string.Join(" ", top);
    }

    private double ScoreSentence(string sentence, int index)
    {
        double score = 1.0;
        
        if (EntityRegex.IsMatch(sentence)) score += 0.4;
        if (IntentRegex.IsMatch(sentence)) score += 0.3;
        
        score *= Math.Exp(-0.15 * index);
        
        return score;
    }
    
    private class DistillResponse
    {
        public string? Distilled { get; set; }
    }
}
