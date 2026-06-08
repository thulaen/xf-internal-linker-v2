# CodeQL Local Security Scan

Last updated: 2026-06-07.

CodeQL is GitHub's security scanner. It reads source code, creates one database per programming language, and writes results as SARIF, which is a standard JSON report format for security tools.

## What Gets Scanned

The repo detects supported languages before every scan. The backend is Python + Rust only (see [ADR 0007](../adr/0007-python-rust-two-language.md)); C/C++ and Go were removed on 2026-06-06. Today it scans:

1. Python.
2. Rust.
3. JavaScript/TypeScript (the Angular frontend).

A language is included only when tracked source files for it exist. PostgreSQL/SQL files are not scanned because this CodeQL setup does not support them for this project.

## Install CodeQL on Windows

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-codeql.ps1 -AddToUserPath
```

Close and reopen the terminal, then check:

```powershell
codeql --version
```

## Run Before Merge

Run all detected languages:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-codeql-local.ps1
```

Run one language:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-codeql-local.ps1 -Language python
```

The local command writes:

- databases under `tmp/codeql/databases/<language>`;
- reports under `reports/codeql/<language>.sarif`.

## Import Findings Into AutoIssues

After a local scan, import one SARIF file:

```powershell
docker compose exec -T backend python manage.py ingest_codeql_sarif --language python --path /repo/reports/codeql/python.sarif --max-open 10
```

Then verify:

```powershell
docker compose exec -T backend python manage.py verify_codeql_autoissues --max-open 10 --block-open
```

If any CodeQL-backed AutoIssue is still open, commits stop until the issue is fixed or reviewed through the normal AutoIssue process.

The importer does not save full CodeQL evidence as plain text. It saves one deduped `CodeQLFindingEvidence` row per finding, and that row stores the full evidence as LZ4-compressed bytes. LZ4 is a fast lossless compression format, which means the data can be restored exactly later while taking less database space. If the same CodeQL finding appears again, the existing compressed row is updated instead of creating a clone.

## Resource Limits

Defaults:

- `CODEQL_THREADS=2`
- `CODEQL_RAM_MB=6144`
- `CODEQL_BUILD_JOBS=2`

Raise these only when the machine has enough free memory and disk space.

## Build Commands

All scanned languages use CodeQL build-free mode. Python, Rust, and JavaScript/TypeScript need no manual build step before analysis, so there are no per-language CodeQL build scripts.
