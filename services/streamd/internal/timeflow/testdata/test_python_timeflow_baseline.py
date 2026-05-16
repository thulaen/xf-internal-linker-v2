"""Tests for the Python timeflow baseline helper."""

import importlib.util
from pathlib import Path


def load_baseline_module():
    path = Path(__file__).with_name("python_timeflow_baseline.py")
    spec = importlib.util.spec_from_file_location("python_timeflow_baseline", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("baseline module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_boundary_iterations_are_required():
    module = load_baseline_module()
    try:
        module.parse_args(["python_timeflow_baseline.py", "timer", "0"])
    except SystemExit as exc:
        assert "greater than zero" in str(exc)
    else:
        raise AssertionError("zero iterations should be invalid")


def test_invalid_mode_is_rejected():
    module = load_baseline_module()
    try:
        module.parse_args(["python_timeflow_baseline.py", "bad", "1"])
    except SystemExit as exc:
        assert "mode must be one of" in str(exc)
    else:
        raise AssertionError("invalid mode should be rejected")


def test_baselines_return_positive_timings():
    module = load_baseline_module()
    for mode in ("timer", "window", "watermark"):
        _, iterations = module.parse_args(["python_timeflow_baseline.py", mode, "2"])
        result = {
            "timer": module.measure_timer_schedule,
            "window": module.measure_window_assignment,
            "watermark": module.measure_watermark_update,
        }[mode](iterations)
        assert result > 0
