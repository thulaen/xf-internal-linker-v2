using System.Security.Cryptography;
using System.Text;

namespace HttpWorker.Api.Middleware;

/// <summary>
/// Validates X-Internal-Token header on all endpoints except /api/v1/status (health probe).
/// The expected token is read from configuration key HttpWorker:Auth:InternalToken.
/// </summary>
public sealed class ApiKeyMiddleware(RequestDelegate next, IConfiguration configuration, ILogger<ApiKeyMiddleware> logger)
{
    private const string HeaderName = "X-Internal-Token";

    private static readonly HashSet<string> PublicPaths = new(StringComparer.OrdinalIgnoreCase)
    {
        "/api/v1/status",
    };

    public async Task InvokeAsync(HttpContext context)
    {
        var path = context.Request.Path.Value ?? string.Empty;

        // Allow health/status probes without auth
        if (PublicPaths.Any(p => path.StartsWith(p, StringComparison.OrdinalIgnoreCase)))
        {
            await next(context);
            return;
        }

        var expectedToken = configuration["HttpWorker:Auth:InternalToken"] ?? string.Empty;

        // If no token is configured, reject all requests (fail-closed)
        if (string.IsNullOrWhiteSpace(expectedToken))
        {
            logger.LogError("HttpWorker:Auth:InternalToken is not configured — rejecting request to {Path}", path);
            context.Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
            await context.Response.WriteAsJsonAsync(new { error = "service not configured" });
            return;
        }

        if (!context.Request.Headers.TryGetValue(HeaderName, out var providedToken) ||
            string.IsNullOrWhiteSpace(providedToken))
        {
            context.Response.StatusCode = StatusCodes.Status401Unauthorized;
            await context.Response.WriteAsJsonAsync(new { error = "missing authentication token" });
            return;
        }

        // Constant-time comparison to prevent timing attacks
        var expected = Encoding.UTF8.GetBytes(expectedToken);
        var provided = Encoding.UTF8.GetBytes(providedToken.ToString());
        if (!CryptographicOperations.FixedTimeEquals(expected, provided))
        {
            context.Response.StatusCode = StatusCodes.Status403Forbidden;
            await context.Response.WriteAsJsonAsync(new { error = "invalid authentication token" });
            return;
        }

        await next(context);
    }
}
