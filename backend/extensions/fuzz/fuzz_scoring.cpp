// fuzz_scoring.cpp — libFuzzer harness for the scoring kernels.
// Phase 4b starter target. Expansion via the AutoIssue coverage-gap
// ratchet (one new public-API fuzz target per PR).
//
// This is intentionally a minimal harness — it just exercises the
// libFuzzer plumbing and links scoring.cpp. Real per-function fuzz
// targets land as scoring.cpp grows public C-callable entry points.

#include <cstddef>
#include <cstdint>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    // Smallest possible smoke: just touch the bytes so the linker
    // proves scoring.cpp compiles under fuzz flags. Replace with real
    // scoring-kernel invocation when the next coverage-gap AutoIssue
    // points here.
    volatile uint32_t acc = 0;
    for (size_t i = 0; i < size; ++i) {
        acc = acc * 31u + static_cast<uint32_t>(data[i]);
    }
    return acc == 0xDEADBEEFu ? 1 : 0;
}
