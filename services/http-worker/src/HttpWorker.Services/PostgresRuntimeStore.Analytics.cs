using HttpWorker.Core.Contracts.V1;
using Npgsql;

namespace HttpWorker.Services;

public sealed partial class PostgresRuntimeStore
{
    public async Task<List<GSCDailyMetrics>> GetPagePerformanceAsync(string pageUrl, DateTime startDate, DateTime endDate, CancellationToken cancellationToken)
    {
        var results = new List<GSCDailyMetrics>();
        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            """
            SELECT date, impressions, clicks
            FROM analytics_gscdailyperformance
            WHERE page_url = @url
              AND date >= @start
              AND date <= @end
            ORDER BY date
            """,
            connection);
        command.Parameters.AddWithValue("url", pageUrl);
        command.Parameters.AddWithValue("start", startDate);
        command.Parameters.AddWithValue("end", endDate);

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            results.Add(new GSCDailyMetrics
            {
                Date = reader.GetDateTime(0),
                Impressions = reader.GetInt32(1),
                Clicks = reader.GetInt32(2)
            });
        }
        return results;
    }

    public async Task<List<GSCDailyMetrics>> GetGlobalPerformanceAsync(DateTime startDate, DateTime endDate, string propertyUrl, CancellationToken cancellationToken)
    {
        var results = new List<GSCDailyMetrics>();
        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            """
            SELECT date, SUM(impressions) as impressions, SUM(clicks) as clicks
            FROM analytics_gscdailyperformance
            WHERE property_url = @prop
              AND date >= @start
              AND date <= @end
            GROUP BY date
            ORDER BY date
            """,
            connection);
        command.Parameters.AddWithValue("prop", propertyUrl);
        command.Parameters.AddWithValue("start", startDate.Date);
        command.Parameters.AddWithValue("end", endDate.Date);

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            results.Add(new GSCDailyMetrics
            {
                Date = reader.GetDateTime(0),
                Impressions = Convert.ToInt32(reader.GetValue(1)),
                Clicks = Convert.ToInt32(reader.GetValue(2))
            });
        }
        return results;
    }

    public async Task<IReadOnlyList<int>> PersistImportNodesAsync(IReadOnlyList<ImportContentMutation> mutations, CancellationToken cancellationToken)
    {
        if (mutations.Count == 0) return new List<int>();

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        // 1. Upsert ContentItem
        await using var batchContent = new NpgsqlBatch(connection, transaction);
        foreach (var m in mutations)
        {
            var cmd = new NpgsqlBatchCommand(
                """
                INSERT INTO content_contentitem (
                    content_id, content_type, scope_id, url, title, distilled_text, content_hash,
                    view_count, reply_count, download_count, post_date, last_post_date, xf_post_id,
                    is_deleted, created_at, updated_at
                ) VALUES (
                    @content_id, @content_type, @scope_id, @url, @title, @distilled_text, @content_hash,
                    @view_count, @reply_count, @download_count, @post_date, @last_post_date, @xf_post_id,
                    FALSE, NOW(), NOW()
                )
                ON CONFLICT (content_id, content_type)
                DO UPDATE SET
                    scope_id = EXCLUDED.scope_id,
                    url = EXCLUDED.url,
                    title = EXCLUDED.title,
                    distilled_text = EXCLUDED.distilled_text,
                    content_hash = CASE WHEN EXCLUDED.content_hash <> '' THEN EXCLUDED.content_hash ELSE content_contentitem.content_hash END,
                    view_count = EXCLUDED.view_count,
                    reply_count = EXCLUDED.reply_count,
                    download_count = EXCLUDED.download_count,
                    post_date = EXCLUDED.post_date,
                    last_post_date = EXCLUDED.last_post_date,
                    xf_post_id = EXCLUDED.xf_post_id,
                    is_deleted = FALSE,
                    updated_at = NOW()
                """);
            cmd.Parameters.AddWithValue("content_id", m.ContentId);
            cmd.Parameters.AddWithValue("content_type", m.ContentType);
            cmd.Parameters.AddWithValue("scope_id", m.ScopeId);
            cmd.Parameters.AddWithValue("url", m.Url);
            cmd.Parameters.AddWithValue("title", m.Title);
            cmd.Parameters.AddWithValue("distilled_text", m.DistilledText);
            cmd.Parameters.AddWithValue("content_hash", m.ContentHash);
            cmd.Parameters.AddWithValue("view_count", m.ViewCount);
            cmd.Parameters.AddWithValue("reply_count", m.ReplyCount);
            cmd.Parameters.AddWithValue("download_count", m.DownloadCount);
            cmd.Parameters.AddWithValue("post_date", m.PostDate.HasValue ? (object)m.PostDate.Value.UtcDateTime : DBNull.Value);
            cmd.Parameters.AddWithValue("last_post_date", m.LastPostDate.HasValue ? (object)m.LastPostDate.Value.UtcDateTime : DBNull.Value);
            cmd.Parameters.AddWithValue("xf_post_id", m.XfPostId.HasValue ? (object)m.XfPostId.Value : DBNull.Value);
            batchContent.BatchCommands.Add(cmd);
        }
        await batchContent.ExecuteNonQueryAsync(cancellationToken);

        // 2. Fetch the corresponding internal `id`s for ContentItem and Upsert Post
        var contentItemDbIds = new Dictionary<(int, string), int>(); // map (ContentId, ContentType) -> DB id
        await using (var fetchCmd = new NpgsqlCommand(
            "SELECT id, content_id, content_type FROM content_contentitem WHERE content_id = ANY(@ids) AND content_type = ANY(@types)", connection, transaction))
        {
            fetchCmd.Parameters.AddWithValue("ids", mutations.Select(x => x.ContentId).ToArray());
            fetchCmd.Parameters.AddWithValue("types", mutations.Select(x => x.ContentType).ToArray());
            await using var reader = await fetchCmd.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                contentItemDbIds[(reader.GetInt32(1), reader.GetString(2))] = reader.GetInt32(0);
            }
        }

        await using var batchPost = new NpgsqlBatch(connection, transaction);
        foreach (var m in mutations.Where(x => contentItemDbIds.ContainsKey((x.ContentId, x.ContentType))))
        {
            var dbId = contentItemDbIds[(m.ContentId, m.ContentType)];
            var cmd = new NpgsqlBatchCommand(
                """
                INSERT INTO content_post (
                    content_item_id, raw_bbcode, clean_text, char_count, word_count, xf_post_id, created_at, updated_at
                ) VALUES (
                    @content_item_id, @raw_bbcode, @clean_text, @char_count, @word_count, @xf_post_id, NOW(), NOW()
                )
                ON CONFLICT (content_item_id)
                DO UPDATE SET
                    raw_bbcode = EXCLUDED.raw_bbcode,
                    clean_text = EXCLUDED.clean_text,
                    char_count = EXCLUDED.char_count,
                    word_count = EXCLUDED.word_count,
                    xf_post_id = EXCLUDED.xf_post_id,
                    updated_at = NOW()
                """);
            cmd.Parameters.AddWithValue("content_item_id", dbId);
            cmd.Parameters.AddWithValue("raw_bbcode", m.RawBody);
            cmd.Parameters.AddWithValue("clean_text", m.CleanText);
            cmd.Parameters.AddWithValue("char_count", m.CleanText.Length);
            cmd.Parameters.AddWithValue("word_count", m.CleanText.Split(' ', StringSplitOptions.RemoveEmptyEntries).Length);
            cmd.Parameters.AddWithValue("xf_post_id", m.XfPostId.HasValue ? (object)m.XfPostId.Value : DBNull.Value);
            batchPost.BatchCommands.Add(cmd);
        }
        if (batchPost.BatchCommands.Count > 0)
        {
            await batchPost.ExecuteNonQueryAsync(cancellationToken);
        }

        // Fetch Post ids
        var postDbIds = new Dictionary<int, int>(); // map Content DB id -> Post DB id
        await using (var fetchCmd = new NpgsqlCommand(
            "SELECT id, content_item_id FROM content_post WHERE content_item_id = ANY(@ids)", connection, transaction))
        {
            fetchCmd.Parameters.AddWithValue("ids", contentItemDbIds.Values.ToArray());
            await using var reader = await fetchCmd.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                postDbIds[reader.GetInt32(1)] = reader.GetInt32(0);
            }
        }

        // 3. Sentences delete & recreate
        await using (var delCmd = new NpgsqlCommand(
            "DELETE FROM content_sentence WHERE content_item_id = ANY(@ids)", connection, transaction))
        {
            delCmd.Parameters.AddWithValue("ids", contentItemDbIds.Values.ToArray());
            await delCmd.ExecuteNonQueryAsync(cancellationToken);
        }

        await using var batchSentence = new NpgsqlBatch(connection, transaction);
        foreach (var m in mutations.Where(x => contentItemDbIds.ContainsKey((x.ContentId, x.ContentType))))
        {
            var dbId = contentItemDbIds[(m.ContentId, m.ContentType)];
            if (!postDbIds.TryGetValue(dbId, out var postId)) continue;

            foreach (var s in m.Sentences)
            {
                var cmd = new NpgsqlBatchCommand(
                    """
                    INSERT INTO content_sentence (
                        content_item_id, post_id, text, position, char_count, start_char, end_char, word_position, created_at, updated_at
                    ) VALUES (
                        @content_item_id, @post_id, @text, @position, @char_count, @start_char, @end_char, @word_position, NOW(), NOW()
                    )
                    """);
                cmd.Parameters.AddWithValue("content_item_id", dbId);
                cmd.Parameters.AddWithValue("post_id", postId);
                cmd.Parameters.AddWithValue("text", s.Text);
                cmd.Parameters.AddWithValue("position", s.Position);
                cmd.Parameters.AddWithValue("char_count", s.CharCount);
                cmd.Parameters.AddWithValue("start_char", s.StartChar);
                cmd.Parameters.AddWithValue("end_char", s.EndChar);
                cmd.Parameters.AddWithValue("word_position", s.WordPosition);
                batchSentence.BatchCommands.Add(cmd);
            }
        }

        if (batchSentence.BatchCommands.Count > 0)
        {
            await batchSentence.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);
        return contentItemDbIds.Values.ToList();
    }

    public async Task<List<(int ScopePk, int ExternalScopeId, string ScopeType)>> GetScopesAsync(IReadOnlyList<int> scopePks, CancellationToken cancellationToken)
    {
        var results = new List<(int, int, string)>();
        await using var connection = await OpenConnectionAsync(cancellationToken);

        // Empty list means "all active scopes" — used when the caller does not restrict by scope.
        NpgsqlCommand command;
        if (scopePks.Count == 0)
        {
            command = new NpgsqlCommand(
                "SELECT id, scope_id, scope_type FROM content_scopeitem", connection);
        }
        else
        {
            command = new NpgsqlCommand(
                "SELECT id, scope_id, scope_type FROM content_scopeitem WHERE id = ANY(@ids)", connection);
            command.Parameters.AddWithValue("ids", scopePks.ToArray());
        }

        await using (command)
        {
            await using var reader = await command.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                results.Add((reader.GetInt32(0), reader.GetInt32(1), reader.GetString(2)));
            }
        }
        return results;
    }
}
