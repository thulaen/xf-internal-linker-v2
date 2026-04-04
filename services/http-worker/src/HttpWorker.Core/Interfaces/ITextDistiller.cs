namespace HttpWorker.Core.Interfaces;

public interface ITextDistiller
{
    Task<string> DistillBodyAsync(IReadOnlyList<string> sentences, int maxSentences = 5, CancellationToken cancellationToken = default);
    bool IsFallbackActive { get; }
}
