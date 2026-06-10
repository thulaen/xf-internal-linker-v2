"""Tests for the Rust RankingDecisionEngine Python boundary.

Given the live ranking authority is a PyO3 Rust module, When Python code calls
the boundary wrapper, Then every public call is delegated to
``extensions.ranking_decision_engine`` and a missing kernel raises loudly with
no Python fallback.
"""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any

from django.test import SimpleTestCase


class RankingDecisionEngineLoaderTests(SimpleTestCase):
    """Boundary behaviour for ``services.ranking_decision_engine``."""

    def setUp(self) -> None:
        self._injected: list[str] = []
        self.addCleanup(self._remove_injected)

    def _inject(self, fullname: str, module: types.ModuleType) -> None:
        sys.modules[fullname] = module
        self._injected.append(fullname)

    def _remove_injected(self) -> None:
        for name in self._injected:
            sys.modules.pop(name, None)

    def _load_wrapper(self):
        module = importlib.import_module("apps.pipeline.services.ranking_decision_engine")
        return importlib.reload(module)

    def test_public_functions_delegate_to_rust_module(self) -> None:
        calls: list[tuple[str, tuple[Any, ...]]] = []
        fake = types.ModuleType("extensions.ranking_decision_engine")

        def record(name: str):
            def _inner(*args: Any) -> str:
                calls.append((name, args))
                return f"{name}:ok"

            return _inner

        fake.rank_candidates = record("rank_candidates")  # type: ignore[attr-defined]
        fake.validate_profile = record("validate_profile")  # type: ignore[attr-defined]
        fake.memory_estimate = record("memory_estimate")  # type: ignore[attr-defined]
        fake.explain = record("explain")  # type: ignore[attr-defined]
        self._inject("extensions.ranking_decision_engine", fake)

        wrapper = self._load_wrapper()

        self.assertEqual(wrapper.rank_candidates({"candidates": [1]}), "rank_candidates:ok")
        self.assertEqual(wrapper.validate_profile({"profile": 1}), "validate_profile:ok")
        self.assertEqual(wrapper.memory_estimate({"count": 1}), "memory_estimate:ok")
        self.assertEqual(wrapper.explain("decision-1"), "explain:ok")
        self.assertEqual(
            calls,
            [
                ("rank_candidates", ({"candidates": [1]},)),
                ("validate_profile", ({"profile": 1},)),
                ("memory_estimate", ({"count": 1},)),
                ("explain", ("decision-1",)),
            ],
        )

    def test_type_lookup_delegates_to_rust_module(self) -> None:
        fake = types.ModuleType("extensions.ranking_decision_engine")
        fake.rank_candidates = lambda request: request  # type: ignore[attr-defined]
        fake.CandidateInput = type("CandidateInput", (), {})  # type: ignore[attr-defined]
        fake.WeightProfile = type("WeightProfile", (), {})  # type: ignore[attr-defined]
        self._inject("extensions.ranking_decision_engine", fake)

        wrapper = self._load_wrapper()

        self.assertIs(wrapper.CandidateInput, fake.CandidateInput)
        self.assertIs(wrapper.WeightProfile, fake.WeightProfile)
        with self.assertRaises(AttributeError):
            _ = wrapper.UnknownRustType

    def test_missing_rust_module_has_no_python_fallback(self) -> None:
        wrapper = self._load_wrapper()
        original_module = wrapper._KERNEL_MODULE
        wrapper._KERNEL_MODULE = "extensions.ranking_decision_engine_missing_for_test"
        self.addCleanup(setattr, wrapper, "_KERNEL_MODULE", original_module)

        with self.assertRaises(wrapper.RankingDecisionEngineUnavailableError) as ctx:
            wrapper.rank_candidates({"candidates": []})

        message = str(ctx.exception)
        self.assertIn("extensions.ranking_decision_engine_missing_for_test", message)
        self.assertIn("no Python fallback", message)
