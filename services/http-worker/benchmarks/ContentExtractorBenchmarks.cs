using BenchmarkDotNet.Attributes;
using HttpWorker.Services;
using Microsoft.Extensions.Logging.Abstractions;

namespace HttpWorker.Benchmarks;

[MemoryDiagnoser]
public class ContentExtractorBenchmarks
{
    private ContentExtractor _extractor = null!;
    private string _smallHtml = null!;
    private string _mediumHtml = null!;
    private string _largeHtml = null!;

    [GlobalSetup]
    public void Setup()
    {
        _extractor = new ContentExtractor(NullLogger<ContentExtractor>.Instance);

        _smallHtml = GenerateHtml(10);
        _mediumHtml = GenerateHtml(100);
        _largeHtml = GenerateHtml(500);
    }

    private static string GenerateHtml(int paragraphs)
    {
        var sb = new System.Text.StringBuilder();
        sb.Append("<!DOCTYPE html><html><head><title>Test Page</title>");
        sb.Append("<meta name=\"description\" content=\"A test page for benchmarking\">");
        sb.Append("</head><body>");
        sb.Append("<nav><a href=\"/\">Home</a><a href=\"/about\">About</a></nav>");
        sb.Append("<main><article>");
        for (var i = 0; i < paragraphs; i++)
        {
            sb.Append($"<p>Paragraph {i} with <a href=\"/page{i}\">internal link {i}</a> ");
            sb.Append($"and some <strong>formatted</strong> content about topic {i}. ");
            sb.Append("This is filler text to make the paragraph realistic in length.</p>");
        }
        sb.Append("</article></main>");
        sb.Append("<footer><a href=\"/privacy\">Privacy</a></footer>");
        sb.Append("</body></html>");
        return sb.ToString();
    }

    [Benchmark]
    public async Task<int> ExtractSmall()
    {
        var result = await _extractor.ExtractAsync(
            _smallHtml, "https://example.com/test", "https://example.com/test",
            200, 100, "text/html", null, null, [], "example.com", 0, CancellationToken.None);
        return result.WordCount;
    }

    [Benchmark]
    public async Task<int> ExtractMedium()
    {
        var result = await _extractor.ExtractAsync(
            _mediumHtml, "https://example.com/test", "https://example.com/test",
            200, 100, "text/html", null, null, [], "example.com", 0, CancellationToken.None);
        return result.WordCount;
    }

    [Benchmark]
    public async Task<int> ExtractLarge()
    {
        var result = await _extractor.ExtractAsync(
            _largeHtml, "https://example.com/test", "https://example.com/test",
            200, 100, "text/html", null, null, [], "example.com", 0, CancellationToken.None);
        return result.WordCount;
    }
}
