cmake_minimum_required(VERSION 3.16)
project(xf_fuzz LANGUAGES CXX)

# libFuzzer harnesses for the C++ hot-path modules.
#
# Build:
#   cmake -B build_fuzz -S . -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
#   cmake --build build_fuzz --parallel 2
#
# Run:
#   ./build_fuzz/fuzz_simsearch -max_total_time=60 corpus/simsearch/

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
    message(FATAL_ERROR
        "libFuzzer requires Clang. Set -DCMAKE_CXX_COMPILER=clang++ before configuring.")
endif()

set(FUZZ_FLAGS "-O1 -g -fno-omit-frame-pointer -fsanitize=fuzzer,address,undefined")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${FUZZ_FLAGS}")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} ${FUZZ_FLAGS}")

set(EXT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")
set(EXT_INC  "${EXT_ROOT}/include")
add_compile_definitions(XF_BENCH_MODE)

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

function(add_fuzz NAME SOURCE)
    add_executable(fuzz_${NAME} fuzz_${NAME}.cpp ${SOURCE})
    target_include_directories(fuzz_${NAME} PRIVATE ${EXT_INC} ${EXT_ROOT})
endfunction()

function(add_single_file_fuzz NAME)
    add_executable(fuzz_${NAME} fuzz_${NAME}.cpp)
    target_include_directories(fuzz_${NAME} PRIVATE ${EXT_INC} ${EXT_ROOT})
endfunction()

# simsearch ported to Rust (rust/extensions/simsearch); its C++ source, header,
# fuzz harness, benchmark, and edge test were removed per RUST-FIRST.md
# dead-code-on-replace. Fuzzing is now the cargo-test/criterion suite in
# rust/extensions/simsearch.
# scoring ported to Rust (rust/extensions/scoring) per RUST-FIRST.md
# dead-code-on-replace; its C++ source, header, fuzz harness, benchmark, and
# edge test were removed.
# passagesim ported to Rust (rust/extensions/passagesim) per RUST-FIRST.md
# dead-code-on-replace; its C++ source, header, fuzz harness, GoogleTest unit
# test, and benchmark were removed.
# quantemb ported to Rust (rust/extensions/quantemb) per RUST-FIRST.md
# dead-code-on-replace; its C++ source, header, fuzz harness, GoogleTest unit
# test, and benchmark were removed.
# rareterm ported to Rust (rust/extensions/rareterm); its C++ source, header,
# fuzz harness, and benchmark were removed per RUST-FIRST.md dead-code-on-replace.
# texttok ported to Rust (rust/extensions/texttok); its C++ source, header, and
# fuzz harness were removed per RUST-FIRST.md dead-code-on-replace.
# anchor_descriptiveness ported to Rust (rust/extensions/anchor_descriptiveness);
# its C++ source and fuzz harness were removed per RUST-FIRST.md dead-code-on-replace.
# anchor_diversity ported to Rust (rust/extensions/anchor_diversity); its C++
# source, header, fuzz harness, and benchmark were removed per RUST-FIRST.md dead-code-on-replace.
# api_rate_limiter ported to Rust (rust/extensions/api_rate_limiter); its C++
# single-file fuzz harness was removed per RUST-FIRST.md dead-code-on-replace.
# anchor_self_information ported to Rust (rust/extensions/anchor_self_information);
# its C++ fuzz harness was removed per RUST-FIRST.md dead-code-on-replace.
# compressed_bloom ported to Rust (rust/extensions/compressed_bloom); its C++
# fuzz harness was removed per RUST-FIRST.md dead-code-on-replace.
# count_min_sketch ported to Rust (rust/extensions/count_min_sketch); its C++
# fuzz harness was removed per RUST-FIRST.md dead-code-on-replace.
# counting_bloom ported to Rust (rust/extensions/counting_bloom); its C++
# fuzz harness was removed per RUST-FIRST.md dead-code-on-replace.
# feedrerank ported to Rust (rust/extensions/feedrerank); its C++ single-file
# fuzz harness was removed per RUST-FIRST.md dead-code-on-replace.
# fieldrel ported to Rust (rust/extensions/fieldrel); its C++ single-file fuzz
# harness was removed per RUST-FIRST.md dead-code-on-replace.
# generic_anchor_matcher ported to Rust (rust/extensions/generic_anchor_matcher);
# its C++ fuzz harness was removed per RUST-FIRST.md dead-code-on-replace.
# ivf_index ported to Rust (rust/extensions/ivf_index); its C++ source, header,
# single-file fuzz harness, GoogleTest unit test, and benchmark were removed per
# RUST-FIRST.md dead-code-on-replace.
# linkparse ported to Rust (rust/extensions/linkparse); its C++ source, header,
# fuzz harness, and orphan benchmark were removed per RUST-FIRST.md dead-code-on-replace.
# pagerank ported to Rust (rust/extensions/pagerank); its C++ single-file fuzz
# harness was removed per RUST-FIRST.md dead-code-on-replace.
# phrasematch ported to Rust (rust/extensions/phrasematch); its C++ source,
# header, and fuzz harness were removed per RUST-FIRST.md dead-code-on-replace.
