using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Options;

namespace HttpWorker.Services;

public sealed class UrlFetchService(
    IHttpClientFactory httpClientFactory,
    IOptions<HttpWorkerOptions> options) : IUrlFetchService
{
    private readonly HttpWorkerOptions _options = options.Value;
    private readonly HttpRequestSupport _http = new(httpClientFactory, options);

    public async Task<UrlFetchResponse> FetchAsync(UrlFetchRequest request, CancellationToken cancellationToken)
    {
        ValidateRequest(request);

        var fetchedItems = new UrlFetchResultItem[request.Urls!.Count];
        var concurrency = Math.Min(request.MaxConcurrency, _options.Http.MaxConcurrency);
        using var throttler = new SemaphoreSlim(concurrency);
        var tasks = request.Urls.Select(async (item, index) =>
        {
            await throttler.WaitAsync(cancellationToken);
            try
            {
                var result = await _http.SendAsync(
                    HttpMethod.Get,
                    item.Url,
                    request.TimeoutSeconds,
                    Math.Min(2, _options.Http.MaxRedirectHops),
                    request.Headers,
                    userAgent: null,
                    captureBody: true,
                    cancellationToken);

                fetchedItems[index] = new UrlFetchResultItem
                {
                    Url = item.Url,
                    Label = item.Label,
                    HttpStatus = result.IsTransportFailure ? 0 : result.StatusCode,
                    Body = result.IsTransportFailure ? string.Empty : result.Body,
                    ContentType = result.IsTransportFailure ? string.Empty : result.ContentType,
                    Error = result.IsTransportFailure ? result.Error : null,
                    FetchedAt = DateTimeOffset.UtcNow,
                };
            }
            finally
            {
                throttler.Release();
            }
        });

        await Task.WhenAll(tasks);

        return new UrlFetchResponse
        {
            Fetched = fetchedItems.ToList(),
            TotalFetched = fetchedItems.Length,
        };
    }

    private static void ValidateRequest(UrlFetchRequest? request)
    {
        if (request is null)
        {
            throw new ValidationException("request body is required");
        }

        if (request.Urls is null || request.Urls.Count == 0)
        {
            throw new ValidationException("urls list is required");
        }

        if (request.Urls.Count > 100)
        {
            throw new ValidationException("urls list must contain 1 to 100 items");
        }

        foreach (var item in request.Urls)
        {
            if (item is null || string.IsNullOrWhiteSpace(item.Url))
            {
                throw new ValidationException("url must be an absolute http/https url");
            }

            if (!Uri.TryCreate(item.Url, UriKind.Absolute, out var uri) ||
                (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
            {
                throw new ValidationException("url must be an absolute http/https url");
            }

            if (!string.IsNullOrEmpty(item.Label) && item.Label.Length > 200)
            {
                throw new ValidationException("label must be 200 chars or fewer");
            }
        }

        if (request.TimeoutSeconds < 1 || request.TimeoutSeconds > 120)
        {
            throw new ValidationException("timeout_seconds must be between 1 and 120");
        }

        if (request.MaxConcurrency < 1 || request.MaxConcurrency > 50)
        {
            throw new ValidationException("max_concurrency must be between 1 and 50");
        }
    }
}
