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
add_executable(test_quantemb tests/test_quantemb.cpp quantemb.cpp)
target_include_directories(test_quantemb PRIVATE include)
target_link_libraries(test_quantemb GTest::gtest_main)
add_executable(test_streaming_sketches tests/test_streaming_sketches.cpp)
target_include_directories(test_streaming_sketches PRIVATE include)
target_link_libraries(test_streaming_sketches GTest::gtest_main)
include(GoogleTest)
gtest_discover_tests(test_simsearch)
gtest_discover_tests(test_scoring)
gtest_discover_tests(test_passagesim)
gtest_discover_tests(test_quantemb)
gtest_discover_tests(test_streaming_sketches)
