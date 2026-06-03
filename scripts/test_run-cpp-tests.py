"""TDD guard for scripts/run-cpp-tests.sh.

Full icecc distribution tests live in scripts/tests/test_icecc_cpp_distribution.py.
"""
from scripts.tests.test_icecc_cpp_distribution import (  # noqa: F401
    test_cpp_tests_sources_icecc_helper,
    test_cpp_tests_passes_launcher_flags_to_cmake,
    test_cpp_tests_raises_parallel_count,
)
