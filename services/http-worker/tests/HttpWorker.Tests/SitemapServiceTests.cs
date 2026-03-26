using System.Net;
using System.Text;
using HttpWorker.Core.Contracts.V1;
using HttpWorker.Services;
using Microsoft.Extensions.Options;
using Xunit;

namespace HttpWorker.Tests;

public sealed class SitemapServiceTests
{
    [Fact]
    public async Task UrlsetWithThreeUrlsWorks()
    {
        var service = CreateService(new Dictionary<string, string>
        {
            ["https://example.com/sitemap.xml"] = """
                <urlset>
                  <url><loc>https://example.com/a</loc></url>
                  <url><loc>https://example.com/b</loc></url>
                  <url><loc>https://example.com/c</loc></url>
                </urlset>
                """
        });

        var result = await service.CrawlAsync(Request("https://example.com/sitemap.xml"), CancellationToken.None);

        Assert.Equal(3, result.TotalDiscovered);
        Assert.False(result.Truncated);
    }

    [Fact]
    public async Task SitemapIndexWithTwoChildrenWorks()
    {
        var service = CreateService(new Dictionary<string, string>
        {
            ["https://example.com/sitemap.xml"] = """
                <sitemapindex>
                  <sitemap><loc>https://example.com/child-1.xml</loc></sitemap>
                  <sitemap><loc>https://example.com/child-2.xml</loc></sitemap>
                </sitemapindex>
                """,
            ["https://example.com/child-1.xml"] = "<urlset><url><loc>https://example.com/a</loc></url></urlset>",
            ["https://example.com/child-2.xml"] = "<urlset><url><loc>https://example.com/b</loc></url></urlset>",
        });

        var result = await service.CrawlAsync(Request("https://example.com/sitemap.xml"), CancellationToken.None);

        Assert.Equal(2, result.TotalDiscovered);
    }

    [Fact]
    public async Task TruncatesAtMaxUrls()
    {
        var service = CreateService(new Dictionary<string, string>
        {
            ["https://example.com/sitemap.xml"] = """
                <urlset>
                  <url><loc>https://example.com/a</loc></url>
                  <url><loc>https://example.com/b</loc></url>
                  <url><loc>https://example.com/c</loc></url>
                </urlset>
                """
        });

        var result = await service.CrawlAsync(Request("https://example.com/sitemap.xml", maxUrls: 2), CancellationToken.None);

        Assert.Equal(2, result.TotalDiscovered);
        Assert.True(result.Truncated);
    }

    [Fact]
    public async Task DuplicateChildSitemapsAreFetchedOnce()
    {
        var counts = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        var service = CreateService(new Dictionary<string, string>
        {
            ["https://example.com/sitemap.xml"] = """
                <sitemapindex>
                  <sitemap><loc>https://example.com/child.xml</loc></sitemap>
                  <sitemap><loc>https://example.com/child.xml</loc></sitemap>
                </sitemapindex>
                """,
            ["https://example.com/child.xml"] = "<urlset><url><loc>https://example.com/a</loc></url></urlset>",
        }, counts);

        await service.CrawlAsync(Request("https://example.com/sitemap.xml"), CancellationToken.None);

        Assert.Equal(1, counts["https://example.com/child.xml"]);
    }

    [Fact]
    public async Task DuplicateDiscoveredUrlsAreDeduplicated()
    {
        var service = CreateService(new Dictionary<string, string>
        {
            ["https://example.com/sitemap.xml"] = """
                <urlset>
                  <url><loc>https://example.com/a</loc></url>
                  <url><loc>https://example.com/a</loc></url>
                </urlset>
                """
        });

        var result = await service.CrawlAsync(Request("https://example.com/sitemap.xml"), CancellationToken.None);

        Assert.Single(result.DiscoveredUrls);
    }

    [Fact]
    public async Task CycleProtectionStopsInfiniteRecursion()
    {
        var service = CreateService(new Dictionary<string, string>
        {
            ["https://example.com/sitemap.xml"] = "<sitemapindex><sitemap><loc>https://example.com/child.xml</loc></sitemap></sitemapindex>",
            ["https://example.com/child.xml"] = "<sitemapindex><sitemap><loc>https://example.com/child.xml</loc></sitemap></sitemapindex>",
        });

        var result = await service.CrawlAsync(Request("https://example.com/sitemap.xml"), CancellationToken.None);

        Assert.Equal(0, result.TotalDiscovered);
    }

    [Fact]
    public async Task ChildFetchCapIsEnforced()
    {
        var map = new Dictionary<string, string>
        {
            ["https://example.com/sitemap.xml"] = "<sitemapindex>" +
                string.Concat(Enumerable.Range(1, 101).Select(i => $"<sitemap><loc>https://example.com/{i}.xml</loc></sitemap>")) +
                "</sitemapindex>",
        };

        foreach (var index in Enumerable.Range(1, 101))
        {
            map[$"https://example.com/{index}.xml"] = $"<urlset><url><loc>https://example.com/page-{index}</loc></url></urlset>";
        }

        var service = CreateService(map);
        var result = await service.CrawlAsync(Request("https://example.com/sitemap.xml"), CancellationToken.None);

        Assert.Equal(100, result.TotalDiscovered);
        Assert.True(result.Truncated);
    }

    [Fact]
    public async Task MalformedXmlThrowsExpectedException()
    {
        var service = CreateService(new Dictionary<string, string>
        {
            ["https://example.com/sitemap.xml"] = "<urlset><url></urlset>",
        });

        var exception = await Assert.ThrowsAsync<MalformedSitemapException>(() =>
            service.CrawlAsync(Request("https://example.com/sitemap.xml"), CancellationToken.None));

        Assert.Equal("malformed sitemap xml", exception.Message);
    }

    [Fact]
    public async Task BlockedChildSitemapIsRejected()
    {
        var service = CreateService(new Dictionary<string, string>
        {
            ["https://example.com/sitemap.xml"] = "<sitemapindex><sitemap><loc>http://127.0.0.1/child.xml</loc></sitemap></sitemapindex>",
        });

        await Assert.ThrowsAsync<BlockedUrlException>(() =>
            service.CrawlAsync(Request("https://example.com/sitemap.xml"), CancellationToken.None));
    }

    private static SitemapCrawlRequest Request(string sitemapUrl, int maxUrls = 10000)
    {
        return new SitemapCrawlRequest
        {
            SitemapUrl = sitemapUrl,
            Headers = new Dictionary<string, string>(),
            TimeoutSeconds = 30,
            MaxUrls = maxUrls,
        };
    }

    private static SitemapService CreateService(
        Dictionary<string, string> responses,
        Dictionary<string, int>? counts = null)
    {
        var handler = new DelegateHandler(request =>
        {
            var url = request.RequestUri!.ToString();
            if (counts is not null)
            {
                counts[url] = counts.TryGetValue(url, out var value) ? value + 1 : 1;
            }

            if (!responses.TryGetValue(url, out var body))
            {
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));
            }

            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(body, Encoding.UTF8, "application/xml"),
            });
        });

        return new SitemapService(new FakeHttpClientFactory(handler), Options.Create(new HttpWorkerOptions
        {
            Http = new HttpOptions
            {
                MaxConcurrency = 50,
                MaxBodyBytes = 5242880,
                MaxRedirectHops = 3,
            },
        }));
    }
}
