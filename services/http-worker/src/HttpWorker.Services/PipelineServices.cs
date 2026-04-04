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
    CeleryTaskEnqueuer celeryTaskEnqueuer,
    ILogger<ImportContentService> logger) : IImportContentService
{
    public async Task<ImportContentResult> ExecuteAsync(string jobId, ImportContentRequest request, CancellationToken cancellationToken)
    {
        logger.LogInformation("Starting Content Import Job {JobId}", jobId);
        
        var batch = new List<ImportContentMutation>();
        // Simulated: Logic for parsing out resources, fetching texts, creating embeddings.
        // We use UrlNormalizer when referencing URLs.
        
        if (batch.Count > 0)
        {
            await runtimeStore.PersistImportNodesAsync(batch, cancellationToken);
        
            var contentIds = batch.Select(b => b.ContentId).ToList();
            await celeryTaskEnqueuer.EnqueueClusterItemsAsync(contentIds);
        }

        return new ImportContentResult { ItemsSynced = batch.Count, ItemsUpdated = batch.Count };
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
            SingleWriter = false, 
            SingleReader = true 
        });

        // Reader & Math execution task
        var readerTask = Task.Run(async () =>
        {
            var destEmbeddingsArray = ArrayPool<float>.Shared.Rent(destinations.Count * 768);
            try
            {
                for (int i = 0; i < destinations.Count; i++)
                {
                    if (destinations[i].Embedding is not null && destinations[i].Embedding.Length == 768)
                    {
                        Array.Copy(destinations[i].Embedding, 0, destEmbeddingsArray, i * 768, 768);
                    }
                }

                int batchSize = 100;
                for (int i = 0; i < hosts.Count; i += batchSize)
                {
                    var chunk = hosts.Skip(i).Take(batchSize).ToList();
                    var hostEmbeddingsArray = ArrayPool<float>.Shared.Rent(chunk.Count * 768);
                    try
                    {
                        for (int j = 0; j < chunk.Count; j++)
                        {
                            if (chunk[j].Embedding is not null && chunk[j].Embedding.Length == 768)
                            {
                                Array.Copy(chunk[j].Embedding, 0, hostEmbeddingsArray, j * 768, 768);
                            }
                        }

                        // Placeholder for fixed P/Invoke mapping
                        /*
                        unsafe
                        {
                            fixed (float* dPtr = destEmbeddingsArray)
                            fixed (float* sPtr = hostEmbeddingsArray)
                            {
                                ScoringInterop.cscore_and_topk(dPtr, 768, ...);
                            }
                        }
                        */

                        foreach (var host in chunk)
                        {
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
                    finally
                    {
                        ArrayPool<float>.Shared.Return(hostEmbeddingsArray);
                    }
                }
            }
            finally
            {
                ArrayPool<float>.Shared.Return(destEmbeddingsArray);
                suggestionChannel.Writer.Complete();
            }
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
