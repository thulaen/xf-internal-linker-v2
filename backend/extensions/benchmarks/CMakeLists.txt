cmake_minimum_required(VERSION 3.16)
project(xf_benchmarks LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── Compiler flags matching CPP-RULES.md ──
if(MSVC)
    add_compile_options(/O2 /arch:AVX2 /W4 /WX /sdl)
else()
    add_compile_options(
        -O3 -march=native -Wall -Wextra -Wpedantic -Werror
        -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion
        -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough
    )
endif()

# ── Benchmark mode: gates out PYBIND11_MODULE blocks ──
add_compile_definitions(XF_BENCH_MODE)

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

# ── FetchContent for Google Benchmark ──
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

# ── Extension source root ──
set(EXT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")
set(EXT_INC  "${EXT_ROOT}/include")

# ── Helper: add one benchmark executable ──
function(add_bench NAME)
    set(SOURCES ${ARGN})
    add_executable(bench_${NAME} bench_${NAME}.cpp ${SOURCES})
    target_include_directories(bench_${NAME} PRIVATE
        ${EXT_INC}
        ${EXT_ROOT}
        ${CMAKE_CURRENT_SOURCE_DIR}
    )
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

# ── Benchmark executables ──

# Category A: extern "C" already exists
add_bench(simsearch       "${EXT_ROOT}/simsearch.cpp")
add_bench(scoring         "${EXT_ROOT}/scoring.cpp")
add_bench(passagesim     "${EXT_ROOT}/passagesim.cpp")
add_bench(quantemb       "${EXT_ROOT}/quantemb.cpp")
add_bench(streaming_sketches)

# Category B: pure STL signatures
# add_bench(phrasematch "${EXT_ROOT}/phrasematch.cpp")
# add_bench(fieldrel    "${EXT_ROOT}/fieldrel.cpp")
# add_bench(linkparse   "${EXT_ROOT}/linkparse.cpp")

# Category C: extracted core functions
# add_bench(l2norm      "${EXT_ROOT}/l2norm.cpp")
# add_bench(feedrerank  "${EXT_ROOT}/feedrerank.cpp")
# add_bench(pagerank    "${EXT_ROOT}/pagerank.cpp")

# Category D: extracted core (STL return)
# add_bench(texttok     "${EXT_ROOT}/texttok.cpp")
# add_bench(rareterm    "${EXT_ROOT}/rareterm.cpp")

# FR-045 C++ batch fast path — pure-STL core, no TBB.
# add_bench(anchor_diversity "${EXT_ROOT}/anchor_diversity.cpp")

# ── Edge-case unit test executables ──
function(add_edge_test NAME)
    set(SOURCES ${ARGN})
    add_executable(test_edges_${NAME} test_edges_${NAME}.cpp ${SOURCES})
    target_include_directories(test_edges_${NAME} PRIVATE
        ${EXT_INC}
        ${EXT_ROOT}
        ${CMAKE_CURRENT_SOURCE_DIR}
    )
    if(NOT MSVC)
        find_package(TBB QUIET)
        if(TBB_FOUND)
            target_link_libraries(test_edges_${NAME} PRIVATE TBB::tbb)
            target_compile_definitions(test_edges_${NAME} PRIVATE HAS_TBB=1)
        endif()
    endif()
    add_test(NAME edge_${NAME} COMMAND test_edges_${NAME})
endfunction()

enable_testing()

add_edge_test(simsearch "${EXT_ROOT}/simsearch.cpp")
add_edge_test(scoring   "${EXT_ROOT}/scoring.cpp")
