using System.Net;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Services;
using Microsoft.Extensions.Options;
using Xunit;

namespace HttpWorker.Tests;

public sealed class BrokenLinkServiceTests
{
    [Fact]
    public async Task Returns200Response()
    {
        var service = CreateService(_ => new HttpResponseMessage(HttpStatusCode.OK));

        var result = await service.CheckAsync(Request("https://example.com/a"), CancellationToken.None);

        Assert.Equal(200, result.Checked.Single().HttpStatus);
        Assert.Equal(0, result.TotalFlagged);
    }

    [Fact]
    public async Task Returns404Response()
    {
        var service = CreateService(_ => new HttpResponseMessage(HttpStatusCode.NotFound));

        var result = await service.CheckAsync(Request("https://example.com/a"), CancellationToken.None);

        Assert.Equal(404, result.Checked.Single().HttpStatus);
        Assert.Equal(1, result.TotalFlagged);
    }

    [Fact]
    public async Task FallsBackToGetAfter405()
    {
        var calls = 0;
        var service = CreateService(request =>
        {
            calls++;
            return request.Method == HttpMethod.Head
                ? new HttpResponseMessage(HttpStatusCode.MethodNotAllowed)
                : new HttpResponseMessage(HttpStatusCode.OK);
        });

        var result = await service.CheckAsync(Request("https://example.com/a"), CancellationToken.None);

        Assert.Equal(2, calls);
        Assert.Equal(200, result.Checked.Single().HttpStatus);
    }

    [Fact]
    public async Task TimeoutReturnsZeroAndError()
    {
        Func<HttpRequestMessage, HttpResponseMessage> responder = _ => throw new TaskCanceledException("timeout");
        var service = CreateService(responder);

        var result = await service.CheckAsync(Request("https://example.com/a"), CancellationToken.None);

        var item = result.Checked.Single();
        Assert.Equal(0, item.HttpStatus);
        Assert.NotNull(item.Error);
    }

    [Fact]
    public async Task MaxConcurrencyCapIsRespected()
    {
        var active = 0;
        var peak = 0;
        var service = CreateService(async _ =>
        {
            var current = Interlocked.Increment(ref active);
            peak = Math.Max(peak, current);
            await Task.Delay(50);
            Interlocked.Decrement(ref active);
            return new HttpResponseMessage(HttpStatusCode.OK);
        }, maxConcurrency: 2);

        var request = new BrokenLinkCheckRequest
        {
            Urls =
            [
                new BrokenLinkUrlRequest { Url = "https://example.com/1", SourceContentId = 1 },
                new BrokenLinkUrlRequest { Url = "https://example.com/2", SourceContentId = 2 },
                new BrokenLinkUrlRequest { Url = "https://example.com/3", SourceContentId = 3 },
                new BrokenLinkUrlRequest { Url = "https://example.com/4", SourceContentId = 4 },
            ],
            TimeoutSeconds = 5,
            MaxConcurrency = 50,
            UserAgent = "XF Internal Linker V2",
        };

        await service.CheckAsync(request, CancellationToken.None);

        Assert.True(peak <= 2);
    }

    [Fact]
    public async Task BlockedUrlThrowsBlockedUrlException()
    {
        var service = CreateService(_ => new HttpResponseMessage(HttpStatusCode.OK));

        await Assert.ThrowsAsync<BlockedUrlException>(() =>
            service.CheckAsync(Request("http://127.0.0.1/a"), CancellationToken.None));
    }

    [Fact]
    public async Task RedirectLoopReturnsZeroAndError()
    {
        var service = CreateService(_ =>
        {
            var response = new HttpResponseMessage(HttpStatusCode.Moved);
            response.Headers.Location = new Uri("https://example.com/a");
            return response;
        });

        var result = await service.CheckAsync(Request("https://example.com/a"), CancellationToken.None);

        var item = result.Checked.Single();
        Assert.Equal(0, item.HttpStatus);
        Assert.Equal("redirect loop detected", item.Error);
    }

    private static BrokenLinkCheckRequest Request(string url)
    {
        return new BrokenLinkCheckRequest
        {
            Urls = [new BrokenLinkUrlRequest { Url = url, SourceContentId = 123 }],
            TimeoutSeconds = 5,
            MaxConcurrency = 10,
            UserAgent = "XF Internal Linker V2",
        };
    }

    private static BrokenLinkService CreateService(
        Func<HttpRequestMessage, HttpResponseMessage> responder,
        int maxConcurrency = 100)
    {
        return CreateService(request => Task.FromResult(responder(request)), maxConcurrency);
    }

    private static BrokenLinkService CreateService(
        Func<HttpRequestMessage, Task<HttpResponseMessage>> responder,
        int maxConcurrency = 100)
    {
        var factory = new FakeHttpClientFactory(new DelegateHandler(responder));
        return new BrokenLinkService(factory, Options.Create(new HttpWorkerOptions
        {
            Http = new HttpOptions
            {
                MaxConcurrency = maxConcurrency,
                MaxBodyBytes = 5242880,
                MaxRedirectHops = 3,
            },
        }));
    }
}

internal sealed class FakeHttpClientFactory(HttpMessageHandler handler) : IHttpClientFactory
{
    public HttpClient CreateClient(string name)
    {
        return new HttpClient(handler, disposeHandler: false)
        {
            Timeout = Timeout.InfiniteTimeSpan,
        };
    }
}

internal sealed class DelegateHandler(Func<HttpRequestMessage, Task<HttpResponseMessage>> responder) : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        return responder(request);
    }
}
