using System.Text.Json.Serialization;

namespace HttpWorker.Core.Contracts.V1;

public sealed class GraphSyncContentRequest
{
    [JsonPropertyName("content_item_pk")]
    public int ContentItemPk { get; set; }

    [JsonPropertyName("content_id")]
    public int ContentId { get; set; }

    [JsonPropertyName("content_type")]
    public string ContentType { get; set; } = string.Empty;

    [JsonPropertyName("raw_bbcode")]
    public string RawBbcode { get; set; } = string.Empty;

    [JsonPropertyName("forum_domains")]
    public List<string> ForumDomains { get; set; } = [];

    [JsonPropertyName("allow_disappearance")]
    public bool AllowDisappearance { get; set; } = true;

    [JsonPropertyName("tracked_at")]
    public DateTimeOffset? TrackedAt { get; set; }
}

public sealed class GraphSyncRefreshRequest
{
    [JsonPropertyName("content_item_pks")]
    public List<int>? ContentItemPks { get; set; }

    [JsonPropertyName("forum_domains")]
    public List<string> ForumDomains { get; set; } = [];

    [JsonPropertyName("tracked_at")]
    public DateTimeOffset? TrackedAt { get; set; }
}

public sealed class GraphSyncResponse
{
    [JsonPropertyName("refreshed_items")]
    public int RefreshedItems { get; set; }

    [JsonPropertyName("active_links")]
    public int ActiveLinks { get; set; }

    [JsonPropertyName("created_links")]
    public int CreatedLinks { get; set; }

    [JsonPropertyName("updated_links")]
    public int UpdatedLinks { get; set; }

    [JsonPropertyName("deleted_links")]
    public int DeletedLinks { get; set; }

    [JsonPropertyName("created_freshness_edges")]
    public int CreatedFreshnessEdges { get; set; }

    [JsonPropertyName("updated_freshness_edges")]
    public int UpdatedFreshnessEdges { get; set; }

    [JsonPropertyName("created_entities")]
    public int CreatedEntities { get; set; }

    [JsonPropertyName("created_entity_edges")]
    public int CreatedEntityEdges { get; set; }
}

public sealed class GraphSyncSourceContent
{
    public int ContentItemPk { get; set; }

    public int ContentId { get; set; }

    public string ContentType { get; set; } = string.Empty;

    public string RawBbcode { get; set; } = string.Empty;
}

public sealed class GraphSyncDestination
{
    public int ContentItemPk { get; set; }

    public int ContentId { get; set; }

    public string ContentType { get; set; } = string.Empty;

    public string Url { get; set; } = string.Empty;
}

public sealed class GraphSyncExistingLinkRow
{
    public long Id { get; set; }

    public int ToContentItemPk { get; set; }

    public int ToContentId { get; set; }

    public string ToContentType { get; set; } = string.Empty;

    public string AnchorText { get; set; } = string.Empty;

    public string ExtractionMethod { get; set; } = string.Empty;

    public int? LinkOrdinal { get; set; }

    public int? SourceInternalLinkCount { get; set; }

    public string ContextClass { get; set; } = string.Empty;
}

public sealed class GraphSyncFreshnessRow
{
    public long Id { get; set; }

    public int ToContentItemPk { get; set; }

    public int ToContentId { get; set; }

    public string ToContentType { get; set; } = string.Empty;

    public DateTimeOffset FirstSeenAt { get; set; }

    public DateTimeOffset LastSeenAt { get; set; }

    public DateTimeOffset? LastDisappearedAt { get; set; }

    public bool IsActive { get; set; }
}

public sealed class GraphSyncSourceState
{
    public List<GraphSyncExistingLinkRow> ExistingLinks { get; } = [];

    public List<GraphSyncFreshnessRow> FreshnessEdges { get; } = [];
}

public sealed class GraphSyncExistingLinkInsert
{
    public int FromContentItemPk { get; set; }

    public int ToContentItemPk { get; set; }

    public string AnchorText { get; set; } = string.Empty;

    public string ExtractionMethod { get; set; } = string.Empty;

    public int? LinkOrdinal { get; set; }

    public int? SourceInternalLinkCount { get; set; }

    public string ContextClass { get; set; } = string.Empty;

    public DateTimeOffset DiscoveredAt { get; set; }
}

public sealed class GraphSyncExistingLinkUpdate
{
    public long Id { get; set; }

    public string AnchorText { get; set; } = string.Empty;

    public string ExtractionMethod { get; set; } = string.Empty;

    public int? LinkOrdinal { get; set; }

    public int? SourceInternalLinkCount { get; set; }

    public string ContextClass { get; set; } = string.Empty;
}

public sealed class GraphSyncFreshnessInsert
{
    public int FromContentItemPk { get; set; }

    public int ToContentItemPk { get; set; }

    public DateTimeOffset FirstSeenAt { get; set; }

    public DateTimeOffset LastSeenAt { get; set; }

    public bool IsActive { get; set; }
}

public sealed class GraphSyncFreshnessUpdate
{
    public long Id { get; set; }

    public DateTimeOffset FirstSeenAt { get; set; }

    public DateTimeOffset LastSeenAt { get; set; }

    public DateTimeOffset? LastDisappearedAt { get; set; }

    public bool IsActive { get; set; }
}

public sealed class GraphSyncPersistenceCommand
{
    public List<GraphSyncExistingLinkInsert> NewLinks { get; } = [];

    public List<GraphSyncExistingLinkUpdate> UpdatedLinks { get; } = [];

    public List<long> DeletedLinkIds { get; } = [];

    public List<GraphSyncFreshnessInsert> NewFreshnessEdges { get; } = [];

    public List<GraphSyncFreshnessUpdate> UpdatedFreshnessEdges { get; } = [];

    public List<GraphSyncEntityNode> KnowledgeGraphEntities { get; } = [];

    public string? KnowledgeGraphExtractionVersion { get; set; }

    public int FromContentItemPk { get; set; }

    public int ActiveLinks { get; set; }
}

public sealed class GraphSyncEntityNode
{
    public string SurfaceForm { get; set; } = string.Empty;

    public string CanonicalForm { get; set; } = string.Empty;

    public string EntityType { get; set; } = "keyword";

    public double Weight { get; set; }
}
