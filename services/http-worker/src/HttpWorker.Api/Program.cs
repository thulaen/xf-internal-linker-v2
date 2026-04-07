using HttpWorker.Api.Middleware;
using HttpWorker.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddHttpWorkerRuntime(builder.Configuration);
builder.Services.AddControllers();

var app = builder.Build();

app.UseMiddleware<ErrorHandlingMiddleware>();
app.UseMiddleware<ApiKeyMiddleware>();
app.MapControllers();
app.Run();
