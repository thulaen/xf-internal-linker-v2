from __future__ import annotations

from pathlib import Path
import subprocess
import sys


HOOK = Path(__file__).with_name("check-no-destructive-docker-commands.py")


def test_hook_blocks_staged_destructive_docker_command(tmp_path):
    repo = _init_repo(tmp_path)
    script = repo / "danger.sh"
    script.write_text("docker volume rm pgdata\n", encoding="utf-8")
    subprocess.run(["git", "add", "danger.sh"], cwd=repo, check=True)

    result = subprocess.run(
        [sys.executable, str(HOOK.resolve())],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "WHY:" in result.stderr
    assert "UNBLOCK:" in result.stderr


def test_hook_allows_documentation_exemption(tmp_path):
    repo = _init_repo(tmp_path)
    script = repo / "note.sh"
    script.write_text(
        "docker volume rm pgdata  # protected-data-stores: documentation\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "note.sh"], cwd=repo, check=True)

    result = subprocess.run(
        [sys.executable, str(HOOK.resolve())],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0


def _init_repo(path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    return path
