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

add_fuzz(simsearch   "${EXT_ROOT}/simsearch.cpp")
add_fuzz(scoring     "${EXT_ROOT}/scoring.cpp")
add_fuzz(passagesim  "${EXT_ROOT}/passagesim.cpp")
add_fuzz(quantemb    "${EXT_ROOT}/quantemb.cpp")
add_fuzz(rareterm    "${EXT_ROOT}/rareterm.cpp")
add_fuzz(texttok     "${EXT_ROOT}/texttok.cpp")
