cmake_minimum_required(VERSION 3.16)
project(xf_fuzz LANGUAGES CXX)

# ───────────────────────────────────────────────────────────────────
# libFuzzer harness for the C++ hot-path modules.
# Phase 4b of the test-hardening plan.
#
# libFuzzer is part of LLVM/Clang. It feeds randomly-mutated byte
# arrays into a `LLVMFuzzerTestOneInput` function thousands of times
# per second to provoke crashes, infinite loops, sanitizer reports,
# and memory leaks. Paired with AddressSanitizer (-fsanitize=fuzzer,
# address), it surfaces bugs that hand-written unit tests would miss.
#
# Requires Clang. GCC does not ship libFuzzer.
#
# Build:
#   cmake -B build_fuzz -S . -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
#   cmake --build build_fuzz --parallel 2
#
# Run (60-second smoke):
#   ./build_fuzz/fuzz_simsearch -max_total_time=60 corpus/simsearch/
#
# Crashes are written to the current working directory as
# `crash-<sha1>` files; commit them as regression fixtures.
# ───────────────────────────────────────────────────────────────────

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Guard: libFuzzer only works under Clang.
if(NOT CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
    message(FATAL_ERROR
        "libFuzzer requires Clang. Set -DCMAKE_CXX_COMPILER=clang++ before configuring.")
endif()

# Compile / link flags — fuzzer + ASan are mutually compatible and the
# usual pairing. Frame pointers stay so crash traces are readable.
set(FUZZ_FLAGS "-O1 -g -fno-omit-frame-pointer -fsanitize=fuzzer,address,undefined")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${FUZZ_FLAGS}")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} ${FUZZ_FLAGS}")

# Project source root + include dir (pybind11 / numpy headers expected
# upstream — the fuzz targets define XF_BENCH_MODE so the
# PYBIND11_MODULE() blocks are stripped before linking).
set(EXT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")
set(EXT_INC  "${EXT_ROOT}/include")
add_compile_definitions(XF_BENCH_MODE)

# pybind11 / Python headers still need to be reachable because the
# project .cpp files `#include <pybind11/numpy.h>` at the top even when
# XF_BENCH_MODE strips out the module-registration block at the bottom.
execute_process(
    COMMAND python -c "import pybind11; print(pybind11.get_include())"
    OUTPUT_VARIABLE PYBIND11_INCLUDE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
execute_process(
    COMMAND python -c "import sys; from sysconfig import get_paths; print(get_paths()['include'])"
    OUTPUT_VARIABLE PYTHON_INCLUDE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
include_directories(${PYBIND11_INCLUDE_DIR})
include_directories(${PYTHON_INCLUDE_DIR})

# ── Helper: register one fuzz target ─────────────────────────────
function(add_fuzz NAME SOURCE)
    add_executable(fuzz_${NAME} fuzz_${NAME}.cpp ${SOURCE})
    target_include_directories(fuzz_${NAME} PRIVATE ${EXT_INC} ${EXT_ROOT})
endfunction()

# ── Starter targets (3) ──────────────────────────────────────────
add_fuzz(simsearch   "${EXT_ROOT}/simsearch.cpp")
add_fuzz(scoring     "${EXT_ROOT}/scoring.cpp")
add_fuzz(passagesim  "${EXT_ROOT}/passagesim.cpp")
