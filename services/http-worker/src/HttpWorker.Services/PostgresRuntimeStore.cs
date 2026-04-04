using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using Microsoft.Extensions.Options;
using Npgsql;

namespace HttpWorker.Services;

public sealed class PostgresRuntimeStore : IPostgresRuntimeStore
{
    private readonly string _connectionString;

    public PostgresRuntimeStore(IOptions<HttpWorkerOptions> options)
    {
        _connectionString = options.Value.Postgres.ConnectionString ?? string.Empty;
    }

    public async Task<bool> CanConnectAsync(CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(_connectionString))
        {
            return false;
        }

        try
        {
            await using var connection = await OpenConnectionAsync(cancellationToken);
            await using var command = new NpgsqlCommand("SELECT 1", connection);
            await command.ExecuteScalarAsync(cancellationToken);
            return true;
        }
        catch
        {
            return false;
        }
    }

    public async Task<BrokenLinkScanWorkload> LoadBrokenLinkScanWorkloadAsync(
        BrokenLinkScanRequest request,
        CancellationToken cancellationToken)
    {
        await using var connection = await OpenConnectionAsync(cancellationToken);
        var workload = new BrokenLinkScanWorkload();
        var seen = new HashSet<(int SourceContentId, string Url)>();

        await LoadExistingLinkUrlsAsync(connection, request, workload, seen, cancellationToken);
        if (!workload.HitScanCap)
        {
            await LoadPostUrlsAsync(connection, request, workload, seen, cancellationToken);
        }

        return workload;
    }

    public async Task<Dictionary<(int SourceContentId, string Url), BrokenLinkExistingRecord>> LoadExistingBrokenLinkRecordsAsync(
        IReadOnlyList<BrokenLinkUrlRequest> items,
        CancellationToken cancellationToken)
    {
        var records = new Dictionary<(int SourceContentId, string Url), BrokenLinkExistingRecord>();
        if (items.Count == 0)
        {
            return records;
        }

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            """
            SELECT broken_link_id, source_content_id, url, status, notes
            FROM graph_brokenlink
            WHERE source_content_id = ANY(@source_ids)
              AND url = ANY(@urls)
            """,
            connection);
        command.Parameters.AddWithValue("source_ids", items.Select(static item => item.SourceContentId).Distinct().ToArray());
        command.Parameters.AddWithValue("urls", items.Select(static item => item.Url).Distinct().ToArray());

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            var record = new BrokenLinkExistingRecord
            {
                BrokenLinkId = reader.GetGuid(0),
                SourceContentId = reader.GetInt32(1),
                Url = reader.GetString(2),
                Status = reader.GetString(3),
                Notes = reader.IsDBNull(4) ? string.Empty : reader.GetString(4),
            };
            records[(record.SourceContentId, record.Url)] = record;
        }

        return records;
    }

    public async Task PersistBrokenLinkBatchAsync(
        IReadOnlyList<BrokenLinkBatchMutation> mutations,
        CancellationToken cancellationToken)
    {
        if (mutations.Count == 0)
        {
            return;
        }

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        foreach (var mutation in mutations)
        {
            await using var command = new NpgsqlCommand(
                mutation.Create ? InsertBrokenLinkSql : UpdateBrokenLinkSql,
                connection,
                transaction);

            if (mutation.Create)
            {
                command.Parameters.AddWithValue("broken_link_id", mutation.BrokenLinkId);
                command.Parameters.AddWithValue("source_content_id", mutation.SourceContentId);
                command.Parameters.AddWithValue("url", mutation.Url);
                command.Parameters.AddWithValue("http_status", mutation.HttpStatus);
                command.Parameters.AddWithValue("redirect_url", mutation.RedirectUrl);
                command.Parameters.AddWithValue("first_detected_at", mutation.CheckedAt.UtcDateTime);
                command.Parameters.AddWithValue("last_checked_at", mutation.CheckedAt.UtcDateTime);
                command.Parameters.AddWithValue("status", mutation.Status);
                command.Parameters.AddWithValue("notes", mutation.Notes);
                command.Parameters.AddWithValue("created_at", mutation.CheckedAt.UtcDateTime);
                command.Parameters.AddWithValue("updated_at", mutation.CheckedAt.UtcDateTime);
            }
            else
            {
                command.Parameters.AddWithValue("broken_link_id", mutation.BrokenLinkId);
                command.Parameters.AddWithValue("http_status", mutation.HttpStatus);
                command.Parameters.AddWithValue("redirect_url", mutation.RedirectUrl);
                command.Parameters.AddWithValue("status", mutation.Status);
                command.Parameters.AddWithValue("last_checked_at", mutation.CheckedAt.UtcDateTime);
                command.Parameters.AddWithValue("updated_at", mutation.CheckedAt.UtcDateTime);
            }

            await command.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);
    }

    public async Task<int> GetEnabledPeriodicTaskCountAsync(CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(_connectionString))
        {
            return 0;
        }

        try
        {
            await using var connection = await OpenConnectionAsync(cancellationToken);
            await using var command = new NpgsqlCommand(
                "SELECT COUNT(*) FROM django_celery_beat_periodictask WHERE enabled = TRUE",
                connection);
            var result = await command.ExecuteScalarAsync(cancellationToken);
            return Convert.ToInt32(result);
        }
        catch
        {
            return 0;
        }
    }

    public async Task<IReadOnlyList<PeriodicTaskRecord>> LoadEnabledPeriodicTasksAsync(CancellationToken cancellationToken)
    {
        var tasks = new List<PeriodicTaskRecord>();
        if (string.IsNullOrWhiteSpace(_connectionString))
        {
            return tasks;
        }

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            """
            SELECT pt.id,
                   pt.name,
                   pt.task,
                   COALESCE(pt.kwargs, '{}'),
                   cs.minute,
                   cs.hour,
                   cs.day_of_week,
                   cs.day_of_month,
                   cs.month_of_year,
                   pt.last_run_at,
                   pt.one_off
            FROM django_celery_beat_periodictask pt
            JOIN django_celery_beat_crontabschedule cs ON cs.id = pt.crontab_id
            WHERE pt.enabled = TRUE
              AND pt.task <> ''
            ORDER BY pt.id
            """,
            connection);

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            tasks.Add(new PeriodicTaskRecord
            {
                Id = reader.GetInt32(0),
                Name = reader.GetString(1),
                Task = reader.GetString(2),
                KwargsJson = reader.GetString(3),
                Minute = reader.GetString(4),
                Hour = reader.GetString(5),
                DayOfWeek = reader.GetString(6),
                DayOfMonth = reader.GetString(7),
                MonthOfYear = reader.GetString(8),
                LastRunAt = reader.IsDBNull(9) ? null : new DateTimeOffset(DateTime.SpecifyKind(reader.GetDateTime(9), DateTimeKind.Utc)),
                OneOff = !reader.IsDBNull(10) && reader.GetBoolean(10),
            });
        }

        return tasks;
    }

    public async Task MarkPeriodicTaskTriggeredAsync(int periodicTaskId, DateTimeOffset triggeredAt, CancellationToken cancellationToken)
    {
        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            """
            UPDATE django_celery_beat_periodictask
            SET last_run_at = @last_run_at,
                total_run_count = total_run_count + 1,
                date_changed = @date_changed
            WHERE id = @id
            """,
            connection);
        command.Parameters.AddWithValue("id", periodicTaskId);
        command.Parameters.AddWithValue("last_run_at", triggeredAt.UtcDateTime);
        command.Parameters.AddWithValue("date_changed", triggeredAt.UtcDateTime);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

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

    private async Task LoadExistingLinkUrlsAsync(
        NpgsqlConnection connection,
        BrokenLinkScanRequest request,
        BrokenLinkScanWorkload workload,
        HashSet<(int SourceContentId, string Url)> seen,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            """
            SELECT el.from_content_item_id, destination.url
            FROM graph_existinglink el
            JOIN content_contentitem source ON source.id = el.from_content_item_id
            JOIN content_contentitem destination ON destination.id = el.to_content_item_id
            WHERE source.is_deleted = FALSE
              AND destination.url <> ''
            ORDER BY el.from_content_item_id, el.to_content_item_id
            """,
            connection);

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            var sourceContentId = reader.GetInt32(0);
            var url = reader.GetString(1);
            if (!TryAddItem(sourceContentId, url, request, workload, seen))
            {
                return;
            }
        }
    }

    private async Task LoadPostUrlsAsync(
        NpgsqlConnection connection,
        BrokenLinkScanRequest request,
        BrokenLinkScanWorkload workload,
        HashSet<(int SourceContentId, string Url)> seen,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            """
            SELECT p.content_item_id, p.raw_bbcode
            FROM content_post p
            JOIN content_contentitem ci ON ci.id = p.content_item_id
            WHERE ci.is_deleted = FALSE
              AND p.raw_bbcode <> ''
            ORDER BY p.content_item_id
            """,
            connection);

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            var sourceContentId = reader.GetInt32(0);
            var rawBbcode = reader.IsDBNull(1) ? string.Empty : reader.GetString(1);

            foreach (var url in BrokenLinkUrlExtractor.ExtractUrls(rawBbcode, request.AllowedDomains))
            {
                if (!TryAddItem(sourceContentId, url, request, workload, seen))
                {
                    return;
                }
            }
        }
    }

    private static bool TryAddItem(
        int sourceContentId,
        string url,
        BrokenLinkScanRequest request,
        BrokenLinkScanWorkload workload,
        HashSet<(int SourceContentId, string Url)> seen)
    {
        if (!seen.Add((sourceContentId, url)))
        {
            return true;
        }

        workload.Items.Add(new BrokenLinkUrlRequest
        {
            SourceContentId = sourceContentId,
            Url = url,
        });

        if (workload.Items.Count < request.ScanCap)
        {
            return true;
        }

        workload.HitScanCap = true;
        return false;
    }

    private async Task<NpgsqlConnection> OpenConnectionAsync(CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(_connectionString))
        {
            throw new Exception("postgres connection string is required");
        }

        var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync(cancellationToken);
        return connection;
    }

    private const string InsertBrokenLinkSql =
        """
        INSERT INTO graph_brokenlink (
            broken_link_id,
            source_content_id,
            url,
            http_status,
            redirect_url,
            first_detected_at,
            last_checked_at,
            status,
            notes,
            created_at,
            updated_at
        )
        VALUES (
            @broken_link_id,
            @source_content_id,
            @url,
            @http_status,
            @redirect_url,
            @first_detected_at,
            @last_checked_at,
            @status,
            @notes,
            @created_at,
            @updated_at
        )
        ON CONFLICT (source_content_id, url)
        DO UPDATE SET
            http_status = EXCLUDED.http_status,
            redirect_url = EXCLUDED.redirect_url,
            status = CASE
                WHEN graph_brokenlink.status = 'ignored' THEN 'ignored'
                ELSE EXCLUDED.status
            END,
            last_checked_at = EXCLUDED.last_checked_at,
            updated_at = EXCLUDED.updated_at
        """;

    private const string UpdateBrokenLinkSql =
        """
        UPDATE graph_brokenlink
        SET http_status = @http_status,
            redirect_url = @redirect_url,
            status = @status,
            last_checked_at = @last_checked_at,
            updated_at = @updated_at
        WHERE broken_link_id = @broken_link_id
        """;
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
        if (scopePks.Count == 0) return results;

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            "SELECT id, scope_id, scope_type FROM content_scopeitem WHERE id = ANY(@ids)", connection);
        command.Parameters.AddWithValue("ids", scopePks.ToArray());

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            results.Add((reader.GetInt32(0), reader.GetInt32(1), reader.GetString(2)));
        }
        return results;
    }

    public async Task<IReadOnlyList<HostNode>> GetHostNodesAsync(List<int> scopeIds, CancellationToken cancellationToken)
    {
        var nodes = new List<HostNode>();
        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            """
            SELECT s.id, s.content_item_id, s.text, s.embedding::text
            FROM content_sentence s
            JOIN content_contentitem ci ON ci.id = s.content_item_id
            WHERE ci.scope_id = ANY(@scopes)
              AND s.embedding IS NOT NULL
              AND ci.is_deleted = FALSE
            """, connection);
        command.Parameters.AddWithValue("scopes", scopeIds.ToArray());
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        
        while (await reader.ReadAsync(cancellationToken))
        {
            float[] embedArray = ParseVector(reader.IsDBNull(3) ? null : reader.GetString(3));
            nodes.Add(new HostNode
            {
                SentenceId = reader.GetInt32(0),
                ContentId = reader.GetInt32(1),
                SentenceText = reader.GetString(2),
                Embedding = embedArray
            });
        }
        return nodes;
    }

    public async Task<IReadOnlyList<DestinationNode>> GetDestinationNodesAsync(List<int> destScopeIds, CancellationToken cancellationToken)
    {
        var nodes = new List<DestinationNode>();
        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            """
            SELECT id, title, embedding::text, march_2026_pagerank_score
            FROM content_contentitem
            WHERE scope_id = ANY(@scopes)
              AND embedding IS NOT NULL
              AND is_deleted = FALSE
            """, connection);
        command.Parameters.AddWithValue("scopes", destScopeIds.ToArray());
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        
        while (await reader.ReadAsync(cancellationToken))
        {
            float[] embedArray = ParseVector(reader.IsDBNull(2) ? null : reader.GetString(2));
            nodes.Add(new DestinationNode
            {
                ContentId = reader.GetInt32(0),
                Title = reader.GetString(1),
                Embedding = embedArray,
                PageRank = reader.IsDBNull(3) ? 0f : (float)reader.GetDouble(3),
                NodeQuality = 1.0f // Node quality could be calculated or derived from DB
            });
        }
        return nodes;
    }

    private static float[] ParseVector(string? vectorStr)
    {
        if (string.IsNullOrWhiteSpace(vectorStr)) return [];
        // format: "[0.1,-0.2,...]"
        var cleanStr = vectorStr.Trim('[', ']');
        var parts = cleanStr.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        var res = new float[parts.Length];
        for (int i = 0; i < parts.Length; i++)
        {
            if (float.TryParse(parts[i], System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out float f))
                res[i] = f;
        }
        return res;
    }

    public async Task PersistPipelineSuggestionsAsync(string runId, IReadOnlyList<PipelineSuggestion> suggestions, CancellationToken cancellationToken)
    {
        if (suggestions.Count == 0) return;

        await using var connection = await OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        await using var batch = new NpgsqlBatch(connection, transaction);
        foreach (var sug in suggestions)
        {
            var cmd = new NpgsqlBatchCommand(
                """
                INSERT INTO suggestions_suggestion (
                    pipeline_run_id, host_item_id, host_sentence_id, destination_item_id,
                    anchor_text, composite_score, 
                    state, is_visible, status, created_at, updated_at
                ) VALUES (
                    @run_id, @host_id, @sentence_id, @dest_id, 
                    @anchor, @score,
                    'pending', TRUE, 'new', NOW(), NOW()
                )
                """);
            cmd.Parameters.AddWithValue("run_id", runId);
            cmd.Parameters.AddWithValue("host_id", sug.HostContentId);
            cmd.Parameters.AddWithValue("sentence_id", sug.HostSentenceId);
            cmd.Parameters.AddWithValue("dest_id", sug.DestinationContentId);
            cmd.Parameters.AddWithValue("anchor", sug.ExactMatchAnchor);
            cmd.Parameters.AddWithValue("score", (double)sug.CompositeScore); // Postgres float field mapped to composite score
            batch.BatchCommands.Add(cmd);
        }

        await batch.ExecuteNonQueryAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }
}
