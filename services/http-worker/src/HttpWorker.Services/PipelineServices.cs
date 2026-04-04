using System.Buffers;
using System.Threading.Channels;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Core.Text;
using HttpWorker.Services.External;
using HttpWorker.Services.Native;
using Microsoft.Extensions.Logging;

namespace HttpWorker.Services;

public class ImportContentService(
    IPostgresRuntimeStore runtimeStore, 
    IXenForoClient xenForoClient,
    ITextDistiller textDistiller,
    CeleryTaskEnqueuer celeryTaskEnqueuer,
    ILogger<ImportContentService> logger) : IImportContentService
{
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
                    // Sequential paging simulation
                    for (int page = 1; page <= 5; page++) 
                    {
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
                                Embedding = [] // Handled by Python layer post-persistence
                            };
                            batch.Add(mutation);
                        }
                    }
                }
                else if (scopeType == "resource_category")
                {
                    // Sequential paging for resources
                    for (int page = 1; page <= 5; page++) 
                    {
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
                                Embedding = [] // Handled by Python layer
                            };
                            batch.Add(mutation);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Failed to process scope {ScopePk}", scopePk);
            }
        }
        
        if (batch.Count > 0)
        {
            await runtimeStore.PersistImportNodesAsync(batch, cancellationToken);
        
            var contentIds = batch.Select(b => b.ContentId).ToList();
            await celeryTaskEnqueuer.EnqueueClusterItemsAsync(contentIds);
            
            // Note: C# side remains separated from embedding generation. 
            // A dedicated enqueue routine for Python's generate_embeddings would occur here depending on pipeline decisions.
        }

        return new ImportContentResult { ItemsSynced = batch.Count, ItemsUpdated = batch.Count };
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

public class RunPipelineService(IPostgresRuntimeStore runtimeStore, ILogger<RunPipelineService> logger) : IRunPipelineService
{
    public async Task<RunPipelineResult> ExecuteAsync(string jobId, RunPipelineRequest request, CancellationToken cancellationToken)
    {
        var runId = request.RunId;
        logger.LogInformation("Starting Pipeline Run {RunId}", runId);
        
        // Deserialize requested scopes properly for real implementation
        var hostScopeIds = new List<int>(); 
        var destScopeIds = new List<int>();

        var sw = System.Diagnostics.Stopwatch.StartNew();

        var destinations = await runtimeStore.GetDestinationNodesAsync(destScopeIds, cancellationToken);
        var hosts = await runtimeStore.GetHostNodesAsync(hostScopeIds, cancellationToken);

        if (destinations.Count == 0 || hosts.Count == 0)
            return new RunPipelineResult();

        var suggestionChannel = Channel.CreateBounded<PipelineSuggestion>(new BoundedChannelOptions(5000) 
        { 
            SingleWriter = true, 
            SingleReader = true 
        });

        // Reader & Math execution task
        var readerTask = Task.Run(async () =>
        {
            int destBatchSize = 800; // 800 * 1024 = 819,200 elements, safely under ~1M limit
            for (int destOuterIdx = 0; destOuterIdx < destinations.Count; destOuterIdx += destBatchSize)
            {
                int currentDestBatch = Math.Min(destBatchSize, destinations.Count - destOuterIdx);
                var destEmbeddingsArray = ArrayPool<float>.Shared.Rent(currentDestBatch * 1024);
                try
                {
                    Array.Clear(destEmbeddingsArray, 0, currentDestBatch * 1024);
                    for (int i = 0; i < currentDestBatch; i++)
                    {
                        var dest = destinations[destOuterIdx + i];
                        if (dest.Embedding is not null && dest.Embedding.Length == 1024)
                        {
                            Array.Copy(dest.Embedding, 0, destEmbeddingsArray, i * 1024, 1024);
                        }
                    }

                    int batchSize = 800;
                    for (int i = 0; i < hosts.Count; i += batchSize)
                    {
                        int currentBatch = Math.Min(batchSize, hosts.Count - i);
                        var hostEmbeddingsArray = ArrayPool<float>.Shared.Rent(currentBatch * 1024);
                        try
                        {
                            Array.Clear(hostEmbeddingsArray, 0, currentBatch * 1024);
                            for (int j = 0; j < currentBatch; j++)
                            {
                                var host = hosts[i + j];
                                if (host.Embedding is not null && host.Embedding.Length == 1024)
                                {
                                    Array.Copy(host.Embedding, 0, hostEmbeddingsArray, j * 1024, 1024);
                                }
                            }

                            // Placeholder for fixed P/Invoke mapping
                            /*
                            unsafe
                            {
                                fixed (float* dPtr = destEmbeddingsArray)
                                fixed (float* sPtr = hostEmbeddingsArray)
                                {
                                    ScoringInterop.cscore_and_topk(dPtr, 1024, ...);
                                }
                            }
                            */

                            // Emit mock suggestions (only on the first pass of destinations so we don't multiply host count)
                            if (destOuterIdx == 0)
                            {
                                for (int j = 0; j < currentBatch; j++)
                                {
                                    var host = hosts[i + j];
                                    await suggestionChannel.Writer.WriteAsync(new PipelineSuggestion
                                    {
                                        HostContentId = host.ContentId,
                                        HostSentenceId = host.SentenceId,
                                        DestinationContentId = destinations[0].ContentId, 
                                        CompositeScore = 0.9f,
                                        ExactMatchAnchor = host.SentenceText
                                    }, cancellationToken);
                                }
                            }
                        }
                        finally
                        {
                            ArrayPool<float>.Shared.Return(hostEmbeddingsArray);
                        }
                    }
                }
                finally
                {
                    ArrayPool<float>.Shared.Return(destEmbeddingsArray);
                }
            }
            suggestionChannel.Writer.Complete();
        });

        int suggestionsCreated = 0;
        var writerTask = Task.Run(async () =>
        {
            var batched = new List<PipelineSuggestion>();
            await foreach (var item in suggestionChannel.Reader.ReadAllAsync(cancellationToken))
            {
                batched.Add(item);
                suggestionsCreated++;
                if (batched.Count >= 500)
                {
                    await runtimeStore.PersistPipelineSuggestionsAsync(runId, batched, cancellationToken);
                    batched.Clear();
                }
            }
            if (batched.Count > 0)
            {
                await runtimeStore.PersistPipelineSuggestionsAsync(runId, batched, cancellationToken);
            }
        });

        await Task.WhenAll(readerTask, writerTask);

        sw.Stop();
        return new RunPipelineResult 
        { 
            SuggestionsCreated = suggestionsCreated,
            DurationSeconds = sw.Elapsed.TotalSeconds,
            ItemsInScope = hosts.Count + destinations.Count
        };
    }
}
