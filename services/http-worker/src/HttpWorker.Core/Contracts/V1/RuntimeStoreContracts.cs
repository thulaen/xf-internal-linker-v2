namespace HttpWorker.Core.Contracts.V1;

public sealed class BrokenLinkScanWorkload
{
    public List<BrokenLinkUrlRequest> Items { get; set; } = [];

    public bool HitScanCap { get; set; }
}

public sealed class BrokenLinkExistingRecord
{
    public Guid BrokenLinkId { get; set; }

    public int SourceContentId { get; set; }

    public string Url { get; set; } = string.Empty;

    public string Status { get; set; } = string.Empty;

    public string Notes { get; set; } = string.Empty;
}

public sealed class BrokenLinkBatchMutation
{
    public bool Create { get; set; }

    public Guid BrokenLinkId { get; set; }

    public int SourceContentId { get; set; }

    public string Url { get; set; } = string.Empty;

    public int HttpStatus { get; set; }

    public string RedirectUrl { get; set; } = string.Empty;

    public string Status { get; set; } = string.Empty;

    public string Notes { get; set; } = string.Empty;

    public DateTimeOffset CheckedAt { get; set; }
}

public sealed class PeriodicTaskRecord
{
    public int Id { get; set; }

    public string Name { get; set; } = string.Empty;

    public string Task { get; set; } = string.Empty;

    public string KwargsJson { get; set; } = "{}";

    public string Minute { get; set; } = "*";

    public string Hour { get; set; } = "*";

    public string DayOfWeek { get; set; } = "*";

    public string DayOfMonth { get; set; } = "*";

    public string MonthOfYear { get; set; } = "*";

    public DateTimeOffset? LastRunAt { get; set; }

    public bool OneOff { get; set; }
}
