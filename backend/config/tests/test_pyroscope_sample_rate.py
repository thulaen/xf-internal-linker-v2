"""Tests for Pyroscope profiler sampling defaults."""

from pathlib import Path


BASE_SETTINGS = Path(__file__).resolve().parents[1] / "settings" / "base.py"


def test_pyroscope_sample_rate_defaults_to_250_samples_per_second():
    text = BASE_SETTINGS.read_text(encoding="utf-8")

    assert 'sample_rate=env.int("PYROSCOPE_SAMPLE_RATE", default=250)' in text
