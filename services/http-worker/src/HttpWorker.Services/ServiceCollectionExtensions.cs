using HttpWorker.Core.Interfaces;
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
        services.AddSingleton<IUrlFetchService, UrlFetchService>();
        services.AddSingleton<IHealthCheckService, HealthCheckService>();
        services.AddSingleton<ISitemapService, SitemapService>();
        services.AddSingleton<IJobQueueService, RedisJobQueueService>();
        services.AddSingleton<IRuntimeTelemetryService, RedisRuntimeTelemetryService>();
        services.AddSingleton<JobProcessor>();
        return services;
    }
}
