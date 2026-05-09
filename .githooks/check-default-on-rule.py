#!/usr/bin/env python3
"""Pre-commit check for the Default-On Rule.

Goal: keep every new feature ON by default with a non-zero starting
value, per `DEFAULT-ON-RULE.md` and the PARAMOUNT entry in `CLAUDE.md`.

What it does:
    - Scans staged migration files under `backend/apps/*/migrations/`.
    - Looks for `AppSetting` seeding patterns where the value is one of
      `"false"`, `"0"`, `"0.0"`, or `"off"` (case-insensitive).
    - Allows the seeding through ONLY if the migration's module-level
      docstring contains the magic exemption comment
      `# DEFAULT-ON-RULE: external-data-gated` plus a non-empty reason
      line below it.

How to override (legitimate cases only):
    Add to the migration's docstring:

        # DEFAULT-ON-RULE: external-data-gated
        # Reason: <one-line explanation of which external data this needs>

    The check looks for both the magic line AND a non-empty Reason line
    that follows.

Run manually:
    python .githooks/check-default-on-rule.py <migration_files...>

Run via the hook:
    Automatic on every commit (pre-commit step 9 in `.githooks/pre-commit`).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
META_TUNER_PATH = REPO_ROOT / "backend" / "apps" / "suggestions" / "services" / "meta_tuner.py"

# Match `AppSetting` writes inside migrations. Both spellings used by the
# project: direct calls (`AppSetting.objects.get_or_create(...)`) and
# `apps.get_model("core", "AppSetting").objects.<...>` inside RunPython.
APPSETTING_KEYWORD = re.compile(r"\bAppSetting\b")

# Match value strings we want to flag.
OFF_VALUES = re.compile(r'["\'](false|0|0\.0|off)["\']', re.IGNORECASE)
# Match numeric value strings (positive or negative, integer or float).
# Used to detect new tunable parameters that should be classified for
# the autotuner. Excludes the OFF_VALUES set above (those are blocked
# by the default-on rule, not the autotuner-tracking rule).
NUMERIC_VALUE = re.compile(r'^["\']-?\d+(?:\.\d+)?["\']$')

# Magic exemption comment that authors add to the migration's docstring
# when an off-default is legitimate (external-data-gated feature).
EXEMPTION_LINE = "# DEFAULT-ON-RULE: external-data-gated"
EXEMPTION_REASON_RE = re.compile(r"^\s*#\s*Reason\s*:\s*\S+", re.MULTILINE)
# Magic exemption for numeric keys that are not autotuner-tracked.
NOT_TUNABLE_LINE = re.compile(
    r"#\s*AUTOTUNER:\s*not-tunable\s*-\s*\S+", re.IGNORECASE
)


def is_migration_path(path: Path) -> bool:
    parts = path.as_posix().split("/")
    return (
        "migrations" in parts
        and len(parts) >= 4
        and parts[0] == "backend"
        and parts[-1].endswith(".py")
    )


def has_valid_exemption(source: str) -> bool:
    """True if the migration's module docstring carries the exemption.

    Two parts required:
        1. The magic line `# DEFAULT-ON-RULE: external-data-gated`
           somewhere in the file (case-sensitive — authors must type it
           exactly).
        2. A non-empty `# Reason: <something>` line elsewhere in the
           file. We don't enforce proximity — the file is short enough
           that scattered annotations are fine.
    """
    if EXEMPTION_LINE not in source:
        return False
    if not EXEMPTION_REASON_RE.search(source):
        return False
    return True


def find_off_seedings(source: str) -> list[tuple[int, str]]:
    """Return [(lineno, snippet), ...] for off-value AppSetting seedings.

    Heuristic: any line that mentions ``AppSetting`` AND contains an
    off-value literal. False positives are possible but cheap to triage
    — the checker errs on the side of false positives because the cost
    of a missed bug (a feature shipped silently off) is much higher than
    the cost of a one-line exemption comment.
    """
    findings: list[tuple[int, str]] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        if APPSETTING_KEYWORD.search(line) and OFF_VALUES.search(line):
            findings.append((lineno, line.strip()))
    # Also catch the common pattern where the value is on a *different*
    # line from the AppSetting reference — scan the whole file once for
    # off-value literals appearing inside a dict literal that's part of
    # an AppSetting call. We use AST for the dict-literal pass so we
    # don't hand-roll a Python parser.
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return findings  # let the regex pass speak; AST failure means
        # the file has bigger problems anyway and a separate linter will
        # flag them.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _calls_appsetting_method(node):
            continue
        for kw in node.keywords:
            if kw.arg != "defaults" or not isinstance(kw.value, ast.Dict):
                continue
            for k, v in zip(kw.value.keys, kw.value.values, strict=False):
                if (
                    isinstance(k, ast.Constant)
                    and k.value == "value"
                    and isinstance(v, ast.Constant)
                    and isinstance(v.value, str)
                    and OFF_VALUES.match(f'"{v.value}"')
                ):
                    findings.append(
                        (v.lineno, f'value="{v.value}" inside AppSetting defaults')
                    )
    # Deduplicate by lineno; the regex pass and AST pass may overlap.
    seen: set[int] = set()
    deduped: list[tuple[int, str]] = []
    for lineno, snippet in findings:
        if lineno in seen:
            continue
        seen.add(lineno)
        deduped.append((lineno, snippet))
    return deduped


def _calls_appsetting_method(node: ast.Call) -> bool:
    """True if the call looks like an AppSetting ORM write.

    Matches:
        AppSetting.objects.get_or_create(...)
        AppSetting.objects.update_or_create(...)
        apps.get_model("core", "AppSetting").objects.update_or_create(...)
    """
    func = node.func
    while isinstance(func, ast.Attribute):
        func = func.value
    if isinstance(func, ast.Name) and func.id == "AppSetting":
        return True
    if isinstance(func, ast.Call):
        # apps.get_model("core", "AppSetting") form
        inner = func.func
        if (
            isinstance(inner, ast.Attribute)
            and inner.attr == "get_model"
            and any(
                isinstance(arg, ast.Constant) and arg.value == "AppSetting"
                for arg in func.args
            )
        ):
            return True
    return False


def _read_meta_tuner_keys() -> tuple[set[str], set[str]]:
    """Return ``(tunable_keys, excluded_keys)`` from ``meta_tuner.py``.

    Used to verify that any new numeric AppSetting key introduced by a
    migration is classified for the autotuner — either tunable (with
    bounds) or explicitly excluded. Returns ``(set(), set())`` if the
    meta_tuner module can't be parsed; the caller treats that as
    "no tracking info available, skip the warning."
    """
    if not META_TUNER_PATH.exists():
        return set(), set()
    try:
        source = META_TUNER_PATH.read_text(encoding="utf-8")
    except OSError:
        return set(), set()
    tunable: set[str] = set()
    excluded: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set(), set()

    def _collect_dict_keys(value: ast.AST, into: set[str]) -> None:
        if not isinstance(value, ast.Dict):
            return
        for k in value.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                into.add(k.value)

    for node in ast.walk(tree):
        # ``_META_PARAM_BOUNDS: dict[str, tuple[float, float]] = {...}``
        # is an ``AnnAssign`` (annotated). Plain ``X = {...}`` is
        # ``Assign``. Handle both — agents may use either form.
        target_names: list[str] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]
            value = node.value
        else:
            continue
        if value is None:
            continue
        if "_META_PARAM_BOUNDS" in target_names:
            _collect_dict_keys(value, tunable)
        elif "_AUTOTUNER_EXCLUDED" in target_names:
            _collect_dict_keys(value, excluded)
    return tunable, excluded


def find_unclassified_numerics(source: str) -> list[tuple[int, str]]:
    """Return [(lineno, key), ...] for numeric AppSetting seedings whose
    keys are NOT classified in meta_tuner.py.

    Heuristic: scan AppSetting AST writes; for each ``defaults={"value": <numeric>}``
    pair, also look at the ``key=`` argument in the same call. If that
    key is missing from both ``_META_PARAM_BOUNDS`` and
    ``_AUTOTUNER_EXCLUDED`` AND the migration doesn't carry the
    ``# AUTOTUNER: not-tunable`` exemption, surface it as a warning.
    Returns an empty list when meta_tuner.py is missing.
    """
    tunable, excluded = _read_meta_tuner_keys()
    if not tunable and not excluded:
        # meta_tuner.py is absent or empty — can't classify anything.
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _calls_appsetting_method(node):
            continue
        # Find the key= and defaults= keyword args.
        key_arg: str | None = None
        defaults_arg: ast.Dict | None = None
        for kw in node.keywords:
            if kw.arg == "key" and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, str):
                    key_arg = kw.value.value
            elif kw.arg == "defaults" and isinstance(kw.value, ast.Dict):
                defaults_arg = kw.value
        # Some migrations build the key from a row dict (NEW_VALUES /
        # SPAM_GUARD_ROWS). When `key=row["key"]` we can't statically
        # resolve the key — skip those rather than emit false positives.
        if key_arg is None or defaults_arg is None:
            continue
        if key_arg in tunable or key_arg in excluded:
            continue
        # Walk the defaults dict for a numeric "value".
        for k, v in zip(defaults_arg.keys, defaults_arg.values, strict=False):
            if (
                isinstance(k, ast.Constant)
                and k.value == "value"
                and isinstance(v, ast.Constant)
                and isinstance(v.value, str)
                and NUMERIC_VALUE.match(f'"{v.value}"')
                # Off-values are blocked by the other check; don't
                # double-warn here.
                and not OFF_VALUES.match(f'"{v.value}"')
            ):
                findings.append((v.lineno, key_arg))
    return findings


def check_file(path: Path) -> list[str]:
    """Return blocking errors for one migration file.

    Two classes of blocking error:
      1. Off-by-default seedings (``false`` / ``0`` / ``0.0`` / ``off``)
         without the ``# DEFAULT-ON-RULE: external-data-gated`` + Reason
         exemption.
      2. Numeric AppSetting keys not classified for the autotuner —
         neither in ``_META_PARAM_BOUNDS`` nor ``_AUTOTUNER_EXCLUDED``
         (in ``meta_tuner.py``), and the migration doesn't carry the
         ``# AUTOTUNER: not-tunable - <reason>`` exemption.

    Both rules can be suppressed with a clear, intent-bearing comment
    in the migration's docstring; neither has a silent-bypass.
    """
    if not is_migration_path(path):
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path}: cannot read file ({exc})"]

    errors: list[str] = []

    # Rule 1 — off-by-default values.
    findings = find_off_seedings(source)
    if findings and not has_valid_exemption(source):
        for lineno, snippet in findings:
            errors.append(
                f"{path}:{lineno}: seeds AppSetting with off-value but no "
                f"`# DEFAULT-ON-RULE: external-data-gated` exemption + Reason "
                f"line in the docstring.\n    {snippet}"
            )

    # Rule 2 — autotuner classification.
    if not NOT_TUNABLE_LINE.search(source):
        for lineno, key in find_unclassified_numerics(source):
            errors.append(
                f"{path}:{lineno}: seeds numeric AppSetting key {key!r} that "
                f"isn't in `_META_PARAM_BOUNDS` or `_AUTOTUNER_EXCLUDED` "
                f"(meta_tuner.py). Classify it for the autotuner, or add "
                f"`# AUTOTUNER: not-tunable - <reason>` to the migration "
                f"docstring to suppress this check."
            )
    return errors


def main(argv: list[str]) -> int:
    if not argv:
        return 0
    all_errors: list[str] = []
    for arg in argv:
        all_errors.extend(check_file(Path(arg)))
    if not all_errors:
        return 0
    sys.stderr.write(
        "\n[default-on-rule] BLOCKED — see DEFAULT-ON-RULE.md for the rule.\n\n"
    )
    for err in all_errors:
        sys.stderr.write(f"  {err}\n\n")
    sys.stderr.write(
        "Suppress hints (use only when the exception genuinely applies):\n\n"
        "  Off-by-default value:\n"
        "    # DEFAULT-ON-RULE: external-data-gated\n"
        "    # Reason: <one-line description of which external data is needed>\n\n"
        "  Numeric AppSetting that isn't meaningfully tunable:\n"
        "    # AUTOTUNER: not-tunable - <one-line reason, e.g. 'fixed timeout, "
        "operator-set ceiling'>\n\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
