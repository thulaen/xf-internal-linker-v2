// fuzz_simsearch.cpp — libFuzzer harness for the cosine-similarity
// top-k function in simsearch.cpp.
//
// Strategy: interpret the input byte stream as a small fixed-shape
// configuration plus three float arrays — destination vector,
// sentence matrix, candidate index list. libFuzzer mutates the bytes;
// we feed them through cscore_and_topk() and let AddressSanitizer /
// UndefinedBehaviorSanitizer flag any out-of-bounds reads, signed
// overflows, etc.
//
// libFuzzer ABI: return 0 unless you want libFuzzer to treat the
// input as "rejected" (then return -1). We always return 0 — the
// sanitizers decide whether the input is interesting.

#include <cstddef>
#include <cstdint>
#include <vector>

// Forward declaration of the C-callable hot path from simsearch.cpp.
// We do NOT include the pybind11 helpers — only the raw kernel.
void cscore_and_topk(const float* destination_ptr, size_t dest_dim,
                     const float* sentence_ptr, size_t num_sentences,
                     size_t sentence_dim, const int32_t* candidate_rows,
                     size_t candidate_count, int top_k,
                     int64_t* out_indices, float* out_scores,
                     size_t* out_count);

namespace {
constexpr size_t kMaxDim = 16;
constexpr size_t kMaxRows = 32;
constexpr size_t kMaxCands = 32;
constexpr int kMaxTopK = 8;
}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    // Minimum bytes for a useful test: 4 (header) + small float buffer.
    if (size < 16) {
        return 0;
    }

    // Header layout (4 bytes):
    //   byte 0: dest_dim  (1..kMaxDim)
    //   byte 1: num_rows  (1..kMaxRows)
    //   byte 2: num_cands (0..kMaxCands)
    //   byte 3: top_k     (1..kMaxTopK)
    const size_t dest_dim   = 1 + (data[0] % kMaxDim);
    const size_t num_rows   = 1 + (data[1] % kMaxRows);
    const size_t num_cands  = data[2] % (kMaxCands + 1);
    const int top_k         = 1 + (data[3] % kMaxTopK);

    const uint8_t* payload = data + 4;
    size_t payload_size = size - 4;

    // Need enough payload for dest + (rows × dest_dim) floats + cands int32s.
    const size_t floats_needed = dest_dim + num_rows * dest_dim;
    const size_t bytes_needed = floats_needed * sizeof(float) + num_cands * sizeof(int32_t);
    if (payload_size < bytes_needed) {
        return 0;
    }

    // Lay out: destination | sentence matrix | candidate rows.
    std::vector<float> dest(payload, payload + dest_dim * sizeof(float));
    std::vector<float> sentence_buf(reinterpret_cast<const float*>(payload + dest_dim * sizeof(float)),
                                    reinterpret_cast<const float*>(payload + dest_dim * sizeof(float))
                                        + num_rows * dest_dim);
    const float* destv  = reinterpret_cast<const float*>(payload);
    const float* sents  = reinterpret_cast<const float*>(payload + dest_dim * sizeof(float));
    const int32_t* cands = reinterpret_cast<const int32_t*>(
        payload + dest_dim * sizeof(float) + num_rows * dest_dim * sizeof(float));

    std::vector<int64_t> out_indices(static_cast<size_t>(top_k));
    std::vector<float> out_scores(static_cast<size_t>(top_k));
    size_t out_count = 0;

    cscore_and_topk(destv, dest_dim, sents, num_rows, dest_dim, cands, num_cands,
                    top_k, out_indices.data(), out_scores.data(), &out_count);

    // Use out_count to prevent the compiler from optimising the call away.
    return out_count > 1024 ? 1 : 0;
}
