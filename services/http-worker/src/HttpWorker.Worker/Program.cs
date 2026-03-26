using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using HttpWorker.Worker;

var builder = Host.CreateApplicationBuilder(args);

builder.Services.Configure<HttpWorkerOptions>(builder.Configuration.GetSection("HttpWorker"));
builder.Services.AddHttpClient("http-worker", client =>
{
    client.Timeout = Timeout.InfiniteTimeSpan;
    client.DefaultRequestHeaders.ConnectionClose = true;
});
builder.Services.AddSingleton<IBrokenLinkService, BrokenLinkService>();
builder.Services.AddSingleton<IUrlFetchService, UrlFetchService>();
builder.Services.AddSingleton<IHealthCheckService, HealthCheckService>();
builder.Services.AddSingleton<ISitemapService, SitemapService>();
builder.Services.AddSingleton<IJobQueueService, RedisJobQueueService>();
builder.Services.AddSingleton<JobProcessor>();
builder.Services.AddHostedService<JobDispatcherWorker>();

var host = builder.Build();
await host.RunAsync();
