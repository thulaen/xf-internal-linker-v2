using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Options;

namespace HttpWorker.Services;

public sealed class HealthCheckService(
    IHttpClientFactory httpClientFactory,
    IOptions<HttpWorkerOptions> options) : IHealthCheckService
{
    private readonly HttpWorkerOptions _options = options.Value;
    private readonly HttpRequestSupport _http = new(httpClientFactory, options);

    public async Task<HealthCheckResponse> CheckAsync(HealthCheckRequest request, CancellationToken cancellationToken)
    {
        ValidateRequest(request);

        var checkedItems = new HealthCheckItem[request.Urls!.Count];
        var concurrency = Math.Min(request.MaxConcurrency, _options.Http.MaxConcurrency);
        using var throttler = new SemaphoreSlim(concurrency);
        var tasks = request.Urls.Select(async (url, index) =>
        {
            await throttler.WaitAsync(cancellationToken);
            try
            {
                var result = await _http.SendAsync(
                    HttpMethod.Head,
                    url,
                    request.TimeoutSeconds,
                    0,
                    headers: null,
                    userAgent: null,
                    captureBody: false,
                    cancellationToken);

                checkedItems[index] = new HealthCheckItem
                {
                    Url = url,
                    Reachable = !result.IsTransportFailure,
                    HttpStatus = result.IsTransportFailure ? 0 : result.StatusCode,
                    LatencyMs = result.LatencyMs,
                    Error = result.IsTransportFailure ? result.Error : null,
                    CheckedAt = DateTimeOffset.UtcNow,
                };
            }
            finally
            {
                throttler.Release();
            }
        });

        await Task.WhenAll(tasks);

        return new HealthCheckResponse
        {
            Checked = checkedItems.ToList(),
            TotalChecked = checkedItems.Length,
            TotalUnreachable = checkedItems.Count(item => !item.Reachable),
        };
    }

    private static void ValidateRequest(HealthCheckRequest? request)
    {
        if (request is null)
        {
            throw new ValidationException("request body is required");
        }

        if (request.Urls is null || request.Urls.Count == 0)
        {
            throw new ValidationException("urls list is required");
        }

        if (request.Urls.Count > 1000)
        {
            throw new ValidationException("urls list must contain 1 to 1000 items");
        }

        foreach (var url in request.Urls)
        {
            if (string.IsNullOrWhiteSpace(url) ||
                !Uri.TryCreate(url, UriKind.Absolute, out var uri) ||
                (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
            {
                throw new ValidationException("url must be an absolute http/https url");
            }
        }

        if (request.TimeoutSeconds < 1 || request.TimeoutSeconds > 30)
        {
            throw new ValidationException("timeout_seconds must be between 1 and 30");
        }

        if (request.MaxConcurrency < 1 || request.MaxConcurrency > 500)
        {
            throw new ValidationException("max_concurrency must be between 1 and 500");
        }
    }
}
