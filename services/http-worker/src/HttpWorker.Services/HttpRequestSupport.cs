using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using Microsoft.Extensions.Options;

namespace HttpWorker.Services;

internal sealed class HttpRequestSupport(IHttpClientFactory httpClientFactory, IOptions<HttpWorkerOptions> options)
{
    private static readonly HashSet<string> BlockedHeaders = new(StringComparer.OrdinalIgnoreCase)
    {
        "Host",
        "Connection",
        "Proxy-Connection",
        "X-Forwarded-For",
        "X-Forwarded-Host",
        "X-Real-IP",
        "Forwarded",
        "TE",
        "Trailer",
        "Transfer-Encoding",
        "Upgrade",
        "Content-Length",
    };

    private static readonly string[] BlockedHostNames =
    [
        "localhost",
        "metadata.google.internal",
        "metadata.azure.internal",
    ];

    private readonly HttpWorkerOptions _options = options.Value;

    public async Task<RequestExecutionResult> SendAsync(
        HttpMethod method,
        string url,
        int timeoutSeconds,
        int maxRedirectHops,
        Dictionary<string, string>? headers,
        string? userAgent,
        bool captureBody,
        CancellationToken cancellationToken)
    {
        var currentUri = EnsureAbsoluteHttpUrl(url);
        var normalizedVisited = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            NormalizeAbsoluteUrl(currentUri),
        };
        string redirectUrl = string.Empty;

        for (var hop = 0; ; hop++)
        {
            await EnsureAllowedAsync(currentUri, cancellationToken);
            using var request = new HttpRequestMessage(method, currentUri);
            ApplyHeaders(request, headers, userAgent);
            using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeoutCts.CancelAfter(TimeSpan.FromSeconds(timeoutSeconds));

            var stopwatch = Stopwatch.StartNew();

            try
            {
                var client = httpClientFactory.CreateClient("http-worker");
                using var response = await client.SendAsync(
                    request,
                    HttpCompletionOption.ResponseHeadersRead,
                    timeoutCts.Token);

                stopwatch.Stop();

                if (IsRedirect(response.StatusCode) && response.Headers.Location is not null)
                {
                    if (hop >= maxRedirectHops)
                    {
                        return RequestExecutionResult.TransportFailure("redirect hop limit exceeded");
                    }

                    var nextUri = response.Headers.Location.IsAbsoluteUri
                        ? response.Headers.Location
                        : new Uri(currentUri, response.Headers.Location);
                    var nextNormalized = NormalizeAbsoluteUrl(nextUri);
                    if (!normalizedVisited.Add(nextNormalized))
                    {
                        return RequestExecutionResult.TransportFailure("redirect loop detected");
                    }

                    redirectUrl = nextUri.ToString();
                    currentUri = nextUri;
                    continue;
                }

                string body = string.Empty;
                if (captureBody)
                {
                    await using var stream = await response.Content.ReadAsStreamAsync(timeoutCts.Token);
                    body = await ReadBodyWithLimitAsync(stream, timeoutCts.Token);
                }

                return RequestExecutionResult.Success(
                    statusCode: (int)response.StatusCode,
                    redirectUrl: redirectUrl,
                    body: body,
                    contentType: response.Content.Headers.ContentType?.MediaType ?? string.Empty,
                    latencyMs: stopwatch.ElapsedMilliseconds,
                    finalUri: currentUri);
            }
            catch (BlockedUrlException)
            {
                throw;
            }
            catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                return RequestExecutionResult.TransportFailure("request timed out");
            }
            catch (HttpRequestException ex)
            {
                return RequestExecutionResult.TransportFailure(string.IsNullOrWhiteSpace(ex.Message) ? "request failed" : ex.Message);
            }
            catch (InvalidOperationException ex)
            {
                return RequestExecutionResult.TransportFailure(string.IsNullOrWhiteSpace(ex.Message) ? "request failed" : ex.Message);
            }
        }
    }

    public async Task EnsureAllowedAsync(Uri uri, CancellationToken cancellationToken)
    {
        if (!uri.IsAbsoluteUri || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
        {
            throw new BlockedUrlException();
        }

        var host = uri.Host.Trim().ToLowerInvariant();
        if (BlockedHostNames.Contains(host, StringComparer.OrdinalIgnoreCase))
        {
            throw new BlockedUrlException();
        }

        if (host == "169.254.169.254")
        {
            throw new BlockedUrlException();
        }

        IPAddress[] addresses;
        try
        {
            addresses = await Dns.GetHostAddressesAsync(host, cancellationToken);
        }
        catch
        {
            throw new BlockedUrlException();
        }

        if (addresses.Length == 0 || addresses.Any(IsBlockedAddress))
        {
            throw new BlockedUrlException();
        }
    }

    public Uri EnsureAbsoluteHttpUrl(string rawUrl)
    {
        if (!Uri.TryCreate(rawUrl, UriKind.Absolute, out var uri))
        {
            throw new ValidationException("url must be an absolute http/https url");
        }

        if (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps)
        {
            throw new ValidationException("url must be an absolute http/https url");
        }

        return uri;
    }

    public string NormalizeAbsoluteUrl(Uri uri)
    {
        var builder = new UriBuilder(uri)
        {
            Host = uri.Host.ToLowerInvariant(),
            Fragment = string.Empty,
        };

        if ((builder.Scheme == Uri.UriSchemeHttp && builder.Port == 80) ||
            (builder.Scheme == Uri.UriSchemeHttps && builder.Port == 443))
        {
            builder.Port = -1;
        }

        return builder.Uri.AbsoluteUri.TrimEnd('/');
    }

    private static bool IsRedirect(HttpStatusCode statusCode)
    {
        return statusCode is HttpStatusCode.Moved or
            HttpStatusCode.Redirect or
            HttpStatusCode.TemporaryRedirect or
            HttpStatusCode.PermanentRedirect;
    }

    private static bool IsBlockedAddress(IPAddress address)
    {
        if (IPAddress.IsLoopback(address))
        {
            return true;
        }

        if (address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork)
        {
            var bytes = address.GetAddressBytes();
            return bytes[0] switch
            {
                0 => true,
                10 => true,
                127 => true,
                169 when bytes[1] == 254 => true,
                172 when bytes[1] is >= 16 and <= 31 => true,
                192 when bytes[1] == 168 => true,
                100 when bytes[1] is >= 64 and <= 127 => true,
                _ => false,
            };
        }

        if (address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetworkV6)
        {
            var bytes = address.GetAddressBytes();
            if (address.Equals(IPAddress.IPv6Loopback))
            {
                return true;
            }

            if ((bytes[0] & 0xFE) == 0xFC)
            {
                return true;
            }

            if (bytes[0] == 0xFE && (bytes[1] & 0xC0) == 0x80)
            {
                return true;
            }
        }

        return false;
    }

    private void ApplyHeaders(HttpRequestMessage request, Dictionary<string, string>? headers, string? userAgent)
    {
        if (!string.IsNullOrWhiteSpace(userAgent))
        {
            request.Headers.TryAddWithoutValidation("User-Agent", userAgent);
        }

        if (headers is null)
        {
            return;
        }

        foreach (var pair in headers)
        {
            if (string.IsNullOrWhiteSpace(pair.Key) || BlockedHeaders.Contains(pair.Key))
            {
                continue;
            }

            if (!request.Headers.TryAddWithoutValidation(pair.Key, pair.Value))
            {
                request.Content ??= new ByteArrayContent([]);
                request.Content.Headers.TryAddWithoutValidation(pair.Key, pair.Value);
            }
        }
    }

    private async Task<string> ReadBodyWithLimitAsync(Stream stream, CancellationToken cancellationToken)
    {
        var maxBytes = _options.Http.MaxBodyBytes;
        var buffer = new byte[8192];
        await using var target = new MemoryStream();

        while (target.Length < maxBytes)
        {
            var remaining = Math.Min(buffer.Length, maxBytes - (int)target.Length);
            var read = await stream.ReadAsync(buffer.AsMemory(0, remaining), cancellationToken);
            if (read == 0)
            {
                break;
            }

            await target.WriteAsync(buffer.AsMemory(0, read), cancellationToken);
        }

        return Encoding.UTF8.GetString(target.ToArray());
    }
}

internal sealed class RequestExecutionResult
{
    public bool IsTransportFailure { get; private init; }
    public int StatusCode { get; private init; }
    public string RedirectUrl { get; private init; } = string.Empty;
    public string Body { get; private init; } = string.Empty;
    public string ContentType { get; private init; } = string.Empty;
    public string? Error { get; private init; }
    public long LatencyMs { get; private init; }
    public Uri? FinalUri { get; private init; }

    public static RequestExecutionResult Success(
        int statusCode,
        string redirectUrl,
        string body,
        string contentType,
        long latencyMs,
        Uri finalUri)
    {
        return new RequestExecutionResult
        {
            StatusCode = statusCode,
            RedirectUrl = redirectUrl,
            Body = body,
            ContentType = contentType,
            LatencyMs = latencyMs,
            FinalUri = finalUri,
        };
    }

    public static RequestExecutionResult TransportFailure(string error)
    {
        return new RequestExecutionResult
        {
            IsTransportFailure = true,
            Error = error,
        };
    }
}
