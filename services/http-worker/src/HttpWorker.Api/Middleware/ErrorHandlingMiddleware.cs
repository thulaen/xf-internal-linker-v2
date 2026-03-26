using System.Text.Json;

namespace HttpWorker.Api.Middleware;

public sealed class ErrorHandlingMiddleware(RequestDelegate next)
{
    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await next(context);
        }
        catch (HttpWorker.Services.BlockedUrlException)
        {
            await WriteJsonAsync(context, StatusCodes.Status400BadRequest, new { error = "blocked url" });
        }
        catch (HttpWorker.Services.MalformedSitemapException)
        {
            await WriteJsonAsync(context, StatusCodes.Status400BadRequest, new { error = "malformed sitemap xml" });
        }
        catch (HttpWorker.Services.ValidationException ex)
        {
            await WriteJsonAsync(context, StatusCodes.Status400BadRequest, new { error = ex.Message });
        }
        catch
        {
            await WriteJsonAsync(context, StatusCodes.Status500InternalServerError, new { error = "internal server error" });
        }
    }

    private static async Task WriteJsonAsync(HttpContext context, int statusCode, object payload)
    {
        context.Response.StatusCode = statusCode;
        context.Response.ContentType = "application/json";
        await context.Response.WriteAsync(JsonSerializer.Serialize(payload));
    }
}
