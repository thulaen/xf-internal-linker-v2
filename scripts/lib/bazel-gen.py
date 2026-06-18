#!/usr/bin/env python3
"""Compatibility wrapper for the Bazel generator helper."""

from __future__ import annotations

from bazel_gen import render_exports_files, write_if_changed

__all__ = ["render_exports_files", "write_if_changed"]
