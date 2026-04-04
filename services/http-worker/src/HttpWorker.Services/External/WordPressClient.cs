using System.Net.Http.Json;
using System.Text.Json.Nodes;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Logging;

namespace HttpWorker.Services.External;

public class WordPressClient : IWordPressClient
{
    private readonly HttpClient _httpClient;
    private readonly ILogger<WordPressClient> _logger;

    public WordPressClient(HttpClient httpClient, ILogger<WordPressClient> logger)
    {
        _httpClient = httpClient;
        _logger = logger;
    }

    private async Task<(List<JsonObject> Items, int TotalPages)> GetListAsync(string endpoint, int page, string status, CancellationToken cancellationToken)
    {
        var url = $"wp-json/wp/v2/{endpoint}?page={page}&per_page=100&status={status}";
        var response = await _httpClient.GetAsync(url, cancellationToken);
        response.EnsureSuccessStatusCode();

        var content = await response.Content.ReadFromJsonAsync<List<JsonObject>>(cancellationToken: cancellationToken);
        
        int totalPages = 1;
        if (response.Headers.TryGetValues("X-WP-TotalPages", out var values))
        {
            if (int.TryParse(values.FirstOrDefault(), out int parsedPages))
            {
                totalPages = Math.Max(1, parsedPages);
            }
        }

        return (content ?? new List<JsonObject>(), totalPages);
    }

    public Task<(List<JsonObject> Items, int TotalPages)> GetPostsAsync(int page = 1, string status = "publish", CancellationToken cancellationToken = default)
        => GetListAsync("posts", page, status, cancellationToken);

    public Task<(List<JsonObject> Items, int TotalPages)> GetPagesAsync(int page = 1, string status = "publish", CancellationToken cancellationToken = default)
        => GetListAsync("pages", page, status, cancellationToken);
}
