"""Phantom-reference CI gate.

Fails the build if any banned token from `deleted_tokens.txt` reappears
anywhere in the repo outside the small allow-list of paths where deleted
names are permitted to remain as historical record (the plan file, the
DELETED-FEATURES.md gravestone, this script's own data file, and git
history itself).

Purpose: when a feature is deleted per plans/check-how-many-pending-tidy-iverson.md,
its identifiers must disappear from every surface. Without this gate, a
future AI session re-reading old doc crumbs might try to resurrect the
feature — the exact "spinning in circles" problem the plan calls out.

Run locally:
    python backend/scripts/check_phantom_references.py

Run in CI:
    Add to .github/workflows/*.yml as a required job.

Exit codes:
    0 — no phantom references found.
    1 — one or more banned tokens appeared in unexpected files.
    2 — the banned-token data file is missing or malformed.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# ── Paths where banned tokens ARE allowed (historical / decision record).
ALLOWED_PATHS: tuple[str, ...] = (
    ".git",
    ".claude",
    "plans/check-how-many-pending-tidy-iverson.md",
    "docs/DELETED-FEATURES.md",
    "backend/scripts/deleted_tokens.txt",
    "backend/scripts/check_phantom_references.py",
    # Authoritative rule files legitimately name retired identifiers in
    # order to warn future AIs not to resurrect them.
    "CLAUDE.md",
    "AGENTS.md",
    "docker-compose.yml",
    # Django migrations are part of the history chain — the CreateModel that
    # set up a now-dropped table and the DeleteModel that drops it both need
    # to reference the original class name to round-trip correctly.
    "backend/apps/suggestions/migrations/0030_metatournamentresult_holdoutquery.py",
    "backend/apps/suggestions/migrations/0034_drop_meta_tournament_tables.py",
    # The HITS pick #29 storage layer legitimately uses Kleinberg's canonical
    # output names ("authority" and "hub"). The banned tokens `hits_authority`
    # and `hits_hub` were deleted as **forward-declared duplicate signals** —
    # the implemented HITS algorithm still has to produce scores under those
    # names because that's what Kleinberg (1999) calls them.
    "backend/apps/pipeline/services/graph_signal_store.py",
)

# ── Directories never scanned (generated / vendored / cache).
SKIP_DIRS: tuple[str, ...] = (
    ".git",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "coverage-html",
    "staticfiles",
    ".venv",
    "venv",
    ".pytest_cache",
    ".benchmarks",
)

# ── File extensions we DO scan. Binary formats and huge generated files skipped.
SCAN_EXTENSIONS: tuple[str, ...] = (
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".html",
    ".scss",
    ".css",
    ".md",
    ".yml",
    ".yaml",
    ".json",
    ".txt",
    ".cpp",
    ".hpp",
    ".h",
    ".cc",
    ".sh",
    ".toml",
    ".ini",
    ".cfg",
)

# ── Files that, if encountered, we never scan regardless of extension
#     (lock files, huge generated schemas, etc.).
SKIP_FILE_BASENAMES: tuple[str, ...] = (
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "schema.yml",
    "openapi.json",
    "test_results.txt",
    "test_output.log",
)


def repo_root(start: Path | None = None) -> Path:
    """Locate the git repo root by walking up from *start* (or this file)."""
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / ".git").exists():
            return parent
    raise SystemExit("phantom-reference gate: cannot locate git repo root")


def load_banned_tokens(data_path: Path) -> list[tuple[str, re.Pattern[str]]]:
    """Read the deleted-tokens list and compile each entry as a word-boundary regex.

    One token per line; lines starting with # are comments.
    Matching uses \\b boundaries so short acronyms (e.g. `pmi`) do not produce
    false positives against unrelated words (`api_pmi_util`).
    """
    if not data_path.exists():
        print(
            f"phantom-reference gate: data file missing — {data_path}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    tokens: list[tuple[str, re.Pattern[str]]] = []
    for line in data_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pattern = re.compile(rf"\b{re.escape(stripped)}\b")
        tokens.append((stripped, pattern))
    if not tokens:
        print(
            f"phantom-reference gate: data file is empty — {data_path}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return tokens


def _is_allowed(rel_path: str) -> bool:
    """True when *rel_path* is on the explicit allow-list."""
    rel_norm = rel_path.replace("\\", "/")
    return any(rel_norm == allowed or rel_norm.startswith(allowed + "/") for allowed in ALLOWED_PATHS)


def _should_scan(rel_path: str, basename: str) -> bool:
    if basename in SKIP_FILE_BASENAMES:
        return False
    suffix = os.path.splitext(basename)[1].lower()
    if suffix not in SCAN_EXTENSIONS:
        return False
    # Skip allow-listed paths (they're the decision record).
    if _is_allowed(rel_path):
        return False
    return True


def scan_file(
    path: Path,
    tokens: list[tuple[str, re.Pattern[str]]],
) -> list[tuple[str, int, str]]:
    """Return every (token, line_number, line_text) hit in *path*."""
    hits: list[tuple[str, int, str]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line_no, line in enumerate(fh, start=1):
                for tok, pattern in tokens:
                    if pattern.search(line):
                        hits.append((tok, line_no, line.rstrip("\n")))
                        break  # one hit per line is enough to fail
    except OSError as exc:
        print(f"phantom-reference gate: cannot read {path} — {exc}", file=sys.stderr)
    return hits


def walk_repo(root: Path) -> list[Path]:
    """Yield every file under *root* that passes the scan filter."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place so os.walk doesn't descend.
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            if _should_scan(rel, name):
                out.append(full)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phantom-reference CI gate.")
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="Path to deleted_tokens.txt (defaults to <repo>/backend/scripts/deleted_tokens.txt).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root to scan (defaults to auto-detected).",
    )
    args = parser.parse_args(argv)

    root = (args.root or repo_root()).resolve()
    data = (args.data or root / "backend" / "scripts" / "deleted_tokens.txt").resolve()
    tokens = load_banned_tokens(data)

    total_hits = 0
    for path in walk_repo(root):
        hits = scan_file(path, tokens)
        if hits:
            rel = path.relative_to(root).as_posix()
            for tok, line_no, text in hits:
                print(f"{rel}:{line_no}: banned token '{tok}' — {text.strip()[:120]}")
                total_hits += 1

    if total_hits:
        print()
        print(
            f"phantom-reference gate: FAILED — {total_hits} banned token(s) found.",
            file=sys.stderr,
        )
        print(
            "Either remove the token, or (if keeping it is genuinely needed) "
            "add its path to ALLOWED_PATHS in check_phantom_references.py.",
            file=sys.stderr,
        )
        return 1

    print(f"phantom-reference gate: OK — scanned {len(tokens)} banned tokens, no phantoms.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
