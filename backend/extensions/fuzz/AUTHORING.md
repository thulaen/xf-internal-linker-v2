# Authoring a libFuzzer target

This dir holds the libFuzzer harnesses for the C++ hot-path modules. Phase 4b of the test-hardening plan ships three starter targets (`fuzz_simsearch`, `fuzz_scoring`, `fuzz_passagesim`); every additional public C++ entry point should grow a fuzz target via the AutoIssue ratchet (one new target per PR).

## What is libFuzzer?

libFuzzer is part of LLVM/Clang. It takes a function called `LLVMFuzzerTestOneInput(const uint8_t*, size_t)` and calls it thousands of times per second, each time with a random byte array — guided by code-coverage feedback so it learns which mutations explore new code paths. Paired with AddressSanitizer (`-fsanitize=fuzzer,address`), it surfaces crashes, leaks, use-after-free, out-of-bounds reads, and undefined-behaviour bugs that hand-written unit tests would never reach.

## Anatomy of a fuzz target

```cpp
#include <cstddef>
#include <cstdint>
#include <vector>

// Forward-declare the C-callable kernel. Do NOT include pybind11 here.
void my_hot_path(const float* in, size_t n, float* out);

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    // 1. Reject inputs that are too small to even shape.
    if (size < 8) return 0;

    // 2. Carve out a small header from the bytes (controls shape).
    const size_t n = 1 + (data[0] % 32);
    if (size < 1 + n * sizeof(float)) return 0;

    // 3. Interpret the rest as your typed input.
    const float* in = reinterpret_cast<const float*>(data + 1);

    // 4. Call the function under test. Sanitizers catch any UB.
    std::vector<float> out(n);
    my_hot_path(in, n, out.data());

    // 5. Use the result to prevent dead-code elimination.
    return out[0] > 1e6f ? 1 : 0;
}
```

## How to add a new fuzz target

1. Pick a public C-callable function in `backend/extensions/<module>.cpp`. If it's only reachable via pybind11, add an `extern "C"` forwarder that takes raw pointers.
2. Create `fuzz_<name>.cpp` in this dir. Use the anatomy above as a template.
3. Optionally drop one or two seed inputs into `corpus/<name>/` to give libFuzzer a head start (binary files; any size).
4. Register the target in `backend/extensions/fuzz/CMakeLists.txt`:
   ```cmake
   add_fuzz(<name>  "${EXT_ROOT}/<module>.cpp")
   ```
5. Add a 60-second run to `.github/workflows/ci.yml` under the `cpp-libfuzzer-smoke` job:
   ```yaml
   - name: fuzz_<name> (60s)
     working-directory: backend/extensions/fuzz
     run: ./build_fuzz/fuzz_<name> -max_total_time=60 corpus/<name>/
   ```

## Locally

```bash
cd backend/extensions/fuzz
cmake -B build_fuzz -S . -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
cmake --build build_fuzz --parallel 2
./build_fuzz/fuzz_simsearch -max_total_time=60 corpus/simsearch/
```

A crash drops a `crash-<sha1>` file into the working dir. Re-run with the crash file as an argument to deterministically reproduce: `./build_fuzz/fuzz_simsearch crash-deadbeef`. Commit reproducer files into `corpus/<name>/` so the crash becomes a regression check.

## Plain-English summary

Fuzz testing throws random byte streams at your C++ functions, millions of times. The compiler instrumentation watches for any time the program reads memory it shouldn't, divides by zero, or just crashes. Every new public function that takes a buffer should get a fuzz target so we find these bugs in CI instead of in production.

## Why we keep starting targets small

The first three targets (`fuzz_simsearch`, `fuzz_scoring`, `fuzz_passagesim`) intentionally do little real work — they only prove the libFuzzer plumbing compiles and links. Real fuzz logic lands per-PR as new public APIs are added or existing ones are touched. The AutoIssue picker (`fuzz_picker.py`, Phase 6) emits a `kind=fuzz-coverage-gap` row for every public function in `backend/extensions/` without a corresponding fuzz target so the gap is visible.
