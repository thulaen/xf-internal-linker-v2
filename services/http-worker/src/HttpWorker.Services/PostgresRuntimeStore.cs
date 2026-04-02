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
            throw new ValidationException("postgres connection string is required");
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
}
