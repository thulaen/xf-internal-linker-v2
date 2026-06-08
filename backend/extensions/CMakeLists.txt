cmake_minimum_required(VERSION 3.20)
project(xf_extensions_tests C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
include(FetchContent)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG        v1.14.0
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)
find_package(TBB QUIET)
if (TBB_FOUND)
    add_compile_definitions(HAS_TBB)
endif()
execute_process(
    COMMAND python -c "import pybind11; print(pybind11.get_include())"
    OUTPUT_VARIABLE PYBIND11_INCLUDE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
include_directories(${PYBIND11_INCLUDE_DIR})

execute_process(
    COMMAND python -c "import sys; from sysconfig import get_paths; print(get_paths()['include'])"
    OUTPUT_VARIABLE PYTHON_INCLUDE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
include_directories(${PYTHON_INCLUDE_DIR})

execute_process(
    COMMAND python -c "import sys; import os; print(os.path.join(sys.prefix, 'libs'))"
    OUTPUT_VARIABLE PYTHON_LIBS_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
link_directories(${PYTHON_LIBS_DIR})

add_compile_definitions(XF_BENCH_MODE)
add_compile_options(-O1)

# Coverage plumbing for FR-251 Gap #3.
# Enable with `-DCOVERAGE=ON`. This adds GCC/Clang coverage flags so an
# lcov pass after `ctest` produces a per-file branch and line report. The
# default OFF preset keeps the normal unit-test build fast. CI's
# `cpp-coverage` job sets COVERAGE=ON.
option(COVERAGE "Build with --coverage flags for lcov output" OFF)
if (COVERAGE)
    message(STATUS "Coverage build enabled; adding --coverage to CXX/LD flags")
    add_compile_options(--coverage -O0 -g)
    add_link_options(--coverage)
endif()

# Mull mutation-testing build (FR-251 Gap #4 — and resolution of the
# pre-2026-05-15 `mull-runner reports "No mutants found"` tooling gap).
# Enable with `-DMULL_BUILD=ON`. Adds the Mull IR pass plugin to every
# compile so mull-runner-19 can find mutation points in the resulting
# binary. Combined with -O0 to keep optimisations from elidng the
# instrumented branches.
option(MULL_BUILD "Build with Mull IR pass for mutation testing" OFF)
if (MULL_BUILD)
    message(STATUS "Mull build enabled; adding mull-ir-frontend pass + -O0 -g")
    add_compile_options(
        -fpass-plugin=/usr/lib/mull-ir-frontend-19
        -O0
        -g
    )
endif()
# NOTE: `simsearch` was ported from C++ to Rust (rust/extensions/simsearch) per
# RUST-FIRST.md dead-code-on-replace. Its GoogleTest cases now live in the Rust
# cargo-test suite (rust/extensions/simsearch/src/lib.rs), so the C++ test
# executable and its translation unit were removed.
# NOTE: `scoring` was ported from C++ to Rust (rust/extensions/scoring) per
# RUST-FIRST.md dead-code-on-replace. Its GoogleTest cases now live in the Rust
# cargo-test suite (rust/extensions/scoring/src/lib.rs), so the C++ test
# executable and its translation unit were removed.
# NOTE: `passagesim` was ported from C++ to Rust (rust/extensions/passagesim)
# per RUST-FIRST.md dead-code-on-replace. Its GoogleTest cases now live in the
# Rust cargo-test suite (rust/extensions/passagesim/src/lib.rs), so the C++ test
# executable and its translation unit were removed.
add_executable(test_fieldrel tests/test_fieldrel.cpp fieldrel.cpp)
target_include_directories(test_fieldrel PRIVATE include)
target_link_libraries(test_fieldrel GTest::gtest_main)
# NOTE: `quantemb` was ported from C++ to Rust (rust/extensions/quantemb) per
# RUST-FIRST.md dead-code-on-replace. Its GoogleTest cases now live in the Rust
# cargo-test suite (rust/extensions/quantemb/src/lib.rs), so the C++ test
# executable and its translation unit were removed.
# NOTE: `ivf_index` was ported from C++ to Rust (rust/extensions/ivf_index) per
# RUST-FIRST.md dead-code-on-replace. Its GoogleTest unit test, C++ source,
# header, fuzz harness, and benchmark were removed; the equivalent coverage now
# lives in the rust/extensions/ivf_index cargo-test suite.
# NOTE: test_streaming_sketches was deleted per RUST-FIRST.md
# dead-code-on-replace. Its three kernels (count_min_sketch, counting_bloom,
# compressed_bloom) were ported from C++ to Rust; the GoogleTest cases now live
# in the Rust cargo-test suites under rust/extensions/<kernel>/src/lib.rs plus
# backend/apps/pipeline/tests_<kernel>_rust_parity.py, so the C++ test
# translation unit no longer exercises any kernel and was removed.

# NOTE: `papertrail_dedup` was ported from C++ to Rust
# (rust/extensions/papertrail_dedup) per RUST-FIRST.md dead-code-on-replace. Its
# GoogleTest cases now live in the Rust cargo-test suite
# (rust/extensions/papertrail_dedup/src/lib.rs), so the C++ test executable and
# its translation unit were removed.

# NOTE: `lesson_index` was ported from C++ to Rust (rust/extensions/lesson_index)
# per RUST-FIRST.md dead-code-on-replace. Its GoogleTest cases now live in the
# Rust cargo-test suite (rust/extensions/lesson_index/src/lib.rs), so the C++
# test executable and its translation unit were removed.

enable_testing()
set(XF_GTEST_TARGETS
    # NOTE: test_passagesim removed — passagesim ported to Rust
    # (rust/extensions/passagesim) per RUST-FIRST.md dead-code-on-replace.
    test_fieldrel
    # NOTE: test_quantemb removed — quantemb ported to Rust
    # (rust/extensions/quantemb) per RUST-FIRST.md dead-code-on-replace.
    # NOTE: test_ivf_index removed — ivf_index ported to Rust
    # (rust/extensions/ivf_index) per RUST-FIRST.md dead-code-on-replace.
)
foreach(test_target IN LISTS XF_GTEST_TARGETS)
    add_test(NAME ${test_target} COMMAND $<TARGET_FILE:${test_target}>)
    set_tests_properties(
        ${test_target}
        PROPERTIES ENVIRONMENT "GTEST_SHUFFLE=1;GTEST_RANDOM_SEED=0"
    )
endforeach()
