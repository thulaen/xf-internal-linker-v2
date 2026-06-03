"""Tests for CodeQL language detection and command planning."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

import codeql_language_inventory as inventory
import run_codeql


class CodeQLLanguageInventoryTests(unittest.TestCase):
    def test_detects_only_supported_present_languages(self) -> None:
        paths = [
            "backend/extensions/scorer.cpp",
            "services/streamd/cmd/main.go",
            "backend/apps/pipeline/services/ranker.py",
            "frontend/src/app/app.component.ts",
            "services/findbugs-haskell/src/Main.hs",
            "backend/apps/core/migrations/0001_initial.py",
            "postgres/init.sql",
        ]

        result = inventory.detect_languages(paths)

        self.assertEqual(
            result.languages,
            ["c-cpp", "go", "python", "javascript-typescript"],
        )
        self.assertIn("haskell", result.unsupported_present)
        self.assertIn("sql", result.unsupported_present)

    def test_excludes_generated_vendored_and_cache_paths(self) -> None:
        paths = [
            "services/sidecars/api/gen/aclsd.pb.go",
            "backend/apps/realtime/_streamd_pb2/api_pb2.py",
            "frontend/node_modules/pkg/index.js",
            ".venv/Lib/site-packages/pkg/source.cpp",
            "backend/extensions/real_kernel.cpp",
        ]

        result = inventory.detect_languages(paths)

        self.assertEqual(result.languages, ["c-cpp"])

    def test_cli_prints_github_matrix_json(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/codeql_language_inventory.py",
                "--from-list",
                "backend/extensions/a.cpp",
                "frontend/src/main.ts",
                "--format",
                "github-matrix",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        matrix = json.loads(proc.stdout)
        self.assertEqual(
            [item["language"] for item in matrix["include"]],
            ["c-cpp", "javascript-typescript"],
        )

    def test_local_cli_uses_codeql_cli_language_names(self) -> None:
        args = run_codeql._database_create_args(
            "codeql",
            "javascript-typescript",
            Path("tmp/db/js"),
            "2",
            "1024",
        )

        self.assertIn("--language=javascript", args)
        self.assertNotIn("--language=javascript-typescript", args)

    def test_local_cli_lets_rust_use_default_extractor_mode(self) -> None:
        args = run_codeql._database_create_args("codeql", "rust", Path("tmp/db/rust"), "2", "1024")

        self.assertIn("--language=rust", args)
        self.assertNotIn("--build-mode=none", args)


if __name__ == "__main__":
    unittest.main()
