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
add_executable(test_simsearch tests/test_simsearch.cpp simsearch.cpp)
target_include_directories(test_simsearch PRIVATE include)
if (TBB_FOUND)
    target_link_libraries(test_simsearch GTest::gtest_main TBB::tbb)
else()
    target_link_libraries(test_simsearch GTest::gtest_main)
endif()
add_executable(test_scoring tests/test_scoring.cpp scoring.cpp)
target_include_directories(test_scoring PRIVATE include)
if (TBB_FOUND)
    target_link_libraries(test_scoring GTest::gtest_main TBB::tbb)
else()
    target_link_libraries(test_scoring GTest::gtest_main)
endif()
add_executable(test_passagesim tests/test_passagesim.cpp passagesim.cpp)
target_include_directories(test_passagesim PRIVATE include)
target_link_libraries(test_passagesim GTest::gtest_main)
add_executable(test_fieldrel tests/test_fieldrel.cpp fieldrel.cpp)
target_include_directories(test_fieldrel PRIVATE include)
target_link_libraries(test_fieldrel GTest::gtest_main)
add_executable(test_quantemb tests/test_quantemb.cpp quantemb.cpp)
target_include_directories(test_quantemb PRIVATE include)
target_link_libraries(test_quantemb GTest::gtest_main)
add_executable(test_ivf_index tests/test_ivf_index.cpp ivf_index.cpp)
target_include_directories(test_ivf_index PRIVATE include)
target_link_libraries(test_ivf_index GTest::gtest_main)
add_executable(test_streaming_sketches tests/test_streaming_sketches.cpp)
target_include_directories(test_streaming_sketches PRIVATE include)
target_link_libraries(test_streaming_sketches GTest::gtest_main)

add_executable(test_papertrail_dedup tests/test_papertrail_dedup.cpp papertrail_dedup.cpp)
target_include_directories(test_papertrail_dedup PRIVATE include)
target_link_libraries(test_papertrail_dedup GTest::gtest_main)

add_executable(test_lesson_index tests/test_lesson_index.cpp lesson_index.cpp)
target_include_directories(test_lesson_index PRIVATE include)
target_link_libraries(test_lesson_index GTest::gtest_main)

enable_testing()
set(XF_GTEST_TARGETS
    test_simsearch
    test_scoring
    test_passagesim
    test_fieldrel
    test_quantemb
    test_ivf_index
    test_streaming_sketches
    test_papertrail_dedup
    test_lesson_index
)
foreach(test_target IN LISTS XF_GTEST_TARGETS)
    add_test(NAME ${test_target} COMMAND $<TARGET_FILE:${test_target}>)
    set_tests_properties(
        ${test_target}
        PROPERTIES ENVIRONMENT "GTEST_SHUFFLE=1;GTEST_RANDOM_SEED=0"
    )
endforeach()
