from __future__ import annotations

from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.destructive_command_guard import block_message, command_is_allowed


CHECK_EXTENSIONS = {".ps1", ".sh", ".py", ".yml", ".yaml", ".dockerfile"}
EXEMPT_PATH_PARTS = {".claude/hooks", ".githooks", "docs"}
DOCUMENTATION_MARKER = "protected-data-stores: documentation"


def main() -> int:
    blocked: list[str] = []
    for path in _staged_files():
        if not _should_check(path):
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            if DOCUMENTATION_MARKER in line:
                continue
            allowed, pattern = command_is_allowed(line)
            if not allowed:
                blocked.append(f"{path}:{number}\n{block_message(line, pattern)}")
    if blocked:
        sys.stderr.write("\n".join(blocked))
        return 2
    return 0


def _staged_files() -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRT"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [Path(line) for line in result.stdout.splitlines() if line.strip()]


def _should_check(path: Path) -> bool:
    normalized = path.as_posix()
    if any(part in normalized for part in EXEMPT_PATH_PARTS):
        return False
    if path.name.startswith("Dockerfile"):
        return True
    return path.suffix.lower() in CHECK_EXTENSIONS


if __name__ == "__main__":
    raise SystemExit(main())
