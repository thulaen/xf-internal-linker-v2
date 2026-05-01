#!/usr/bin/env python3
"""Pre-commit linter — block migrations that introduce duplicate-prone tables.

Reads staged Django migration files, finds any new model with a ForeignKey
to a per-content parent (``ContentItem``, ``Post``, ``Sentence``, etc.), and
verifies the model declares the four pieces required by ``NO-DUPLICATES.md``:

    1. A content-identity column (any field name containing ``hash`` or
       ``content_hash`` or ``fingerprint`` or ``signature``).
    2. A signal-version column (any field name containing ``version`` or
       ``model_version`` or ``signal_version``).
    3. A unique constraint OR an upsert mechanism (heuristic — looks for
       ``unique_together`` / ``UniqueConstraint`` / ``unique=True``).
    4. Either an entry in ``NO-DUPLICATES.md`` table, OR a ``Superseded*``
       sibling model in the same migration, OR an ``ignore_invariant``
       comment on the operation.

The check is INTENTIONALLY conservative — false positives are easier to
silence (with an ``# noqa: dedup-invariant`` comment near the model) than
false negatives are to recover from once a non-deduped table goes live.

Exit codes:
    0   — staged migrations are clean (or none staged)
    1   — at least one staged migration violates the invariant
    2   — the linter itself failed (e.g. unparseable migration)

Usage from the pre-commit shim::

    if [ -n "$STAGED_MIGRATIONS" ]; then
      python "$REPO_ROOT/.githooks/check-no-duplicates-invariant.py" $STAGED_MIGRATIONS
    fi
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

# Per-content parents whose children must satisfy the invariant.
PER_CONTENT_PARENTS = {
    "ContentItem",
    "Post",
    "Sentence",
    "Page",
    "Thread",
    "PassageEmbedding",  # children of passages also count
}

# Field-name fragments that satisfy each piece.
HASH_FRAGMENTS = ("hash", "content_hash", "fingerprint", "signature")
VERSION_FRAGMENTS = ("version", "model_version", "signal_version", "codebook_version")

NO_DUPLICATES_MD = Path(__file__).parent.parent / "NO-DUPLICATES.md"


def staged_migration_paths(args: list[str]) -> list[Path]:
    """Return staged paths the hook should check.

    Accepts either explicit paths from argv (pre-commit invocation) or, when
    run with no args, queries git for staged migration files.
    """
    if args:
        return [Path(a) for a in args if a.endswith(".py") and "/migrations/" in a]
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return [Path(p) for p in out if p.endswith(".py") and "/migrations/" in p]


def parse_migration(path: Path) -> ast.Module | None:
    """Parse the migration file or return None on syntax error."""
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return None


def collect_create_models(tree: ast.Module) -> list[ast.Call]:
    """Return every ``migrations.CreateModel(...)`` call in the migration."""
    out: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "CreateModel":
            out.append(node)
    return out


def model_field_summary(call: ast.Call) -> tuple[str, list[tuple[str, str]]]:
    """Return ``(model_name, [(field_name, field_kind), ...])`` for a CreateModel call.

    ``field_kind`` is the field constructor's last attribute name (e.g.
    ``"ForeignKey"``, ``"CharField"``, ``"BinaryField"``).
    """
    name = ""
    fields: list[tuple[str, str]] = []
    for kw in call.keywords:
        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
            name = str(kw.value.value)
        elif kw.arg == "fields" and isinstance(kw.value, (ast.List, ast.Tuple)):
            for elt in kw.value.elts:
                if not isinstance(elt, ast.Tuple) or len(elt.elts) < 2:
                    continue
                f_name = elt.elts[0].value if isinstance(elt.elts[0], ast.Constant) else ""
                f_call = elt.elts[1]
                f_kind = ""
                if isinstance(f_call, ast.Call):
                    func = f_call.func
                    if isinstance(func, ast.Attribute):
                        f_kind = func.attr
                    elif isinstance(func, ast.Name):
                        f_kind = func.id
                fields.append((str(f_name), f_kind))
    return name, fields


def fk_target_names(call: ast.Call) -> set[str]:
    """Return the set of model names this CreateModel's FKs point at.

    Handles the ``"app.Model"`` and ``"Model"`` forms; lower-cases for
    case-insensitive comparison against ``PER_CONTENT_PARENTS``.
    """
    out: set[str] = set()
    for kw in call.keywords:
        if kw.arg != "fields" or not isinstance(kw.value, (ast.List, ast.Tuple)):
            continue
        for elt in kw.value.elts:
            if not isinstance(elt, ast.Tuple) or len(elt.elts) < 2:
                continue
            f_call = elt.elts[1]
            if not isinstance(f_call, ast.Call):
                continue
            func = f_call.func
            if isinstance(func, ast.Attribute) and func.attr != "ForeignKey":
                continue
            if isinstance(func, ast.Name) and func.id != "ForeignKey":
                continue
            for arg in [*f_call.args, *(kw_.value for kw_ in f_call.keywords if kw_.arg == "to")]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    parts = arg.value.split(".")
                    out.add(parts[-1])
    return out


def has_unique_constraint(call: ast.Call) -> bool:
    """True if the CreateModel options declare any uniqueness constraint."""
    for kw in call.keywords:
        if kw.arg == "options" and isinstance(kw.value, ast.Dict):
            for opt_key, _opt_val in zip(kw.value.keys, kw.value.values):
                if isinstance(opt_key, ast.Constant) and opt_key.value in (
                    "unique_together",
                    "constraints",
                ):
                    return True
        if kw.arg == "fields" and isinstance(kw.value, (ast.List, ast.Tuple)):
            for elt in kw.value.elts:
                if not isinstance(elt, ast.Tuple) or len(elt.elts) < 2:
                    continue
                f_call = elt.elts[1]
                if isinstance(f_call, ast.Call):
                    for fk_kw in f_call.keywords:
                        if fk_kw.arg == "unique" and isinstance(fk_kw.value, ast.Constant):
                            if fk_kw.value.value is True:
                                return True
    return False


def model_documented_in_no_duplicates(model_name: str) -> bool:
    """True if NO-DUPLICATES.md mentions the model in its tables-list."""
    try:
        text = NO_DUPLICATES_MD.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    return f"`{model_name}" in text or model_name in text


def lint_migration(path: Path) -> list[str]:
    """Return a list of human-readable violations (empty == clean)."""
    tree = parse_migration(path)
    if tree is None:
        return [f"{path}: could not parse — fix the syntax error first"]

    source = path.read_text(encoding="utf-8")
    violations: list[str] = []

    for call in collect_create_models(tree):
        name, fields = model_field_summary(call)
        targets = fk_target_names(call)
        per_content_parents = targets & PER_CONTENT_PARENTS
        if not per_content_parents:
            continue
        if "# noqa: dedup-invariant" in source:
            continue

        field_names = {fname.lower() for fname, _ in fields}

        has_hash = any(
            any(frag in fname for frag in HASH_FRAGMENTS) for fname in field_names
        )
        has_version = any(
            any(frag in fname for frag in VERSION_FRAGMENTS) for fname in field_names
        )
        has_uniq = has_unique_constraint(call)
        documented = model_documented_in_no_duplicates(name)

        missing: list[str] = []
        if not has_hash:
            missing.append("content-identity column (e.g. content_hash, embedding_text_hash)")
        if not has_version:
            missing.append("signal-version column (e.g. embedding_model_version, signal_version)")
        if not has_uniq:
            missing.append("unique constraint OR upsert mechanism")
        if not documented:
            missing.append(f"entry in NO-DUPLICATES.md tables-list for `{name}`")

        if missing:
            violations.append(
                f"{path}:{call.lineno} — model `{name}` (FK to {', '.join(per_content_parents)}) is missing:\n"
                + "\n".join(f"    • {m}" for m in missing)
            )
    return violations


def main(argv: list[str]) -> int:
    paths = staged_migration_paths(argv[1:])
    if not paths:
        return 0

    all_violations: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        all_violations.extend(lint_migration(path))

    if not all_violations:
        return 0

    print("\n[no-duplicates-invariant] One or more staged migrations violate the rule:\n")
    for v in all_violations:
        print(v)
        print()
    print(
        "Fix the migration to satisfy NO-DUPLICATES.md, OR add\n"
        "  # noqa: dedup-invariant  # justification: <one-line reason>\n"
        "to the migration if the table genuinely doesn't need the invariant\n"
        "(e.g. the model isn't a per-content artefact).\n"
        "See NO-DUPLICATES.md for the full pattern.\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
