"""Hard check for unresolved CodeQL-backed AutoIssues."""

from __future__ import annotations

import subprocess


def main() -> int:
    proc = subprocess.run([
        "docker",
        "compose",
        "exec",
        "-T",
        "backend",
        "python",
        "manage.py",
        "verify_codeql_autoissues",
        "--max-open",
        "10",
        "--block-open",
    ])
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
