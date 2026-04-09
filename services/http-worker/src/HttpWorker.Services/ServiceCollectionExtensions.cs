using HttpWorker.Core.Interfaces;
using HttpWorker.Services.Analytics;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using StackExchange.Redis;

namespace HttpWorker.Services;

public static class ServiceCollectionExtensions
{
    public static IServiceCollection AddHttpWorkerRuntime(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        services.Configure<HttpWorkerOptions>(configuration.GetSection("HttpWorker"));
        services.AddHttpClient("http-worker", client =>
        {
            client.Timeout = Timeout.InfiniteTimeSpan;
            client.DefaultRequestHeaders.ConnectionClose = true;
        });
        services.AddSingleton(sp =>
        {
            var options = sp.GetRequiredService<IOptions<HttpWorkerOptions>>().Value;
            var redisOptions = ConfigurationOptions.Parse(options.Redis.ConnectionString);
            redisOptions.AbortOnConnectFail = false;
            redisOptions.ConnectRetry = 1;
            redisOptions.ConnectTimeout = 5000;
            return ConnectionMultiplexer.Connect(redisOptions);
        });
        services.AddSingleton<IBrokenLinkService, BrokenLinkService>();
        services.AddSingleton<IBrokenLinkScanService, BrokenLinkScanService>();
        services.AddSingleton<IGraphSyncStore, PostgresGraphSyncStore>();
        services.AddSingleton<IGraphSyncService, GraphSyncService>();
        services.AddSingleton<IUrlFetchService, UrlFetchService>();
        services.AddSingleton<IHealthCheckService, HealthCheckService>();
        services.AddSingleton<ISitemapService, SitemapService>();
        services.AddSingleton<IJobQueueService, RedisJobQueueService>();
        services.AddSingleton<IProgressStreamService, RedisProgressStreamService>();
        services.AddSingleton<IPostgresRuntimeStore, PostgresRuntimeStore>();
        services.AddSingleton<IRuntimeTelemetryService, RedisRuntimeTelemetryService>();
        services.AddSingleton<ISchedulerDispatchService, SchedulerDispatchService>();
        services.AddSingleton<GSCAttributionService>();
        services.AddSingleton<WeightTunerDataCollector>();
        services.AddSingleton<WeightTunerService>();
        services.AddSingleton<HttpWorker.Services.External.CeleryTaskEnqueuer>();
        services.AddSingleton<HttpWorker.Core.Interfaces.IXenForoClient, HttpWorker.Services.External.XenForoClient>();
        services.AddSingleton<HttpWorker.Core.Interfaces.IWordPressClient, HttpWorker.Services.External.WordPressClient>();
        services.AddSingleton<HttpWorker.Core.Interfaces.ITextDistiller, HttpWorker.Services.Distillation.TextDistiller>();
        services.AddSingleton<IImportContentService, ImportContentService>();
        services.AddSingleton<IRunPipelineService, RunPipelineService>();
        services.AddSingleton<IGraphCandidateService, GraphCandidateService>();
        services.AddSingleton<TrafficDecayService>();
        services.AddSingleton<ICrawlSessionService, CrawlSessionService>();
        services.AddSingleton<JobProcessor>();
        return services;
    }
}
