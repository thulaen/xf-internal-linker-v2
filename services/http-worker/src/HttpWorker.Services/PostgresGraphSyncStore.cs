using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Options;
using Npgsql;

namespace HttpWorker.Services;

public sealed class PostgresGraphSyncStore : IGraphSyncStore
{
    private readonly string _connectionString;

    public PostgresGraphSyncStore(IOptions<HttpWorkerOptions> options)
    {
        _connectionString = options.Value.Postgres.ConnectionString ?? string.Empty;
    }

    public async Task<IReadOnlyList<GraphSyncSourceContent>> LoadRefreshSourcesAsync(
        IReadOnlyList<int>? contentItemPks,
        CancellationToken cancellationToken)
    {
        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            contentItemPks is { Count: > 0 }
                ? """
                  SELECT ci.id, ci.content_id, ci.content_type, p.raw_bbcode
                  FROM content_contentitem ci
                  JOIN content_post p ON p.content_item_id = ci.id
                  WHERE ci.is_deleted = FALSE
                    AND p.raw_bbcode <> ''
                    AND ci.id = ANY(@content_item_pks)
                  ORDER BY ci.id
                  """
                : """
                  SELECT ci.id, ci.content_id, ci.content_type, p.raw_bbcode
                  FROM content_contentitem ci
                  JOIN content_post p ON p.content_item_id = ci.id
                  WHERE ci.is_deleted = FALSE
                    AND p.raw_bbcode <> ''
                  ORDER BY ci.id
                  """,
            connection);
        if (contentItemPks is { Count: > 0 })
        {
            command.Parameters.AddWithValue("content_item_pks", contentItemPks.ToArray());
        }

        var items = new List<GraphSyncSourceContent>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            items.Add(new GraphSyncSourceContent
            {
                ContentItemPk = reader.GetInt32(0),
                ContentId = reader.GetInt32(1),
                ContentType = reader.GetString(2),
                RawBbcode = reader.IsDBNull(3) ? string.Empty : reader.GetString(3),
            });
        }

        return items;
    }

    public async Task<Dictionary<(int ContentId, string ContentType), GraphSyncDestination>> LoadDestinationsAsync(
        IReadOnlyCollection<(int ContentId, string ContentType)> keys,
        CancellationToken cancellationToken)
    {
        var destinations = new Dictionary<(int ContentId, string ContentType), GraphSyncDestination>(StringTupleComparer.Instance);
        if (keys.Count == 0)
        {
            return destinations;
        }

        await using var connection = await OpenConnectionAsync(cancellationToken);
        foreach (var group in keys.GroupBy(static item => item.ContentType, StringComparer.Ordinal))
        {
            await using var command = new NpgsqlCommand(
                """
                SELECT id, content_id, content_type, url
                FROM content_contentitem
                WHERE content_type = @content_type
                  AND content_id = ANY(@content_ids)
                """,
                connection);
            command.Parameters.AddWithValue("content_type", group.Key);
            command.Parameters.AddWithValue("content_ids", group.Select(static item => item.ContentId).Distinct().ToArray());

            await using var reader = await command.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                var destination = new GraphSyncDestination
                {
                    ContentItemPk = reader.GetInt32(0),
                    ContentId = reader.GetInt32(1),
                    ContentType = reader.GetString(2),
                    Url = reader.IsDBNull(3) ? string.Empty : reader.GetString(3),
                };
                destinations[(destination.ContentId, destination.ContentType)] = destination;
            }
        }

        return destinations;
    }

    public async Task<Dictionary<string, GraphSyncDestination>> LoadDestinationsByUrlAsync(
        IReadOnlyCollection<string> normalizedUrls,
        CancellationToken cancellationToken)
    {
        var destinations = new Dictionary<string, GraphSyncDestination>(StringComparer.Ordinal);
        if (normalizedUrls.Count == 0)
        {
            return destinations;
        }

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            """
            SELECT id, content_id, content_type, url
            FROM content_contentitem
            WHERE url = ANY(@urls)
            """,
            connection);
        command.Parameters.AddWithValue("urls", normalizedUrls.ToArray());

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            var destination = new GraphSyncDestination
            {
                ContentItemPk = reader.GetInt32(0),
                ContentId = reader.GetInt32(1),
                ContentType = reader.GetString(2),
                Url = reader.IsDBNull(3) ? string.Empty : reader.GetString(3),
            };
            if (!string.IsNullOrEmpty(destination.Url))
            {
                destinations[destination.Url] = destination;
            }
        }

        return destinations;
    }

    public async Task<GraphSyncSourceState> LoadSourceStateAsync(
        int contentItemPk,
        CancellationToken cancellationToken)
    {
        await using var connection = await OpenConnectionAsync(cancellationToken);
        var state = new GraphSyncSourceState();

        await using (var existingCommand = new NpgsqlCommand(
            """
            SELECT el.id,
                   el.to_content_item_id,
                   destination.content_id,
                   destination.content_type,
                   el.anchor_text,
                   el.extraction_method,
                   el.link_ordinal,
                   el.source_internal_link_count,
                   el.context_class
            FROM graph_existinglink el
            JOIN content_contentitem destination ON destination.id = el.to_content_item_id
            WHERE el.from_content_item_id = @content_item_pk
            ORDER BY el.id
            """,
            connection))
        {
            existingCommand.Parameters.AddWithValue("content_item_pk", contentItemPk);
            await using var reader = await existingCommand.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                state.ExistingLinks.Add(new GraphSyncExistingLinkRow
                {
                    Id = reader.GetInt64(0),
                    ToContentItemPk = reader.GetInt32(1),
                    ToContentId = reader.GetInt32(2),
                    ToContentType = reader.GetString(3),
                    AnchorText = reader.IsDBNull(4) ? string.Empty : reader.GetString(4),
                    ExtractionMethod = reader.IsDBNull(5) ? string.Empty : reader.GetString(5),
                    LinkOrdinal = reader.IsDBNull(6) ? null : reader.GetInt32(6),
                    SourceInternalLinkCount = reader.IsDBNull(7) ? null : reader.GetInt32(7),
                    ContextClass = reader.IsDBNull(8) ? string.Empty : reader.GetString(8),
                });
            }
        }

        await using (var freshnessCommand = new NpgsqlCommand(
            """
            SELECT edge.id,
                   edge.to_content_item_id,
                   destination.content_id,
                   destination.content_type,
                   edge.first_seen_at,
                   edge.last_seen_at,
                   edge.last_disappeared_at,
                   edge.is_active
            FROM graph_linkfreshnessedge edge
            JOIN content_contentitem destination ON destination.id = edge.to_content_item_id
            WHERE edge.from_content_item_id = @content_item_pk
            ORDER BY edge.id
            """,
            connection))
        {
            freshnessCommand.Parameters.AddWithValue("content_item_pk", contentItemPk);
            await using var reader = await freshnessCommand.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                state.FreshnessEdges.Add(new GraphSyncFreshnessRow
                {
                    Id = reader.GetInt64(0),
                    ToContentItemPk = reader.GetInt32(1),
                    ToContentId = reader.GetInt32(2),
                    ToContentType = reader.GetString(3),
                    FirstSeenAt = new DateTimeOffset(DateTime.SpecifyKind(reader.GetDateTime(4), DateTimeKind.Utc)),
                    LastSeenAt = new DateTimeOffset(DateTime.SpecifyKind(reader.GetDateTime(5), DateTimeKind.Utc)),
                    LastDisappearedAt = reader.IsDBNull(6)
                        ? null
                        : new DateTimeOffset(DateTime.SpecifyKind(reader.GetDateTime(6), DateTimeKind.Utc)),
                    IsActive = reader.GetBoolean(7),
                });
            }
        }

        return state;
    }

    public async Task PersistAsync(
        GraphSyncPersistenceCommand command,
        CancellationToken cancellationToken)
    {
        if (command.NewLinks.Count == 0 &&
            command.UpdatedLinks.Count == 0 &&
            command.DeletedLinkIds.Count == 0 &&
            command.NewFreshnessEdges.Count == 0 &&
            command.UpdatedFreshnessEdges.Count == 0)
        {
            return;
        }

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        foreach (var row in command.NewLinks)
        {
            await using var insertCommand = new NpgsqlCommand(
                """
                INSERT INTO graph_existinglink (
                    from_content_item_id,
                    to_content_item_id,
                    anchor_text,
                    extraction_method,
                    link_ordinal,
                    source_internal_link_count,
                    context_class,
                    discovered_at
                )
                VALUES (
                    @from_content_item_id,
                    @to_content_item_id,
                    @anchor_text,
                    @extraction_method,
                    @link_ordinal,
                    @source_internal_link_count,
                    @context_class,
                    @discovered_at
                )
                """,
                connection,
                transaction);
            insertCommand.Parameters.AddWithValue("from_content_item_id", row.FromContentItemPk);
            insertCommand.Parameters.AddWithValue("to_content_item_id", row.ToContentItemPk);
            insertCommand.Parameters.AddWithValue("anchor_text", row.AnchorText);
            insertCommand.Parameters.AddWithValue("extraction_method", row.ExtractionMethod);
            insertCommand.Parameters.AddWithValue("link_ordinal", (object?)row.LinkOrdinal ?? DBNull.Value);
            insertCommand.Parameters.AddWithValue("source_internal_link_count", (object?)row.SourceInternalLinkCount ?? DBNull.Value);
            insertCommand.Parameters.AddWithValue("context_class", row.ContextClass);
            insertCommand.Parameters.AddWithValue("discovered_at", row.DiscoveredAt.UtcDateTime);
            await insertCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        foreach (var row in command.UpdatedLinks)
        {
            await using var updateCommand = new NpgsqlCommand(
                """
                UPDATE graph_existinglink
                SET anchor_text = @anchor_text,
                    extraction_method = @extraction_method,
                    link_ordinal = @link_ordinal,
                    source_internal_link_count = @source_internal_link_count,
                    context_class = @context_class
                WHERE id = @id
                """,
                connection,
                transaction);
            updateCommand.Parameters.AddWithValue("id", row.Id);
            updateCommand.Parameters.AddWithValue("anchor_text", row.AnchorText);
            updateCommand.Parameters.AddWithValue("extraction_method", row.ExtractionMethod);
            updateCommand.Parameters.AddWithValue("link_ordinal", (object?)row.LinkOrdinal ?? DBNull.Value);
            updateCommand.Parameters.AddWithValue("source_internal_link_count", (object?)row.SourceInternalLinkCount ?? DBNull.Value);
            updateCommand.Parameters.AddWithValue("context_class", row.ContextClass);
            await updateCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        if (command.DeletedLinkIds.Count > 0)
        {
            await using var deleteCommand = new NpgsqlCommand(
                "DELETE FROM graph_existinglink WHERE id = ANY(@ids)",
                connection,
                transaction);
            deleteCommand.Parameters.AddWithValue("ids", command.DeletedLinkIds.Distinct().ToArray());
            await deleteCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        foreach (var row in command.NewFreshnessEdges)
        {
            await using var insertCommand = new NpgsqlCommand(
                """
                INSERT INTO graph_linkfreshnessedge (
                    from_content_item_id,
                    to_content_item_id,
                    first_seen_at,
                    last_seen_at,
                    last_disappeared_at,
                    is_active
                )
                VALUES (
                    @from_content_item_id,
                    @to_content_item_id,
                    @first_seen_at,
                    @last_seen_at,
                    NULL,
                    @is_active
                )
                ON CONFLICT (from_content_item_id, to_content_item_id)
                DO UPDATE SET
                    first_seen_at = EXCLUDED.first_seen_at,
                    last_seen_at = EXCLUDED.last_seen_at,
                    last_disappeared_at = EXCLUDED.last_disappeared_at,
                    is_active = EXCLUDED.is_active
                """,
                connection,
                transaction);
            insertCommand.Parameters.AddWithValue("from_content_item_id", row.FromContentItemPk);
            insertCommand.Parameters.AddWithValue("to_content_item_id", row.ToContentItemPk);
            insertCommand.Parameters.AddWithValue("first_seen_at", row.FirstSeenAt.UtcDateTime);
            insertCommand.Parameters.AddWithValue("last_seen_at", row.LastSeenAt.UtcDateTime);
            insertCommand.Parameters.AddWithValue("is_active", row.IsActive);
            await insertCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        foreach (var row in command.UpdatedFreshnessEdges
            .GroupBy(static item => item.Id)
            .Select(static group => group.Last()))
        {
            await using var updateCommand = new NpgsqlCommand(
                """
                UPDATE graph_linkfreshnessedge
                SET first_seen_at = @first_seen_at,
                    last_seen_at = @last_seen_at,
                    last_disappeared_at = @last_disappeared_at,
                    is_active = @is_active
                WHERE id = @id
                """,
                connection,
                transaction);
            updateCommand.Parameters.AddWithValue("id", row.Id);
            updateCommand.Parameters.AddWithValue("first_seen_at", row.FirstSeenAt.UtcDateTime);
            updateCommand.Parameters.AddWithValue("last_seen_at", row.LastSeenAt.UtcDateTime);
            updateCommand.Parameters.AddWithValue("last_disappeared_at", row.LastDisappearedAt?.UtcDateTime ?? (object)DBNull.Value);
            updateCommand.Parameters.AddWithValue("is_active", row.IsActive);
            await updateCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);
    }

    private async Task<NpgsqlConnection> OpenConnectionAsync(CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(_connectionString))
        {
            throw new ValidationException("postgres connection string is required");
        }

        var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync(cancellationToken);
        return connection;
    }
}
