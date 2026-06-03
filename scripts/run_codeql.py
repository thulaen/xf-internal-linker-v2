"""Run one CodeQL database and SARIF analysis per detected language."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from codeql_language_inventory import build_mode_for_language, detect_languages

QUERY_SUITES = {
    "c-cpp": "codeql/cpp-queries:codeql-suites/cpp-security-and-quality.qls",
    "go": "codeql/go-queries:codeql-suites/go-security-and-quality.qls",
    "rust": "codeql/rust-queries:codeql-suites/rust-code-scanning.qls",
    "python": "codeql/python-queries:codeql-suites/python-security-and-quality.qls",
    "javascript-typescript": "codeql/javascript-queries:codeql-suites/javascript-security-and-quality.qls",
}

CLI_LANGUAGES = {
    "c-cpp": "cpp",
    "javascript-typescript": "javascript",
}

BUILD_COMMANDS = {
    "c-cpp": "bash scripts/codeql-build-cpp.sh",
    "go": "bash scripts/codeql-build-go.sh",
}


def _run(command: list[str], *, dry_run: bool) -> None:
    print("+ " + " ".join(command))
    if not dry_run:
        subprocess.run(command, check=True)


def _database_create_args(
    codeql: str,
    language: str,
    db_path: Path,
    threads: str,
    ram: str,
) -> list[str]:
    args = [
        codeql,
        "database",
        "create",
        str(db_path),
        f"--language={CLI_LANGUAGES.get(language, language)}",
        "--source-root=.",
        "--codescanning-config=.github/codeql/codeql-config.yml",
        f"--threads={threads}",
        f"--ram={ram}",
    ]
    if build_mode_for_language(language) == "manual":
        args.append(f"--command={BUILD_COMMANDS[language]}")
    elif language != "rust":
        args.append("--build-mode=none")
    return args


def _analyze_args(codeql: str, language: str, db_path: Path, sarif: Path, threads: str, ram: str) -> list[str]:
    return [
        codeql,
        "database",
        "analyze",
        str(db_path),
        QUERY_SUITES[language],
        "--format=sarifv2.1.0",
        f"--output={sarif}",
        f"--threads={threads}",
        f"--ram={ram}",
    ]


def _selected_languages(requested: list[str]) -> list[str]:
    detected = detect_languages().languages
    if requested:
        return [language for language in detected if language in set(requested)]
    return detected


def run_codeql(args: argparse.Namespace) -> None:
    languages = _selected_languages(args.language)
    args.db_root.mkdir(parents=True, exist_ok=True)
    args.sarif_root.mkdir(parents=True, exist_ok=True)
    for language in languages:
        db_path = args.db_root / language
        sarif = args.sarif_root / f"{language}.sarif"
        if db_path.exists() and not args.dry_run:
            shutil.rmtree(db_path)
        create = _database_create_args(args.codeql, language, db_path, args.threads, args.ram)
        analyze = _analyze_args(args.codeql, language, db_path, sarif, args.threads, args.ram)
        _run(create, dry_run=args.dry_run)
        _run(analyze, dry_run=args.dry_run)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codeql", default=os.environ.get("CODEQL", "codeql"))
    parser.add_argument("--db-root", type=Path, default=Path("tmp/codeql/databases"))
    parser.add_argument("--sarif-root", type=Path, default=Path("reports/codeql"))
    parser.add_argument("--threads", default=os.environ.get("CODEQL_THREADS", "2"))
    parser.add_argument("--ram", default=os.environ.get("CODEQL_RAM_MB", "6144"))
    parser.add_argument("--language", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    run_codeql(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
