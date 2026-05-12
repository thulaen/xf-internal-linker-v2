// fuzz_passagesim.cpp — libFuzzer harness for the passage-similarity
// `maxsim` kernel. Phase 4b starter target.
//
// Real implementation pending — for now this is a smoke harness that
// proves passagesim.cpp links under fuzzer + ASan + UBSan flags. A
// future PR fills LLVMFuzzerTestOneInput with a real call to maxsim
// over fuzz-mutated query/matrix arrays.

#include <cstddef>
#include <cstdint>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    volatile uint32_t hash = 0xCAFEBABEu;
    for (size_t i = 0; i < size; ++i) {
        hash ^= (hash << 5) + (hash >> 2) + data[i];
    }
    return hash == 0u ? 1 : 0;
}
