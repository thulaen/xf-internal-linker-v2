import importlib.util
import os
import sys
from pathlib import Path
import pytest

# Load the module dynamically since it has hyphens in the name
current_dir = Path(__file__).parent
module_path = current_dir / "check-docs-updated.py"

spec = importlib.util.spec_from_file_location("check_docs_updated", module_path)
check_docs_updated = importlib.util.module_from_spec(spec)
sys.modules["check_docs_updated"] = check_docs_updated
spec.loader.exec_module(check_docs_updated)

class TestCheckDocsUpdated:
    @pytest.mark.parametrize("path,expected", [
        ("backend/app/main.py", True),
        ("frontend/src/index.ts", True),
        ("rust/src/lib.rs", True),
        ("scripts/deploy.sh", True),
        ("services/go-service/main.go", True),
        # False cases
        ("docs/index.md", False),
        ("frontend/public/favicon.ico", False), # doesn't start with frontend/src/
        ("random_dir/file.txt", False),
        (".github/workflows/ci.yml", False),
    ])
    def test_is_source_file(self, path, expected):
        assert check_docs_updated.is_source_file(path) == expected

    @pytest.mark.parametrize("path,expected", [
        # Test files
        ("backend/test_main.py", True),
        ("test_root.py", True),
        ("frontend/src/app_test.py", True),
        ("app_test.py", True),
        ("conftest.py", True),
        ("backend/conftest.py", True),
        ("backend/tests/something.py", True),
        ("frontend/src/app.spec.ts", True),
        ("frontend/src/app.stories.ts", True),
        # Config files
        (".env", True),
        (".env.local", True),
        ("config.yml", True),
        ("backend/config.yaml", True),
        ("package.json", True), # root-level JSON
        # Config False cases
        ("backend/package.json", False), # nested JSON is not exempt
        # CI/CD
        (".github/workflows/main.yml", True),
        # Agent protocol files
        ("AGENT-HANDOFF.md", True),
        ("AI-CONTEXT.md", True),
        ("PLAIN-ENGLISH-RULE.md", True),
        ("THINK-BEFORE-YOU-CODE.md", True),
        ("NO-DUPLICATES.md", True),
        # Hook scripts
        (".githooks/pre-commit", True),
        (".githooks/check-docs-updated.py", True),
        # Docs directories
        ("docs/architecture.md", True),
        ("docs-site/docs/index.md", True),
        # Migrations
        ("backend/app/migrations/0001_initial.py", True),
        ("backend/migrations/0002_auto.py", True),
        # Lock files
        ("package-lock.json", True),
        ("backend/poetry.lock", True),
        ("rust/Cargo.lock", True),
        # Type stubs
        ("frontend/src/types.d.ts", True),
        
        # General non-exempt source files (False cases)
        ("backend/app/main.py", False),
        ("frontend/src/index.ts", False),
        ("rust/src/lib.rs", False),
        ("scripts/deploy.sh", False),
        ("services/go-service/main.go", False),
    ])
    def test_is_exempt(self, path, expected):
        assert check_docs_updated.is_exempt(path) == expected

    @pytest.mark.parametrize("path,expected", [
        ("docs-site/docs/index.md", True),
        ("docs-site/package.json", True),
        ("docs/index.md", False),
        ("backend/docs-site.py", False),
    ])
    def test_is_docs_file(self, path, expected):
        assert check_docs_updated.is_docs_file(path) == expected

    def test_main_empty_staged_files(self, monkeypatch):
        monkeypatch.setattr(check_docs_updated, "staged_files", lambda: [])
        assert check_docs_updated.main() == 0

    def test_main_only_exempt_files(self, monkeypatch):
        monkeypatch.setattr(check_docs_updated, "staged_files", lambda: [
            "backend/tests/test_main.py",
            "package.json",
            ".githooks/pre-commit",
            "backend/migrations/0001_initial.py"
        ])
        assert check_docs_updated.main() == 0

    def test_main_only_non_source_files(self, monkeypatch):
        # e.g., root files that are not json/yaml, or other non-source dirs
        monkeypatch.setattr(check_docs_updated, "staged_files", lambda: [
            "README.md",
            "other_dir/some_file.txt"
        ])
        assert check_docs_updated.main() == 0

    def test_main_source_file_missing_docs(self, monkeypatch, capsys):
        monkeypatch.setattr(check_docs_updated, "staged_files", lambda: [
            "backend/app/main.py"
        ])
        assert check_docs_updated.main() == 1
        captured = capsys.readouterr()
        assert "FAIL check-docs-updated" in captured.out
        assert "backend/app/main.py" in captured.out

    def test_main_multiple_source_files_missing_docs(self, monkeypatch, capsys):
        # Test capping of files output to 10
        files = [f"backend/app/file{i}.py" for i in range(15)]
        monkeypatch.setattr(check_docs_updated, "staged_files", lambda: files)
        assert check_docs_updated.main() == 1
        captured = capsys.readouterr()
        assert "FAIL check-docs-updated" in captured.out
        # Should print first 10
        for i in range(10):
            assert f"backend/app/file{i}.py" in captured.out
        # Should truncate
        assert "and 5 more" in captured.out
        assert "backend/app/file11.py" not in captured.out

    def test_main_source_file_with_docs(self, monkeypatch):
        monkeypatch.setattr(check_docs_updated, "staged_files", lambda: [
            "backend/app/main.py",
            "docs-site/docs/updated_api.md"
        ])
        assert check_docs_updated.main() == 0

    def test_main_source_file_with_exempt_file_missing_docs(self, monkeypatch, capsys):
        monkeypatch.setattr(check_docs_updated, "staged_files", lambda: [
            "backend/app/main.py",
            "backend/tests/test_main.py"
        ])
        assert check_docs_updated.main() == 1
        captured = capsys.readouterr()
        assert "backend/app/main.py" in captured.out
        # test_main.py shouldn't be listed as it's exempt
        assert "test_main.py" not in captured.out
