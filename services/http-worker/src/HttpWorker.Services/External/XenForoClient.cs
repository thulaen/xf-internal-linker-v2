using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json.Nodes;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Logging;

namespace HttpWorker.Services.External;

public class XenForoClient : IXenForoClient
{
    private readonly HttpClient _httpClient;
    private readonly ILogger<XenForoClient> _logger;

    public XenForoClient(HttpClient httpClient, ILogger<XenForoClient> logger)
    {
        _httpClient = httpClient;
        _logger = logger;
    }

    private async Task<JsonObject> GetAsync(string endpoint, CancellationToken cancellationToken)
    {
        var response = await _httpClient.GetAsync(endpoint, cancellationToken);
        response.EnsureSuccessStatusCode();
        var content = await response.Content.ReadFromJsonAsync<JsonObject>(cancellationToken: cancellationToken);
        return content ?? new JsonObject();
    }

    public Task<JsonObject> GetThreadsAsync(int nodeId, int page = 1, CancellationToken cancellationToken = default)
        => GetAsync($"api/threads/?node_id={nodeId}&page={page}", cancellationToken);

    public Task<JsonObject> GetThreadAsync(int threadId, CancellationToken cancellationToken = default)
        => GetAsync($"api/threads/{threadId}/", cancellationToken);

    public Task<JsonObject> GetPostsAsync(int threadId, int page = 1, CancellationToken cancellationToken = default)
        => GetAsync($"api/posts/?thread_id={threadId}&page={page}", cancellationToken);

    public Task<JsonObject> GetPostAsync(int postId, CancellationToken cancellationToken = default)
        => GetAsync($"api/posts/{postId}/", cancellationToken);

    public Task<JsonObject> GetResourcesAsync(int categoryId, int page = 1, CancellationToken cancellationToken = default)
        => GetAsync($"api/resources/?resource_category_id={categoryId}&page={page}", cancellationToken);

    public Task<JsonObject> GetResourceUpdatesAsync(int resourceId, CancellationToken cancellationToken = default)
        => GetAsync($"api/resources/{resourceId}/updates", cancellationToken);
}
