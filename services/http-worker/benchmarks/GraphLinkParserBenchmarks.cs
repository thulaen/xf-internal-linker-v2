using BenchmarkDotNet.Attributes;
using HttpWorker.Services;

namespace HttpWorker.Benchmarks;

[MemoryDiagnoser]
public class GraphLinkParserBenchmarks
{
    private string _bbcode = null!;
    private readonly string[] _forumDomains = ["example.com", "forum.example.com"];

    [Params(1_000, 10_000, 100_000)]
    public int InputSize { get; set; }

    [GlobalSetup]
    public void Setup()
    {
        var sb = new System.Text.StringBuilder(InputSize);
        var i = 0;
        while (sb.Length < InputSize)
        {
            var kind = i % 3;
            if (kind == 0)
                sb.Append($"[url=https://example.com/page{i}]Link {i}[/url] ");
            else if (kind == 1)
                sb.Append($"<a href=\"https://example.com/html{i}\">Anchor {i}</a> ");
            else
                sb.Append($"https://example.com/bare{i} ");
            sb.Append("filler text and content padding here. ");
            i++;
        }
        _bbcode = sb.ToString();
    }

    [Benchmark]
    public int FindPendingLinks()
    {
        var result = GraphLinkParser.FindPendingLinks(
            _bbcode, 1, "https://example.com", _forumDomains);
        return result.Count;
    }
}
