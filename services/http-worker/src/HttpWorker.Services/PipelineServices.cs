using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Core.Text;
using HttpWorker.Services.External;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace HttpWorker.Services;

public class ImportContentService(
    IPostgresRuntimeStore runtimeStore,
    IXenForoClient xenForoClient,
    IWordPressClient wordPressClient,
    ITextDistiller textDistiller,
    IGraphSyncService graphSyncService,
    IOptions<HttpWorkerOptions> options,
    ILogger<ImportContentService> logger) : IImportContentService
{
    private readonly int _importMaxPages = options.Value.Http.ImportMaxPages;
    public async Task<ImportContentResult> ExecuteAsync(string jobId, ImportContentRequest request, CancellationToken cancellationToken)
    {
        logger.LogInformation("Starting Content Import Job {JobId}", jobId);
        
        var batch = new List<ImportContentMutation>();
        var scopes = await runtimeStore.GetScopesAsync(request.ScopeIds, cancellationToken);

        foreach (var scope in scopes)
        {
            var (scopePk, externalScopeId, scopeType) = scope;
            logger.LogInformation("Processing Scope: PK={ScopePk}, ExtID={ExtId}, Type={Type}", scopePk, externalScopeId, scopeType);

            try
            {
                if (scopeType == "node")
                {
                    // Sequential paging — cap controlled by HttpWorker:Http:ImportMaxPages
                    for (int page = 1; page <= _importMaxPages; page++)
                    {
                        logger.LogInformation("Importing page {Page}/{Max} for scope {ScopePk}", page, _importMaxPages, scopePk);
                        var response = await xenForoClient.GetThreadsAsync(externalScopeId, page, cancellationToken);
                        if (response == null || !response.ContainsKey("threads")) break;

                        var threadsArray = response["threads"]?.AsArray();
                        if (threadsArray == null || threadsArray.Count == 0) break;

                        foreach (var thread in threadsArray)
                        {
                            if (thread == null) continue;
                            int contentId = thread["thread_id"]?.GetValue<int>() ?? 0;
                            if (contentId == 0) continue;

                            string title = thread["title"]?.GetValue<string>() ?? string.Empty;
                            string url = thread["view_url"]?.GetValue<string>() ?? string.Empty;
                            int viewCount = thread["view_count"]?.GetValue<int>() ?? 0;
                            int replyCount = thread["reply_count"]?.GetValue<int>() ?? 0;

                            // Mocked fetch for thread body (since XenForo threads API often doesn't return full body)
                            var postResponse = await xenForoClient.GetPostsAsync(contentId, 1, cancellationToken);
                            string rawBody = string.Empty;
                            int? firstPostId = null;
                            
                            var postsArray = postResponse?["posts"]?.AsArray();
                            if (postsArray != null && postsArray.Count > 0)
                            {
                                var firstPost = postsArray[0];
                                rawBody = firstPost?["message"]?.GetValue<string>() ?? string.Empty;
                                firstPostId = firstPost?["post_id"]?.GetValue<int>();
                            }

                            string cleanText = ScrubBbcode(rawBody);
                            string distilled = await textDistiller.DistillBodyAsync(new[] { title, cleanText }, 3, cancellationToken);

                            var mutation = new ImportContentMutation
                            {
                                ScopeId = scopePk,
                                ContentId = contentId,
                                ContentType = "thread",
                                Url = UrlNormalizer.NormalizeInternalUrl(url),
                                Title = title,
                                RawBody = rawBody,
                                CleanText = cleanText,
                                DistilledText = distilled,
                                ViewCount = viewCount,
                                ReplyCount = replyCount,
                                XfPostId = firstPostId,
                                ContentHash = GenerateHash(rawBody),
                                Sentences = ExtractSentences(cleanText),
                            };
                            batch.Add(mutation);
                        }
                    }
                }
                else if (scopeType == "resource_category")
                {
                    // Sequential paging — cap controlled by HttpWorker:Http:ImportMaxPages
                    for (int page = 1; page <= _importMaxPages; page++)
                    {
                        logger.LogInformation("Importing page {Page}/{Max} for scope {ScopePk}", page, _importMaxPages, scopePk);
                        var response = await xenForoClient.GetResourcesAsync(externalScopeId, page, cancellationToken);
                        if (response == null || !response.ContainsKey("resources")) break;

                        var resourcesArray = response["resources"]?.AsArray();
                        if (resourcesArray == null || resourcesArray.Count == 0) break;

                        foreach (var resource in resourcesArray)
                        {
                            if (resource == null) continue;
                            int contentId = resource["resource_id"]?.GetValue<int>() ?? 0;
                            if (contentId == 0) continue;

                            string title = resource["title"]?.GetValue<string>() ?? string.Empty;
                            string url = resource["view_url"]?.GetValue<string>() ?? string.Empty;
                            int viewCount = resource["view_count"]?.GetValue<int>() ?? 0;
                            int reviewCount = resource["review_count"]?.GetValue<int>() ?? 0;
                            int downloadCount = resource["download_count"]?.GetValue<int>() ?? 0;

                            // Fetch resource updates/description
                            var updateResponse = await xenForoClient.GetResourceUpdatesAsync(contentId, cancellationToken);
                            string rawBody = string.Empty;
                            var updatesArray = updateResponse?["description_updates"]?.AsArray();
                            if (updatesArray != null && updatesArray.Count > 0)
                            {
                                rawBody = updatesArray[0]?["message"]?.GetValue<string>() ?? string.Empty;
                            }

                            string cleanText = ScrubBbcode(rawBody);
                            string distilled = await textDistiller.DistillBodyAsync(new[] { title, cleanText }, 3, cancellationToken);

                            var mutation = new ImportContentMutation
                            {
                                ScopeId = scopePk,
                                ContentId = contentId,
                                ContentType = "resource",
                                Url = UrlNormalizer.NormalizeInternalUrl(url),
                                Title = title,
                                RawBody = rawBody,
                                CleanText = cleanText,
                                DistilledText = distilled,
                                ViewCount = viewCount,
                                ReplyCount = reviewCount,
                                DownloadCount = downloadCount,
                                ContentHash = GenerateHash(rawBody),
                                Sentences = ExtractSentences(cleanText),
                            };
                            batch.Add(mutation);
                        }
                    }
                }
                else if (scopeType == "wp_posts" || scopeType == "wp_pages")
                {
                    bool isPage = scopeType == "wp_pages";
                    // Sequential paging — cap controlled by HttpWorker:Http:ImportMaxPages
                    for (int page = 1; page <= _importMaxPages; page++)
                    {
                        logger.LogInformation("Importing page {Page}/{Max} for scope {ScopePk}", page, _importMaxPages, scopePk);
                        var (items, totalPages) = isPage
                            ? await wordPressClient.GetPagesAsync(page, "publish", cancellationToken)
                            : await wordPressClient.GetPostsAsync(page, "publish", cancellationToken);

                        if (items == null || items.Count == 0) break;

                        foreach (var item in items)
                        {
                            if (item == null) continue;
                            int contentId = item["id"]?.GetValue<int>() ?? 0;
                            if (contentId == 0) continue;

                            string title = item["title"]?["rendered"]?.GetValue<string>() ?? string.Empty;
                            string url = item["link"]?.GetValue<string>() ?? string.Empty;
                            // Raw editorial body directly from the REST API JSON payload, completely bypassing page templates/chrome
                            string rawBody = item["content"]?["rendered"]?.GetValue<string>() ?? string.Empty;

                            string cleanText = ScrubBbcode(rawBody); // scrub html tags
                            string distilled = await textDistiller.DistillBodyAsync(new[] { title, cleanText }, 3, cancellationToken);

                            var mutation = new ImportContentMutation
                            {
                                ScopeId = scopePk,
                                ContentId = contentId,
                                ContentType = isPage ? "wp_page" : "wp_post",
                                Url = UrlNormalizer.NormalizeInternalUrl(url),
                                Title = HttpWorker.Core.Text.UrlNormalizer.NormalizeInternalUrl(title), // not quite, just keep title
                                RawBody = rawBody,
                                CleanText = cleanText,
                                DistilledText = distilled,
                                ViewCount = 0, // WP API doesn't return view_count natively usually
                                ReplyCount = 0,
                                DownloadCount = 0,
                                ContentHash = GenerateHash(rawBody),
                                Sentences = ExtractSentences(cleanText),
                            };
                            
                            // Revert accidental title modification
                            mutation.Title = ScrubBbcode(title); // Decode HTML entities in title
                            
                            batch.Add(mutation);
                        }
                        
                        if (page >= totalPages) break;
                    }
                }
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Failed to process scope {ScopePk}", scopePk);
            }
        }
        
        var updatedPks = new List<int>();
        if (batch.Count > 0)
        {
            var contentPkList = await runtimeStore.PersistImportNodesAsync(batch, cancellationToken);
            updatedPks = contentPkList.ToList();
        
            // Trigger the C# graph extraction (it operates purely on the persisted RawBbcode boundary, keeping layout chrome out)
            await graphSyncService.RefreshAsync(new GraphSyncRefreshRequest
            {
                ContentItemPks = updatedPks
            }, cancellationToken);
        }

        return new ImportContentResult 
        { 
            ItemsSynced = batch.Count, 
            ItemsUpdated = batch.Count,
            UpdatedPks = updatedPks
        };
    }

    private static string ScrubBbcode(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return string.Empty;
        var noTags = System.Text.RegularExpressions.Regex.Replace(raw, @"\[.*?\]", " ");
        var noHtml = System.Text.RegularExpressions.Regex.Replace(noTags, @"<.*?>", " ");
        return System.Text.RegularExpressions.Regex.Replace(noHtml, @"\s+", " ").Trim();
    }

    private static List<SentenceMutation> ExtractSentences(string cleanText)
    {
        var sentences = new List<SentenceMutation>();
        if (string.IsNullOrWhiteSpace(cleanText)) return sentences;

        var parts = System.Text.RegularExpressions.Regex.Split(cleanText, @"(?<=[\.!\?])\s+");
        int currentPos = 0;
        int wordPos = 0;

        for (int i = 0; i < parts.Length; i++)
        {
            var part = parts[i].Trim();
            if (string.IsNullOrWhiteSpace(part)) continue;

            int len = part.Length;
            int words = part.Split(' ', StringSplitOptions.RemoveEmptyEntries).Length;

            sentences.Add(new SentenceMutation
            {
                Text = part,
                Position = i,
                CharCount = len,
                StartChar = currentPos,
                EndChar = currentPos + len,
                WordPosition = wordPos
            });

            currentPos += len + 1; // +1 for the space
            wordPos += words;
        }

        return sentences;
    }

    private static string GenerateHash(string text)
    {
        using var sha256 = System.Security.Cryptography.SHA256.Create();
        var bytes = sha256.ComputeHash(System.Text.Encoding.UTF8.GetBytes(text));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}
