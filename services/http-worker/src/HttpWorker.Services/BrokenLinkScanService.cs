using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;

namespace HttpWorker.Services;

public sealed class BrokenLinkScanService(
    IBrokenLinkService brokenLinkService,
    IPostgresRuntimeStore postgresRuntimeStore,
    IProgressStreamService progressStreamService)
    : IBrokenLinkScanService
{
    public async Task<BrokenLinkScanResponse> ExecuteAsync(
        string jobId,
        BrokenLinkScanRequest request,
        CancellationToken cancellationToken)
    {
        ValidateRequest(request);

        await progressStreamService.PublishAsync(
            jobId,
            BuildProgressEvent(jobId, "running", 0.0, "Collecting URLs for broken-link scan..."),
            cancellationToken);

        var workload = await postgresRuntimeStore.LoadBrokenLinkScanWorkloadAsync(request, cancellationToken);
        var totalUrls = workload.Items.Count;
        if (totalUrls == 0)
        {
            var emptyResponse = new BrokenLinkScanResponse
            {
                ScannedUrls = 0,
                FlaggedUrls = 0,
                FixedUrls = 0,
                HitScanCap = false,
            };
            await progressStreamService.PublishAsync(
                jobId,
                BuildProgressEvent(jobId, "completed", 1.0, "No URLs found to scan.", scannedUrls: 0, totalUrls: 0),
                cancellationToken);
            return emptyResponse;
        }

        await progressStreamService.PublishAsync(
            jobId,
            BuildProgressEvent(
                jobId,
                "running",
                0.02,
                $"Scanning {totalUrls} URL(s) for link health...",
                totalUrls: totalUrls,
                hitScanCap: workload.HitScanCap),
            cancellationToken);

        var existingRecords = await postgresRuntimeStore.LoadExistingBrokenLinkRecordsAsync(workload.Items, cancellationToken);
        var flaggedUrls = 0;
        var fixedUrls = 0;
        var scannedUrls = 0;
        var effectiveBatchSize = Math.Clamp(request.BatchSize, 1, 1000);

        foreach (var batch in workload.Items.Chunk(effectiveBatchSize))
        {
            var checkResponse = await brokenLinkService.CheckAsync(
                new BrokenLinkCheckRequest
                {
                    Urls = batch.ToList(),
                    UserAgent = request.UserAgent,
                    TimeoutSeconds = request.TimeoutSeconds,
                    MaxConcurrency = request.MaxConcurrency,
                },
                cancellationToken);

            var mutations = new List<BrokenLinkBatchMutation>(checkResponse.Checked.Count);
            foreach (var item in checkResponse.Checked)
            {
                scannedUrls++;
                var key = (item.SourceContentId, item.Url);
                var issueDetected = item.HttpStatus == 0 ||
                    item.HttpStatus >= 400 ||
                    !string.IsNullOrEmpty(item.RedirectUrl);

                if (issueDetected)
                {
                    if (!existingRecords.TryGetValue(key, out var existingRecord))
                    {
                        existingRecord = new BrokenLinkExistingRecord
                        {
                            BrokenLinkId = Guid.NewGuid(),
                            SourceContentId = item.SourceContentId,
                            Url = item.Url,
                            Status = "open",
                            Notes = string.Empty,
                        };
                        existingRecords[key] = existingRecord;
                        mutations.Add(BuildCreateMutation(existingRecord, item));
                    }
                    else
                    {
                        var nextStatus = string.Equals(existingRecord.Status, "ignored", StringComparison.OrdinalIgnoreCase)
                            ? "ignored"
                            : "open";
                        existingRecord.Status = nextStatus;
                        mutations.Add(BuildUpdateMutation(existingRecord, item, nextStatus));
                    }

                    flaggedUrls++;
                }
                else if (existingRecords.TryGetValue(key, out var cleanRecord))
                {
                    cleanRecord.Status = "fixed";
                    mutations.Add(BuildUpdateMutation(cleanRecord, item, "fixed"));
                    fixedUrls++;
                }

                if (scannedUrls % 25 == 0 || scannedUrls == totalUrls)
                {
                    await progressStreamService.PublishAsync(
                        jobId,
                        BuildProgressEvent(
                            jobId,
                            "running",
                            (double)scannedUrls / totalUrls,
                            $"Checked {scannedUrls}/{totalUrls}: {StatusLabel(item.HttpStatus)}",
                            scannedUrls: scannedUrls,
                            totalUrls: totalUrls,
                            flaggedUrls: flaggedUrls,
                            fixedUrls: fixedUrls,
                            currentUrl: item.Url,
                            hitScanCap: workload.HitScanCap),
                        cancellationToken);
                }
            }

            await postgresRuntimeStore.PersistBrokenLinkBatchAsync(mutations, cancellationToken);
        }

        var response = new BrokenLinkScanResponse
        {
            ScannedUrls = scannedUrls,
            FlaggedUrls = flaggedUrls,
            FixedUrls = fixedUrls,
            HitScanCap = workload.HitScanCap,
            ProbeBackend = "csharp_http_worker",
        };
        var completionMessage =
            $"Broken link scan complete. {flaggedUrls} issue(s) flagged, {fixedUrls} previously flagged link(s) resolved." +
            (workload.HitScanCap ? " Scan stopped at the 10,000 URL safety cap." : string.Empty);

        await progressStreamService.PublishAsync(
            jobId,
            BuildProgressEvent(
                jobId,
                "completed",
                1.0,
                completionMessage,
                scannedUrls: scannedUrls,
                totalUrls: totalUrls,
                flaggedUrls: flaggedUrls,
                fixedUrls: fixedUrls,
                hitScanCap: workload.HitScanCap),
            cancellationToken);

        return response;
    }

    private static BrokenLinkBatchMutation BuildCreateMutation(
        BrokenLinkExistingRecord record,
        BrokenLinkCheckItem item)
    {
        return new BrokenLinkBatchMutation
        {
            Create = true,
            BrokenLinkId = record.BrokenLinkId,
            SourceContentId = item.SourceContentId,
            Url = item.Url,
            HttpStatus = item.HttpStatus,
            RedirectUrl = item.RedirectUrl,
            Status = record.Status,
            Notes = record.Notes,
            CheckedAt = item.CheckedAt,
        };
    }

    private static BrokenLinkBatchMutation BuildUpdateMutation(
        BrokenLinkExistingRecord record,
        BrokenLinkCheckItem item,
        string status)
    {
        return new BrokenLinkBatchMutation
        {
            Create = false,
            BrokenLinkId = record.BrokenLinkId,
            SourceContentId = item.SourceContentId,
            Url = item.Url,
            HttpStatus = item.HttpStatus,
            RedirectUrl = item.RedirectUrl,
            Status = status,
            Notes = record.Notes,
            CheckedAt = item.CheckedAt,
        };
    }

    private static object BuildProgressEvent(
        string jobId,
        string state,
        double progress,
        string message,
        int? scannedUrls = null,
        int? totalUrls = null,
        int? flaggedUrls = null,
        int? fixedUrls = null,
        string? currentUrl = null,
        bool? hitScanCap = null)
    {
        return new
        {
            type = "job.progress",
            job_id = jobId,
            state,
            progress,
            message,
            scanned_urls = scannedUrls,
            total_urls = totalUrls,
            flagged_urls = flaggedUrls,
            fixed_urls = fixedUrls,
            current_url = currentUrl,
            hit_scan_cap = hitScanCap,
            probe_backend = "csharp_http_worker",
        };
    }

    private static string StatusLabel(int httpStatus)
    {
        return httpStatus == 0 ? "connection error" : httpStatus.ToString();
    }

    private static void ValidateRequest(BrokenLinkScanRequest request)
    {
        if (request.ScanCap < 1 || request.ScanCap > 10000)
        {
            throw new ValidationException("scan_cap must be between 1 and 10000");
        }

        if (request.BatchSize < 1 || request.BatchSize > 1000)
        {
            throw new ValidationException("batch_size must be between 1 and 1000");
        }

        if (request.TimeoutSeconds < 1 || request.TimeoutSeconds > 60)
        {
            throw new ValidationException("timeout_seconds must be between 1 and 60");
        }

        if (request.MaxConcurrency < 1 || request.MaxConcurrency > 200)
        {
            throw new ValidationException("max_concurrency must be between 1 and 200");
        }
    }
}
