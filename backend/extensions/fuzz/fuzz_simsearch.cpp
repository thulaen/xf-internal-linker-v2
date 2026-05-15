// libFuzzer harness for the cosine-similarity top-k kernel.

#include <cstddef>
#include <cstdint>
#include <vector>

#include "include/simsearch_core.h"

namespace {
constexpr size_t kMaxDim = 16;
constexpr size_t kMaxRows = 32;
constexpr size_t kMaxCands = 32;
constexpr int kMaxTopK = 8;
}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 16) {
    return 0;
  }

  const size_t dest_dim = 1 + (data[0] % kMaxDim);
  const size_t num_rows = 1 + (data[1] % kMaxRows);
  const size_t num_cands = data[2] % (kMaxCands + 1);
  const int top_k = 1 + (data[3] % kMaxTopK);

  const uint8_t* payload = data + 4;
  const size_t payload_size = size - 4;
  const size_t floats_needed = dest_dim + num_rows * dest_dim;
  const size_t bytes_needed =
      floats_needed * sizeof(float) + num_cands * sizeof(int32_t);
  if (payload_size < bytes_needed) {
    return 0;
  }

  const float* destv = reinterpret_cast<const float*>(payload);
  const float* sents =
      reinterpret_cast<const float*>(payload + dest_dim * sizeof(float));
  const int32_t* cands = reinterpret_cast<const int32_t*>(
      payload + dest_dim * sizeof(float) + num_rows * dest_dim * sizeof(float));

  std::vector<int64_t> out_indices(static_cast<size_t>(top_k));
  std::vector<float> out_scores(static_cast<size_t>(top_k));
  size_t out_count = 0;

  cscore_and_topk(destv, dest_dim, sents, num_rows, dest_dim, cands, num_cands,
                  top_k, out_indices.data(), out_scores.data(), &out_count);

  return out_count > 1024 ? 1 : 0;
}
