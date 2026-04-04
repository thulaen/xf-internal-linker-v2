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

public class HostNode
{
    public int ContentId { get; set; }
    public int SentenceId { get; set; }
    public string SentenceText { get; set; } = string.Empty;
    public float[] Embedding { get; set; } = [];
}

public class DestinationNode
{
    public int ContentId { get; set; }
    public string Title { get; set; } = string.Empty;
    public float[] Embedding { get; set; } = [];
    public float PageRank { get; set; }
    public float NodeQuality { get; set; }
}

public class PipelineSuggestion
{
    public int HostContentId { get; set; }
    public int HostSentenceId { get; set; }
    public int DestinationContentId { get; set; }
    public string ExactMatchAnchor { get; set; } = string.Empty;
    public float CompositeScore { get; set; }
}
