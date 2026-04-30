"""Benchmark for Pick #56 Aho-Corasick Multi-Pattern Matcher."""

import time
import re
from apps.pipeline.services.pattern_matcher import AhoCorasickMatcher


def test_bench_aho_corasick_vs_regex(benchmark):
    """Compare Aho-Corasick against a standard regex loop for 1000 patterns."""
    patterns = [f"pattern_{i}" for i in range(1000)]
    # Add some real patterns that might actually match
    patterns.extend(["apple", "banana", "cherry", "date", "elderberry"])
    
    text = "I like apple and banana, but not cherry pie or date fruit or elderberry jam. " * 100
    # Add some noise
    text += " ".join([f"word_{i}" for i in range(1000)])
    
    # --- Legacy Regex Loop ---
    def regex_scan(text, patterns):
        matches = []
        for p in patterns:
            for match in re.finditer(re.escape(p), text, re.IGNORECASE):
                matches.append(match.group(0))
        return matches

    # --- Aho-Corasick Matcher ---
    matcher = AhoCorasickMatcher(case_sensitive=False)
    for p in patterns:
        matcher.add_pattern(p, p)
    matcher.build()

    def aho_scan(text, matcher):
        return matcher.find_all(text)

    # Benchmark Regex
    start_regex = time.perf_counter()
    res_regex = regex_scan(text, patterns)
    end_regex = time.perf_counter()
    regex_time = end_regex - start_regex

    # Benchmark Aho-Corasick
    start_aho = time.perf_counter()
    res_aho = aho_scan(text, matcher)
    end_aho = time.perf_counter()
    aho_time = end_aho - start_aho

    print(f"\nRegex time: {regex_time:.6f}s")
    print(f"Aho-Corasick time: {aho_time:.6f}s")
    print(f"Speedup: {regex_time / aho_time:.2f}x")

    assert len(res_regex) == len(res_aho)
    assert regex_time / aho_time >= 5.0  # Objective: >= 5x speedup
