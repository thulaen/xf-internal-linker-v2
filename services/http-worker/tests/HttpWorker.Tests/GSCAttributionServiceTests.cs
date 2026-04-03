using HttpWorker.Core.Contracts.V1;
using HttpWorker.Core.Interfaces;
using HttpWorker.Services;
using Microsoft.Extensions.Logging.Abstractions;
using NSubstitute;
using Xunit;

namespace HttpWorker.Tests;

public sealed class GSCAttributionServiceTests
{
    private readonly IPostgresRuntimeStore _store = Substitute.For<IPostgresRuntimeStore>();
    private readonly GSCAttributionService _sut;

    public GSCAttributionServiceTests()
    {
        _sut = new GSCAttributionService(_store, NullLogger<GSCAttributionService>.Instance);
    }

    [Fact]
    public async Task AnalyzeUpliftAsync_PositiveUplift_ReturnsPositiveLabel()
    {
        // Arrange
        var payload = new GSCAttributionJobPayload
        {
            SuggestionId = Guid.NewGuid(),
            PageUrl = "https://example.com/target",
            PropertyUrl = "sc-domain:example.com",
            ApplyDate = new DateTimeOffset(2026, 4, 1, 0, 0, 0, TimeSpan.Zero),
            WindowDays = 7
        };

        // Page performance: 1% baseline -> 5% post
        _store.GetPagePerformanceAsync(Arg.Any<string>(), Arg.Any<DateTime>(), Arg.Any<DateTime>(), default)
            .Returns(new List<GSCDailyMetrics>
            {
                // Before
                new() { Date = new DateTime(2026, 3, 25), Impressions = 1000, Clicks = 10 },
                // After
                new() { Date = new DateTime(2026, 4, 2), Impressions = 1000, Clicks = 50 }
            });

        // Global performance: Stable at 1%
        _store.GetGlobalPerformanceAsync(Arg.Any<DateTime>(), Arg.Any<DateTime>(), Arg.Any<string>(), default)
            .Returns(new List<GSCDailyMetrics>
            {
                new() { Date = new DateTime(2026, 3, 25), Impressions = 100000, Clicks = 1000 },
                new() { Date = new DateTime(2026, 4, 2), Impressions = 100000, Clicks = 1000 }
            });

        // Act
        var result = await _sut.AnalyzeUpliftAsync(payload, default);

        // Assert
        Assert.Equal("positive", result.RewardLabel);
        Assert.True(result.ProbabilityOfUplift > 0.95);
    }

    [Fact]
    public async Task AnalyzeUpliftAsync_LowImpressions_ReturnsInconclusive()
    {
        // Arrange
        var payload = new GSCAttributionJobPayload { PageUrl = "x", WindowDays = 7, ApplyDate = DateTimeOffset.UtcNow };
        
        _store.GetPagePerformanceAsync(Arg.Any<string>(), Arg.Any<DateTime>(), Arg.Any<DateTime>(), default)
            .Returns(new List<GSCDailyMetrics>
            {
                new() { Impressions = 5, Clicks = 0 },
                new() { Impressions = 5, Clicks = 0 }
            });
            
        _store.GetGlobalPerformanceAsync(Arg.Any<DateTime>(), Arg.Any<DateTime>(), Arg.Any<string>(), default)
            .Returns(new List<GSCDailyMetrics> { new() { Impressions = 1000, Clicks = 10 } });

        // Act
        var result = await _sut.AnalyzeUpliftAsync(payload, default);

        // Assert
        Assert.Equal("inconclusive", result.RewardLabel);
    }
}
