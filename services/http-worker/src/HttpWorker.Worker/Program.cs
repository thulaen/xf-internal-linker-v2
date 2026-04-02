using HttpWorker.Services;
using HttpWorker.Worker;

var builder = Host.CreateApplicationBuilder(args);

builder.Services.AddHttpWorkerRuntime(builder.Configuration);
builder.Services.AddHostedService<JobDispatcherWorker>();
builder.Services.AddHostedService<SchedulerWorker>();

var host = builder.Build();
await host.RunAsync();
