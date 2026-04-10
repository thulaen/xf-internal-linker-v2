using BenchmarkDotNet.Attributes;
using HttpWorker.Core.Text;

namespace HttpWorker.Benchmarks;

[MemoryDiagnoser]
public class UrlNormalizerBenchmarks
{
    private string[] _urls = null!;

    [Params(100, 1_000, 10_000)]
    public int Count { get; set; }

    [GlobalSetup]
    public void Setup()
    {
        _urls = new string[Count];
        for (var i = 0; i < Count; i++)
        {
            var kind = i % 3;
            if (kind == 0)
                _urls[i] = $"https://Example.COM/forum/threads/topic-{i}/#post-{i * 10}";
            else if (kind == 1)
                _urls[i] = $"HTTP://example.com:80/resources/article-{i}/";
            else
                _urls[i] = $"https://example.com/pages/page-{i}?ref=sidebar&utm_source=test";
        }
    }

    [Benchmark]
    public int NormalizeAll()
    {
        var total = 0;
        foreach (var url in _urls)
        {
            total += UrlNormalizer.NormalizeInternalUrl(url).Length;
        }
        return total;
    }
}
