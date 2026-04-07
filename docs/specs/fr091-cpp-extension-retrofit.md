# FR-091 - C++ Extension Retrofit

## Confirmation

- **Backlog confirmed**: `FR-091 - C++ Extension Retrofit` is a pending operational hardening task.
- **Repo confirmed**: `backend/extensions/CPP-RULES.md` defines the mandatory compliance standard for all C++ extensions. The 12 existing extensions predate this document and do not satisfy all requirements.
- **Repo confirmed**: The 12 existing extensions are: `scoring.cpp`, `simsearch.cpp`, `feedrerank.cpp`, `pagerank.cpp`, `l2norm.cpp`, `texttok.cpp`, `fieldrel.cpp`, `topicvec.cpp`, `anchorsim.cpp`, `graphwalk.cpp`, `sentenceseg.cpp`, `bm25.cpp`. All are compiled via `backend/extensions/setup.py`.

## Engineering Rationale

FR-091 is not derived from a patent or academic paper. It is an internal code-quality enforcement task.

The `CPP-RULES.md` standard was written after the first 12 extensions shipped. Those extensions work correctly but lack the safety guardrails the standard now requires: strict compiler warnings, NaN/Inf input validation, flush-to-zero mode for denormal performance, and double-precision accumulators for long reductions.

Bringing the existing 12 extensions into compliance prevents a two-tier codebase where new extensions follow the rules and old ones silently do not.

## Plain-English Summary

Simple version first.

The project has 12 C++ extensions that speed up the ranking pipeline. A rules document (`CPP-RULES.md`) was written later to make sure all C++ code is safe, warns on suspicious code, rejects NaN/Inf inputs, avoids slow denormal arithmetic, and uses double-precision math where rounding errors could accumulate.

The 12 existing extensions were written before these rules existed. FR-091 retrofits them so every extension meets the same standard.

Think of it like a building code update: the existing buildings still stand, but they need to be inspected and upgraded to the new code.

## Problem Statement

Today the 12 existing C++ extensions compile with minimal warnings (`-O2` only, no `-Wall -Werror`), accept NaN/Inf values silently (producing garbage output instead of an error), do not set flush-to-zero mode (risking 100x slowdowns on denormal values), and use `float` accumulators in reduction loops (losing precision on long vectors).

New extensions written under `CPP-RULES.md` will have all four protections. Without FR-091, the existing 12 extensions are the weakest link in the chain.

## Goals

FR-091 should:

- add strict compiler flags (`-Wall -Werror -Wconversion` etc.) to all 12 existing extensions via `setup.py`;
- add NaN/Inf input validation to every hot-path function that accepts float/double arrays;
- add flush-to-zero and denormals-are-zero initialization to extensions that perform floating-point arithmetic in tight loops;
- replace `float` accumulators with `double` accumulators in reduction loops (specifically `l2norm.cpp`);
- confirm output parity with pre-retrofit behavior within `1e-4` tolerance;
- confirm no more than 5% performance regression via `bench_extensions.py`.

## Non-Goals

FR-091 does not:

- change any algorithm logic, ranking formula, or signal computation;
- add new C++ extensions;
- change the pybind11 API surface of any extension;
- modify Python-side code that calls the extensions;
- affect any database model, migration, or API endpoint;
- change the Docker build process (extensions are compiled inside the existing build step).

## Math-Fidelity Note

### Fix 1 -- Compiler flags (setup.py, all 12 extensions)

```
Unix:  -std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror
       -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion
       -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough
Win:   /std:c++17 /O2 /arch:AVX2 /W4 /WX /sdl
```

These flags turn all warnings into errors, catch implicit type conversions, shadowed variables, null dereferences, and implicit fallthrough in switch statements.

### Fix 2 -- NaN/Inf input validation (scoring.cpp, simsearch.cpp, feedrerank.cpp)

```cpp
// At entry of every hot-path function that accepts float/double arrays:
for (size_t i = 0; i < n; ++i) {
    if (!std::isfinite(arr[i])) {
        throw std::invalid_argument("NaN or Inf in input at index " + std::to_string(i));
    }
}
// Cost: O(n) scan, ~0.5 ns/element on modern CPU. For n=50000: ~25 us overhead.
```

### Fix 3 -- Flush-to-zero / denormals-are-zero (scoring.cpp, simsearch.cpp, feedrerank.cpp, pagerank.cpp)

```cpp
#include <xmmintrin.h>  // _MM_SET_FLUSH_ZERO_MODE
#include <pmmintrin.h>  // _MM_SET_DENORMALS_ZERO_MODE

// In PYBIND11_MODULE() init:
_MM_SET_FLUSH_ZERO_MODE(_MM_FLUSH_ZERO_ON);
_MM_SET_DENORMALS_ZERO_MODE(_MM_DENORMALS_ZERO_ON);
// Effect: denormals (numbers < 1.17e-38) are treated as zero.
// Prevents 100x slowdown on denormal arithmetic in Intel/AMD CPUs.
```

### Fix 4 -- Double accumulator in l2norm.cpp

```cpp
// Before (precision loss on long vectors):
float sum_sq = 0.0f;
for (size_t i = 0; i < n; ++i) sum_sq += ptr[i] * ptr[i];

// After (correct):
double sum_sq = 0.0;
for (size_t i = 0; i < n; ++i) {
    sum_sq += static_cast<double>(ptr[i]) * static_cast<double>(ptr[i]);
}
float norm = static_cast<float>(std::sqrt(sum_sq));
// Worst-case precision delta for d=1024: ~1e-7 (negligible for ranking).
```

### Performance budget

| Fix | Overhead per call | Acceptable? |
|---|---|---|
| Compiler flags | 0 (may improve via `-O3 -march=native`) | Yes |
| NaN/Inf scan | ~25 us for n=50,000 | Yes (<0.1% of total pipeline) |
| Flush-to-zero | 0 (one-time module init) | Yes |
| Double accumulator | ~5% slower on l2norm hot path | Yes (within 5% budget) |

## Scope Boundary

FR-091 must stay separate from:

- **All ranking signals (FR-006 through FR-090)**: FR-091 does not change any signal's output value. The `1e-4` parity test confirms this.
- **New C++ extensions (OPT-01 through OPT-72, META-01 through META-39)**: Those are written under `CPP-RULES.md` from the start. FR-091 only retrofits the pre-existing 12.
- **Python fallback paths**: FR-091 does not create, modify, or remove any Python fallback. The `USE_NATIVE_EXTENSIONS` guard pattern is unchanged.

Hard rule: FR-091 must not change any extension's pybind11 function signature, argument count, argument types, or return type.

## Inputs Required

FR-091 uses only data already available in the build system:

- `backend/extensions/setup.py` -- the single build file that compiles all 12 extensions
- The 12 `.cpp` source files in `backend/extensions/`
- `backend/extensions/CPP-RULES.md` -- the compliance checklist

Explicitly disallowed inputs:

- No runtime data, no database queries, no API calls
- No changes to any Python file outside `setup.py`

## Settings And Feature-Flag Plan

FR-091 does not add any operator-facing settings. The compiler flags and code changes are unconditional.

The existing `USE_NATIVE_EXTENSIONS` setting in `settings/base.py` is unchanged. It continues to control whether extensions are loaded at all.

No new feature flag is needed because the retrofit is a code-quality fix, not a behavioral change.

## Diagnostics And Explainability Plan

### Verification suite

Two existing test files must pass after the retrofit:

- `test_parity_simple.py` -- compares pre-retrofit and post-retrofit output for every extension function on a fixed test corpus. Pass threshold: all outputs within `1e-4` absolute difference.
- `bench_extensions.py` -- measures wall-clock time for every extension function on a fixed workload. Pass threshold: no function regresses by more than 5%.

### CI gate

The retrofit PR must include a CI step that:

1. builds extensions with old flags (baseline);
2. builds extensions with new flags (retrofit);
3. runs `test_parity_simple.py` comparing outputs;
4. runs `bench_extensions.py` comparing timings;
5. fails if any parity delta exceeds `1e-4` or any timing regression exceeds 5%.

## Storage / Model / API Impact

### Suggestion model

No changes.

### Content model

No changes.

### Backend API

No changes.

### Frontend

No changes.

### Database / migrations

No changes.

### Docker

No changes. Extensions are compiled inside the existing `pip install -e backend/extensions/` step during image build. The new flags are picked up automatically by `setup.py`.

## Affected Files

- `backend/extensions/setup.py` -- add strict compiler flags for Unix and Windows
- `backend/extensions/scoring.cpp` -- add NaN/Inf validation, flush-to-zero init
- `backend/extensions/simsearch.cpp` -- add NaN/Inf validation, flush-to-zero init
- `backend/extensions/feedrerank.cpp` -- add NaN/Inf validation, flush-to-zero init
- `backend/extensions/pagerank.cpp` -- add flush-to-zero init
- `backend/extensions/l2norm.cpp` -- replace float accumulator with double accumulator

Files that must stay untouched:

- All Python files except `setup.py`
- All database models and migrations
- All frontend files
- `CPP-RULES.md` itself (source of truth, not a modification target)

## Test Plan

### 1. Compiler flag acceptance

- All 12 extensions compile cleanly with `-Wall -Werror -Wconversion -Wsign-conversion` (Unix) or `/W4 /WX` (Windows).
- Zero compiler warnings.

### 2. NaN/Inf rejection

- Passing a numpy array containing `float('nan')` to `scoring.score_batch()` raises `ValueError`.
- Passing a numpy array containing `float('inf')` to `simsearch.batch_cosine()` raises `ValueError`.
- Passing clean float32 arrays works identically to pre-retrofit.

### 3. Output parity

- `test_parity_simple.py` passes with all outputs within `1e-4` of baseline.
- The double accumulator in `l2norm.cpp` may improve precision (smaller delta vs. ground truth), never worsen it.

### 4. Performance budget

- `bench_extensions.py` shows no function regresses by more than 5%.

### 5. Flush-to-zero behavior

- Passing an array of denormal values (e.g., `1e-40`) to `scoring.score_batch()` does not cause a 100x slowdown compared to normal values.

## Risk List

- `-Wconversion` may flag legitimate casts in existing code that need explicit `static_cast<>` fixes -- these are safe to add but increase the diff size;
- `-Werror` turns any new compiler warning in a future toolchain update into a build failure -- mitigated by pinning the compiler version in the Docker image;
- the double accumulator in `l2norm.cpp` changes output values by up to `1e-7` -- the `1e-4` parity threshold absorbs this, and the change improves accuracy;
- flush-to-zero mode is process-global on x86 -- it affects all floating-point operations in the same process, including Python/numpy. In practice this is harmless because denormals are never meaningful in ranking math.
