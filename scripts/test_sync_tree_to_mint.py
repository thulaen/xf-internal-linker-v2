from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = ROOT / "scripts" / "sync-tree-to-mint.sh"


def _sync_text() -> str:
    return SYNC_SCRIPT.read_text(encoding="utf-8")


def test_mint_sync_uses_git_file_list_instead_of_whole_tree_tar() -> None:
    text = _sync_text()

    assert "git ls-files -z --cached --modified --others --exclude-standard" in text
    assert "-C \"${REPO_ROOT}\" ." not in text
    assert "tar --null -T -" in text


def test_mint_sync_excludes_generated_permission_heavy_paths() -> None:
    text = _sync_text()

    for excluded in (
        "backend/coverage-html/*",
        "backend/extensions/build_tests/*",
        "backend/staticfiles/*",
        "backend/media/*",
        "backend/extensions/reports/*",
        "services/speccheck/mutants.out",
        "services/speccheck/mutants.out/*",
        "services/speccheck/mutants.out.old/*",
        "frontend/dist/*",
        "node_modules/*",
    ):
        assert excluded in text


def test_mint_sync_removes_stale_helper_files_but_preserves_git_dir() -> None:
    text = _sync_text()

    assert "docker run --rm -v" in text
    assert "find" in text
    assert "/repo" in text
    assert "-mindepth 1 -maxdepth 1" in text
    assert "! -name .git" in text
    assert "-exec rm -rf {} +" in text
    assert "tar -xzf - -C" in text
