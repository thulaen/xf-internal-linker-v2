cmake_minimum_required(VERSION 3.20)
project(xf_extensions_tests CXX)
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
find_package(TBB REQUIRED)
add_compile_definitions(XF_BENCH_MODE)
add_compile_options(-O1)
add_executable(test_simsearch tests/test_simsearch.cpp simsearch.cpp)
target_include_directories(test_simsearch PRIVATE include)
target_link_libraries(test_simsearch GTest::gtest_main TBB::tbb)
add_executable(test_scoring tests/test_scoring.cpp scoring.cpp)
target_include_directories(test_scoring PRIVATE include)
target_link_libraries(test_scoring GTest::gtest_main TBB::tbb)
include(GoogleTest)
gtest_discover_tests(test_simsearch)
gtest_discover_tests(test_scoring)
