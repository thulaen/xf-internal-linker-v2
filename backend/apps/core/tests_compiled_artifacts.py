"""Focused tests for Docker-managed compiled artifact storage."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path
from types import ModuleType
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase


def _load_script() -> ModuleType:
    repo_root = Path(settings.REPO_ROOT) if hasattr(settings, "REPO_ROOT") else None
    if repo_root is None or not (repo_root / "scripts").exists():
        repo_root = Path("/repo")
    if not (repo_root / "scripts").exists():
        repo_root = Path(settings.BASE_DIR).parent
    script_path = repo_root / "scripts" / "ensure_compiled_artifacts.py"
    spec = importlib.util.spec_from_file_location("ensure_compiled_artifacts_test", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load ensure_compiled_artifacts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _configure_paths(module: ModuleType, root: Path) -> None:
    artifact_root = root / "compiled"
    module.ARTIFACT_ROOT = artifact_root
    module.BUILD_ROOT = root / "build"
    module.BACKEND_ROOT = root / "backend"
    module.REPO_ROOT = root / "repo"
    module.MANIFEST_PATH = artifact_root / "manifest.json"
    module.STORE_ROOT = artifact_root / "store"
    module.ACTIVE_ROOT = artifact_root / "active"
    module.ACTIVE_EXTENSIONS_ROOT = module.ACTIVE_ROOT / "extensions"
    module.ACTIVE_GO_ROOT = module.ACTIVE_ROOT / "go"
    module.ROLLBACK_ROOT = artifact_root / "rollback"


class CompiledArtifactScriptTests(SimpleTestCase):
    def test_unchanged_cpp_source_skips_rebuild_when_active_artifacts_exist(self) -> None:
        module = _load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _configure_paths(module, root)
            module.EXTENSION_NAMES = {"scoring"}
            module.ACTIVE_EXTENSIONS_ROOT.mkdir(parents=True)
            (module.ACTIVE_EXTENSIONS_ROOT / "scoring.so").write_bytes(b"runtime")
            manifest = {"active": {"cpp_runtime": {"source_hash": "same"}}, "store": {}}

            rebuilt = module._build_cpp_runtime(root / "backend", "same", manifest)

        self.assertFalse(rebuilt)

    def test_changed_cpp_source_builds_in_scratch_then_activates_after_verify(self) -> None:
        module = _load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _configure_paths(module, root)
            (module.BACKEND_ROOT / "extensions").mkdir(parents=True)
            module.EXTENSION_NAMES = {"scoring", "simsearch", "texttok"}
            manifest = {"active": {}, "store": {}}

            def fake_run(command: list[str], cwd: Path) -> None:
                output = Path(command[command.index("--build-lib") + 1])
                output.mkdir(parents=True)
                for name in module.EXTENSION_NAMES:
                    (output / f"{name}.so").write_bytes(b"same-binary")

            with mock.patch.object(module, "_run", side_effect=fake_run):
                with mock.patch.object(module, "_verify_runtime_imports"):
                    rebuilt = module._build_cpp_runtime(module.BACKEND_ROOT, "changed", manifest)

            active_files = {path.name for path in module.ACTIVE_EXTENSIONS_ROOT.glob("*.so")}

        self.assertTrue(rebuilt)
        self.assertEqual(active_files, {"scoring.so", "simsearch.so", "texttok.so"})
        self.assertEqual(len(manifest["store"]), 1)

    def test_failed_cpp_import_verification_leaves_old_active_artifacts(self) -> None:
        module = _load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _configure_paths(module, root)
            module.ACTIVE_EXTENSIONS_ROOT.mkdir(parents=True)
            old_artifact = module.ACTIVE_EXTENSIONS_ROOT / "scoring.so"
            old_artifact.write_bytes(b"old")
            stage_dir = module.ACTIVE_ROOT / ".stage-test"
            (stage_dir / "extensions").mkdir(parents=True)
            (stage_dir / "extensions" / "scoring.so").write_bytes(b"new")

            with mock.patch.object(module, "_verify_runtime_imports", side_effect=RuntimeError):
                with self.assertRaises(RuntimeError):
                    module._activate_staged_runtime(stage_dir)

            still_old = old_artifact.read_bytes()

        self.assertEqual(still_old, b"old")

    def test_no_go_modules_records_state_without_fake_artifacts(self) -> None:
        module = _load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _configure_paths(module, root)
            module.REPO_ROOT.mkdir(parents=True)
            manifest = {"active": {}, "store": {}}

            module._record_go_state(module.REPO_ROOT, manifest)

            go_entry = manifest["active"]["go_runtime"]

        self.assertEqual(go_entry["status"], "no-go-modules")
        self.assertFalse(module.ACTIVE_GO_ROOT.exists())

    def test_identical_compiled_outputs_share_one_store_file(self) -> None:
        module = _load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _configure_paths(module, root)
            first = root / "first.so"
            second = root / "second.so"
            first.write_bytes(b"same")
            second.write_bytes(b"same")
            manifest = {"active": {}, "store": {}}

            first_record = module._store_artifact(first, manifest)
            second_record = module._store_artifact(second, manifest)

            store_files = list(module.STORE_ROOT.iterdir())

        self.assertEqual(first_record["sha256"], second_record["sha256"])
        self.assertEqual(len(store_files), 1)

    def test_prune_stale_deletes_scratch_but_keeps_manifest_referenced_store(self) -> None:
        module = _load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _configure_paths(module, root)
            scratch = module.BUILD_ROOT / "old-test-build"
            scratch.mkdir(parents=True)
            store_file = module.STORE_ROOT / ("a" * 64)
            store_file.parent.mkdir(parents=True)
            store_file.write_bytes(b"keep")
            manifest = {
                "active": {
                    "cpp_runtime": {
                        "artifacts": [{"sha256": "a" * 64, "store_path": str(store_file)}],
                    }
                },
                "store": {},
            }
            module._write_manifest(manifest)

            result = module.prune_stale(retention_days=0)

            kept_store = store_file.exists()
            scratch_deleted = not scratch.exists()

        self.assertTrue(kept_store)
        self.assertTrue(scratch_deleted)
        self.assertEqual(result["scratch_dirs"], [str(scratch)])

    def test_prune_refuses_compiled_artifact_root_as_scratch(self) -> None:
        module = _load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _configure_paths(module, root)
            module.BUILD_ROOT = module.ARTIFACT_ROOT

            with self.assertRaisesMessage(ValueError, "compiled artifact storage"):
                module.prune_stale()
