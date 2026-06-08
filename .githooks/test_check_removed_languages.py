#!/usr/bin/env python3
"""Tests for ``.githooks/check-removed-languages.py``.

The guard enforces the two-language policy (Python + Rust only): a staged file
that ADDS or MODIFIES a removed-language source (C/C++, Go, Haskell, Lua, Java)
hard-blocks the commit. Rust (``.rs`` / ``Cargo.toml``) and Python stay allowed,
and DELETING a removed-language file is fine (the migration removes them).

These tests exercise the pure ``removed_language`` classifier so no real git/
staging is needed.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_HOOK_PATH = Path(__file__).resolve().parent / "check-removed-languages.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_removed_languages_uut", _HOOK_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("could not load check-removed-languages.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load()


class RemovedLanguageTests(unittest.TestCase):
    def test_cpp_sources_blocked(self) -> None:
        for p in (
            "backend/extensions/scoring.cpp",
            "backend/extensions/include/perfetto.h",
            "a/b.cc", "a/b.cxx", "a/b.hpp",
        ):
            self.assertEqual(hook.removed_language(p), "C/C++", p)

    def test_go_blocked(self) -> None:
        self.assertEqual(hook.removed_language("services/streamd/cmd/streamd/main.go"), "Go")
        self.assertEqual(hook.removed_language("services/streamd/go.mod"), "Go")
        self.assertEqual(hook.removed_language("services/streamd/go.sum"), "Go")
        self.assertEqual(hook.removed_language("services/sidecars/api/api.proto"), "Go")

    def test_haskell_blocked(self) -> None:
        self.assertEqual(hook.removed_language("services/findbugs-haskell/src/Main.hs"), "Haskell")
        self.assertEqual(hook.removed_language("services/findbugs-haskell/findbugs.cabal"), "Haskell")

    def test_lua_blocked(self) -> None:
        self.assertEqual(hook.removed_language("backend/lua/rules.lua"), "Lua")

    def test_java_blocked(self) -> None:
        self.assertEqual(hook.removed_language("src/Main.java"), "Java")

    def test_rust_allowed(self) -> None:
        for p in ("services/speccheck/src/lib.rs", "services/speccheck/Cargo.toml",
                  "services/speccheck/Cargo.lock"):
            self.assertIsNone(hook.removed_language(p), p)

    def test_python_and_docs_allowed(self) -> None:
        for p in ("backend/apps/pipeline/services/ranker.py", "docs/CPP-ROADMAP.md",
                  "config/mutation-routing.json", "README.md"):
            self.assertIsNone(hook.removed_language(p), p)

    def test_backslash_paths_normalised(self) -> None:
        self.assertEqual(hook.removed_language("backend\\extensions\\scoring.cpp"), "C/C++")

    def test_classify_staged_collects_violations(self) -> None:
        staged = ["a.py", "b.rs", "c.go", "d.cpp", "e.hs", "f.lua", "g.java", "go.mod"]
        violations = hook.classify_staged(staged)
        # py + rs allowed; the other six (+ go.mod) blocked
        flagged = {v[0] for v in violations}
        self.assertEqual(flagged, {"c.go", "d.cpp", "e.hs", "f.lua", "g.java", "go.mod"})
        self.assertNotIn("a.py", flagged)
        self.assertNotIn("b.rs", flagged)

    def test_extensionless_path_allowed(self) -> None:
        # A file with no extension (Dockerfile, Makefile, LICENSE, a bare name)
        # is not a removed-language source, so the classifier returns None.
        for p in ("Dockerfile", "Makefile", "LICENSE", "scripts/run", "a/b/c"):
            self.assertIsNone(hook.removed_language(p), p)

    def test_cargo_lock_and_generic_toml_allowed(self) -> None:
        # Cargo.lock is a kept-language (Rust) manifest, and a generic .toml is
        # plain configuration; neither is a removed language, so both are None.
        for p in ("services/speccheck/Cargo.lock", "Cargo.lock",
                  "pyproject.toml", "config/settings.toml"):
            self.assertIsNone(hook.removed_language(p), p)

    def test_go_under_services_cmd_blocked(self) -> None:
        # A Go source nested under a service's cmd/ directory is still Go and
        # must be hard-blocked.
        self.assertEqual(hook.removed_language("services/streamd/cmd/x.go"), "Go")


if __name__ == "__main__":
    unittest.main(verbosity=2)
