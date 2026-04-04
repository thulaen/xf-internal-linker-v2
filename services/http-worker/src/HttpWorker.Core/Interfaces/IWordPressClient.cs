using System.Text.Json.Nodes;

namespace HttpWorker.Core.Interfaces;

public interface IWordPressClient
{
    Task<(List<JsonObject> Items, int TotalPages)> GetPostsAsync(int page = 1, string status = "publish", CancellationToken cancellationToken = default);
    Task<(List<JsonObject> Items, int TotalPages)> GetPagesAsync(int page = 1, string status = "publish", CancellationToken cancellationToken = default);
}
