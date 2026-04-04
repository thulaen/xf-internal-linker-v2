using System.Runtime.InteropServices;

namespace HttpWorker.Services.Native;

public static class ScoringInterop
{
    private const string SimSearchLib = "simsearch";
    private const string ScoringLib = "scoring";

    [DllImport(SimSearchLib, CallingConvention = CallingConvention.Cdecl)]
    public static extern unsafe void cscore_and_topk(
        float* destinationPtr, nuint destDim,
        float* sentencePtr, nuint numSentences, nuint sentenceDim,
        int* candidateRows, nuint candidateCount,
        int topK,
        long* outIndices, float* outScores, nuint* outCount
    );

    [DllImport(ScoringLib, CallingConvention = CallingConvention.Cdecl)]
    public static extern unsafe void cscore_full_batch(
        float* componentScores, nuint numRows, nuint numComponents,
        float* weights, nuint numWeights,
        float* siloScores, nuint numSilo,
        float* outScores
    );
}
