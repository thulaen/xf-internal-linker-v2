using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Options;

namespace HttpWorker.Services;

public sealed class BrokenLinkService(
    IHttpClientFactory httpClientFactory,
    IOptions<HttpWorkerOptions> options) : IBrokenLinkService
{
    private readonly HttpWorkerOptions _options = options.Value;
    private readonly HttpRequestSupport _http = new(httpClientFactory, options);

    public async Task<BrokenLinkCheckResponse> CheckAsync(BrokenLinkCheckRequest request, CancellationToken cancellationToken)
    {
        ValidateRequest(request);

        var checkedItems = new BrokenLinkCheckItem[request.Urls!.Count];
        var concurrency = Math.Min(request.MaxConcurrency, _options.Http.MaxConcurrency);
        using var throttler = new SemaphoreSlim(concurrency);
        var tasks = request.Urls.Select(async (item, index) =>
        {
            await throttler.WaitAsync(cancellationToken);
            try
            {
                checkedItems[index] = await CheckOneAsync(item, request, cancellationToken);
            }
            finally
            {
                throttler.Release();
            }
        });

        await Task.WhenAll(tasks);

        return new BrokenLinkCheckResponse
        {
            Checked = checkedItems.ToList(),
            TotalChecked = checkedItems.Length,
            TotalFlagged = checkedItems.Count(item =>
                item.HttpStatus == 0 ||
                item.HttpStatus >= 400 ||
                !string.IsNullOrEmpty(item.RedirectUrl)),
        };
    }

    private async Task<BrokenLinkCheckItem> CheckOneAsync(
        BrokenLinkUrlRequest item,
        BrokenLinkCheckRequest request,
        CancellationToken cancellationToken)
    {
        var now = DateTimeOffset.UtcNow;
        var result = await _http.SendAsync(
            HttpMethod.Head,
            item.Url,
            request.TimeoutSeconds,
            Math.Min(3, _options.Http.MaxRedirectHops),
            headers: null,
            userAgent: request.UserAgent,
            captureBody: false,
            cancellationToken);

        if (result.StatusCode is 405 or 501)
        {
            result = await _http.SendAsync(
                HttpMethod.Get,
                item.Url,
                request.TimeoutSeconds,
                Math.Min(3, _options.Http.MaxRedirectHops),
                headers: null,
                userAgent: request.UserAgent,
                captureBody: false,
                cancellationToken);
        }

        return new BrokenLinkCheckItem
        {
            Url = item.Url,
            SourceContentId = item.SourceContentId,
            HttpStatus = result.IsTransportFailure ? 0 : result.StatusCode,
            RedirectUrl = result.IsTransportFailure ? string.Empty : result.RedirectUrl,
            Error = result.IsTransportFailure ? result.Error : null,
            CheckedAt = now,
        };
    }

    private static void ValidateRequest(BrokenLinkCheckRequest? request)
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

            if (item.SourceContentId <= 0)
            {
                throw new ValidationException("source_content_id must be a positive integer");
            }
        }

        if (request.TimeoutSeconds < 1 || request.TimeoutSeconds > 60)
        {
            throw new ValidationException("timeout_seconds must be between 1 and 60");
        }

        if (request.MaxConcurrency < 1 || request.MaxConcurrency > 200)
        {
            throw new ValidationException("max_concurrency must be between 1 and 200");
        }
    }
}
