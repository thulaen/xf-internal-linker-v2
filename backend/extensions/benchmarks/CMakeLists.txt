cmake_minimum_required(VERSION 3.16)
project(xf_benchmarks LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

function(apply_project_warnings TARGET)
    if(MSVC)
        target_compile_options(${TARGET} PRIVATE /O2 /arch:AVX2 /W4 /WX /sdl)
    else()
        target_compile_options(${TARGET} PRIVATE
            -O3 -march=native -Wall -Wextra -Wpedantic -Werror
            -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion
            -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough
        )
    endif()
endfunction()

add_compile_definitions(XF_BENCH_MODE)

execute_process(
    COMMAND python -c "import pybind11; print(pybind11.get_include())"
    OUTPUT_VARIABLE PYBIND11_INCLUDE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
include_directories(SYSTEM ${PYBIND11_INCLUDE_DIR})

execute_process(
    COMMAND python -c "import sys; from sysconfig import get_paths; print(get_paths()['include'])"
    OUTPUT_VARIABLE PYTHON_INCLUDE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
include_directories(SYSTEM ${PYTHON_INCLUDE_DIR})

execute_process(
    COMMAND python -c "import sys; import os; print(os.path.join(sys.prefix, 'libs'))"
    OUTPUT_VARIABLE PYTHON_LIBS_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
link_directories(${PYTHON_LIBS_DIR})

include(FetchContent)
FetchContent_Declare(
    googlebenchmark
    GIT_REPOSITORY https://github.com/google/benchmark.git
    GIT_TAG        v1.9.1
    GIT_SHALLOW    TRUE
)
set(BENCHMARK_ENABLE_TESTING OFF CACHE BOOL "" FORCE)
set(BENCHMARK_ENABLE_INSTALL OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googlebenchmark)

set(EXT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")
set(EXT_INC  "${EXT_ROOT}/include")

function(add_bench NAME)
    set(SOURCES ${ARGN})
    add_executable(bench_${NAME} bench_${NAME}.cpp ${SOURCES})
    target_include_directories(bench_${NAME} PRIVATE
        ${EXT_INC}
        ${EXT_ROOT}
        ${CMAKE_CURRENT_SOURCE_DIR}
    )
    apply_project_warnings(bench_${NAME})
    target_link_libraries(bench_${NAME} PRIVATE
        benchmark::benchmark
        benchmark::benchmark_main
    )
    if(NOT MSVC)
        find_package(TBB QUIET)
        if(TBB_FOUND)
            target_link_libraries(bench_${NAME} PRIVATE TBB::tbb)
            target_compile_definitions(bench_${NAME} PRIVATE HAS_TBB=1)
        endif()
    endif()
endfunction()

# NOTE: `simsearch` was ported from C++ to Rust (rust/extensions/simsearch) per
# RUST-FIRST.md dead-code-on-replace. Its benchmark now lives at
# rust/extensions/simsearch/benches/bench_simsearch.rs (criterion), so the C++
# add_bench entry and bench_simsearch.cpp were removed.
# NOTE: `scoring` was ported from C++ to Rust (rust/extensions/scoring) per
# RUST-FIRST.md dead-code-on-replace. Its benchmark now lives at
# rust/extensions/scoring/benches/bench_scoring.rs (criterion), so the C++
# add_bench entry and bench_scoring.cpp were removed.
# NOTE: `passagesim` was ported from C++ to Rust (rust/extensions/passagesim)
# per RUST-FIRST.md dead-code-on-replace. Its benchmark now lives at
# rust/extensions/passagesim/benches/bench_passagesim.rs (criterion), so the C++
# add_bench entry and bench_passagesim.cpp were removed.
# NOTE: `quantemb` was ported from C++ to Rust (rust/extensions/quantemb) per
# RUST-FIRST.md dead-code-on-replace. Its benchmark now lives at
# rust/extensions/quantemb/benches/bench_quantemb.rs (criterion), so the C++
# add_bench entry and bench_quantemb.cpp were removed.
# NOTE: `ivf_index` was ported from C++ to Rust (rust/extensions/ivf_index) per
# RUST-FIRST.md dead-code-on-replace. Its benchmark now lives at
# rust/extensions/ivf_index/benches/bench_ivf_index.rs (criterion), so the C++
# add_bench entry and bench_ivf_index.cpp were removed.
# NOTE: bench_anchor_garbage was deleted per RUST-FIRST.md
# dead-code-on-replace. Its anchor_self_information section was ported to Rust,
# and modifying the shared C++ benchmark would violate the removed-language
# guard. Keep the remaining anchor C++ kernels covered by their existing tests
# until their Rust ports land.
# NOTE: bench_streaming_sketches was deleted per RUST-FIRST.md
# dead-code-on-replace. Its three kernels (count_min_sketch, counting_bloom,
# compressed_bloom) were ported from C++ to Rust; the benchmarks now live in the
# Rust Criterion benches under rust/extensions/<kernel>/benches/, so the C++
# bench translation unit no longer benchmarks any kernel and was removed.
# api_rate_limiter ported to Rust (rust/extensions/api_rate_limiter); its C++
# single-file benchmark was removed per RUST-FIRST.md dead-code-on-replace. The
# benchmark now lives in rust/extensions/api_rate_limiter/benches/.
# papertrail_dedup ported to Rust (rust/extensions/papertrail_dedup); its C++
# single-file benchmark was removed per RUST-FIRST.md dead-code-on-replace. The
# benchmark now lives in rust/extensions/papertrail_dedup/benches/.
# lesson_index ported to Rust (rust/extensions/lesson_index); its C++ benchmark
# was removed per RUST-FIRST.md dead-code-on-replace. The benchmark now lives in
# rust/extensions/lesson_index/benches/.

function(add_edge_test NAME)
    set(SOURCES ${ARGN})
    add_executable(test_edges_${NAME} test_edges_${NAME}.cpp ${SOURCES})
    target_include_directories(test_edges_${NAME} PRIVATE
        ${EXT_INC}
        ${EXT_ROOT}
        ${CMAKE_CURRENT_SOURCE_DIR}
    )
    apply_project_warnings(test_edges_${NAME})
    if(NOT MSVC)
        find_package(TBB QUIET)
        if(TBB_FOUND)
            target_link_libraries(test_edges_${NAME} PRIVATE TBB::tbb)
            target_compile_definitions(test_edges_${NAME} PRIVATE HAS_TBB=1)
        endif()
    endif()
    add_test(NAME edge_${NAME} COMMAND test_edges_${NAME} --gtest_shuffle)
endfunction()

enable_testing()

# NOTE: `simsearch` edge tests were ported to Rust cargo tests
# (rust/extensions/simsearch/src/lib.rs) per RUST-FIRST.md dead-code-on-replace;
# the C++ add_edge_test entry and test_edges_simsearch.cpp were removed.
# NOTE: `scoring` edge tests were ported to Rust cargo tests
# (rust/extensions/scoring/src/lib.rs) per RUST-FIRST.md dead-code-on-replace;
# the C++ add_edge_test entry and test_edges_scoring.cpp were removed.
