"""Pytest settings for top-level script tests."""
from __future__ import annotations


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "property: property-based tests over pure script logic",
    )
