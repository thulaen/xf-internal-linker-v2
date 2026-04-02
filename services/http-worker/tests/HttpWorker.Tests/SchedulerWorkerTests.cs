using HttpWorker.Core.Contracts.V1;
using HttpWorker.Worker;
using Xunit;

namespace HttpWorker.Tests;

public sealed class SchedulerWorkerTests
{
    [Fact]
    public void IsDue_ReturnsTrue_WhenCronMatchesAndTaskHasNotRunThisMinute()
    {
        var now = new DateTimeOffset(2026, 4, 2, 2, 0, 10, TimeSpan.Zero);
        var task = new PeriodicTaskRecord
        {
            Id = 1,
            Name = "nightly-xenforo-sync",
            Task = "pipeline.import_content",
            Minute = "0",
            Hour = "2",
            DayOfWeek = "*",
            DayOfMonth = "*",
            MonthOfYear = "*",
            LastRunAt = now.AddMinutes(-1),
        };

        Assert.True(SchedulerWorker.IsDue(task, now));
    }

    [Fact]
    public void IsDue_ReturnsFalse_WhenTaskAlreadyRanThisMinute()
    {
        var now = new DateTimeOffset(2026, 4, 2, 2, 0, 25, TimeSpan.Zero);
        var task = new PeriodicTaskRecord
        {
            Id = 1,
            Name = "nightly-xenforo-sync",
            Task = "pipeline.import_content",
            Minute = "0",
            Hour = "2",
            DayOfWeek = "*",
            DayOfMonth = "*",
            MonthOfYear = "*",
            LastRunAt = new DateTimeOffset(2026, 4, 2, 2, 0, 1, TimeSpan.Zero),
        };

        Assert.False(SchedulerWorker.IsDue(task, now));
    }

    [Fact]
    public void IsDue_MatchesFirstSundayWindowUsedByMonthlyTune()
    {
        var now = new DateTimeOffset(2026, 6, 7, 2, 0, 0, TimeSpan.Zero);
        var task = new PeriodicTaskRecord
        {
            Id = 2,
            Name = "monthly-r-auto-tune",
            Task = "pipeline.monthly_r_auto_tune",
            Minute = "0",
            Hour = "2",
            DayOfWeek = "0",
            DayOfMonth = "1-7",
            MonthOfYear = "*",
            LastRunAt = now.AddMonths(-1),
        };

        Assert.True(SchedulerWorker.IsDue(task, now));
    }
}
