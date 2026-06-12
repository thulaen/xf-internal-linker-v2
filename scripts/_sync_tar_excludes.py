"""Single source of truth for the tar ``--exclude`` recipe shared by every
source-snapshot syncer that feeds the Dell content-hash manifest.

Why this module exists: the identical 14-pattern exclude tuple was copy-pasted
into 5 Python files and 1 shell script. They MUST stay byte-identical — the Dell
side re-hashes the same bytes, so a drifted exclude list makes the manifest fail
(and, as the 2026-06-08 backend/backups incident showed, a *missing* exclude
ships hundreds of MB every run). Importing the one tuple from here makes drift
impossible.

Two ways to consume it:
    Python:  from _sync_tar_excludes import TAR_EXCLUDES
    Shell:   python3 scripts/_sync_tar_excludes.py   # prints one --exclude=... per line

The pattern ORDER is part of the content-hash contract. Do NOT reorder or edit
without updating every consumer in lockstep and re-baselining the manifests.
"""

# Patterns in their established order (no ``--exclude=`` prefix).
TAR_EXCLUDE_PATTERNS = (
    "__pycache__", "*.pyc",
    "build", ".pytest_cache",
    ".ruff_cache", "htmlcov", "backend/reports",
    "backend/backups", "backend/coverage-html",
    "backend/extensions/build", "backend/extensions/build_*",
    "backend/extensions/reports",
    "rust/target",
)

# The exact tuple the syncers pass to ``tar`` (byte-identical to the former
# inline ``_TAR_EXCLUDES`` literals).
TAR_EXCLUDES = tuple(f"--exclude={pattern}" for pattern in TAR_EXCLUDE_PATTERNS)


if __name__ == "__main__":
    # Emit one --exclude=... per line so a shell caller can read it into an array.
    print("\n".join(TAR_EXCLUDES))
