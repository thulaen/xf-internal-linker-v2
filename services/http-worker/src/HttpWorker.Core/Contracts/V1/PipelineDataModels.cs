namespace HttpWorker.Core.Contracts.V1;

public class ImportContentMutation
{
    public int ScopeId { get; set; }
    public int ContentId { get; set; }
    public string ContentType { get; set; } = string.Empty;
    public string Url { get; set; } = string.Empty;
    public string Title { get; set; } = string.Empty;
    public string RawBody { get; set; } = string.Empty;
    public string CleanText { get; set; } = string.Empty;
    public string DistilledText { get; set; } = string.Empty;
    public string ContentHash { get; set; } = string.Empty;
    public int ViewCount { get; set; }
    public int ReplyCount { get; set; }
    public int DownloadCount { get; set; }
    public DateTimeOffset? PostDate { get; set; }
    public DateTimeOffset? LastPostDate { get; set; }
    public int? XfPostId { get; set; }
    public float[] Embedding { get; set; } = [];
    public List<SentenceMutation> Sentences { get; set; } = new();
}

public class SentenceMutation
{
    public string Text { get; set; } = string.Empty;
    public int Position { get; set; }
    public int CharCount { get; set; }
    public int StartChar { get; set; }
    public int EndChar { get; set; }
    public int WordPosition { get; set; }
}

