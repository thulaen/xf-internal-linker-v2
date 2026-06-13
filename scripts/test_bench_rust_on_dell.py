"""Unit tests for the bencher-output parser in bench_rust_on_dell."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "bench_rust_on_dell", Path(__file__).resolve().parent / "bench_rust_on_dell.py"
)
brod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(brod)


def test_parses_group_value_into_function_and_size():
    text = "test score_full_batch/100 ... bench:        1234 ns/iter (+/- 56)\n"
    rows = brod.parse_bencher_output(text, "scoring")
    assert rows == [{
        "extension": "scoring",
        "function_name": "score_full_batch",
        "input_size": "100",
        "mean_ns": 1234,
        "median_ns": 1234,
    }]


def test_strips_thousands_separators():
    text = "test bench_tokenize/100000 ... bench:    1,234,567 ns/iter (+/- 9,000)\n"
    rows = brod.parse_bencher_output(text, "texttok")
    assert rows[0]["mean_ns"] == 1234567


def test_id_without_slash_uses_default_size():
    text = "test pagerank_iter ... bench:        9999 ns/iter (+/- 1)\n"
    rows = brod.parse_bencher_output(text, "pagerank")
    assert rows[0]["function_name"] == "pagerank_iter"
    assert rows[0]["input_size"] == "default"


def test_ignores_non_bench_lines():
    text = "Compiling scoring v0.1.0\nrunning 3 tests\ngarbage\n"
    assert brod.parse_bencher_output(text, "scoring") == []


def test_multiple_sizes_one_kernel():
    text = (
        "test score/100 ... bench: 100 ns/iter (+/- 1)\n"
        "test score/10000 ... bench: 9000 ns/iter (+/- 5)\n"
    )
    rows = brod.parse_bencher_output(text, "scoring")
    assert {r["input_size"] for r in rows} == {"100", "10000"}
    assert len(rows) == 2
