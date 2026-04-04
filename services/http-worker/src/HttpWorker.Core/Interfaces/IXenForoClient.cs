using System.Text.Json.Nodes;

namespace HttpWorker.Core.Interfaces;

public interface IXenForoClient
{
    Task<JsonObject> GetThreadsAsync(int nodeId, int page = 1, CancellationToken cancellationToken = default);
    Task<JsonObject> GetThreadAsync(int threadId, CancellationToken cancellationToken = default);
    Task<JsonObject> GetPostsAsync(int threadId, int page = 1, CancellationToken cancellationToken = default);
    Task<JsonObject> GetPostAsync(int postId, CancellationToken cancellationToken = default);
    Task<JsonObject> GetResourcesAsync(int categoryId, int page = 1, CancellationToken cancellationToken = default);
    Task<JsonObject> GetResourceUpdatesAsync(int resourceId, CancellationToken cancellationToken = default);
}
