using HttpWorker.Api.Middleware;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services;

var builder = WebApplication.CreateBuilder(args);

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
builder.Services.AddControllers();

var app = builder.Build();

app.UseMiddleware<ErrorHandlingMiddleware>();
app.MapControllers();
app.Run();
