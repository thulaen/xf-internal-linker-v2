namespace HttpWorker.Core.Contracts.V1;

public class ImportContentMutation
{
    public int SourceId { get; set; }
    public string Url { get; set; } = string.Empty;
    public string Title { get; set; } = string.Empty;
    public string RawBody { get; set; } = string.Empty;
    public string DistilledBody { get; set; } = string.Empty;
    public float[] Embedding { get; set; } = [];
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
