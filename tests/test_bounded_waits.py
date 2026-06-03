"""Static checks that repo-owned command waits stay bounded."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FILES_REQUIRING_SUBPROCESS_TIMEOUTS = (
    Path("scripts/run_quality_step.py"),
    Path("scripts/commit_scope.py"),
    Path("scripts/check_quality_policy.py"),
    Path("scripts/ensure_compiled_artifacts.py"),
)


def _subprocess_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        value = func.value
        if isinstance(value, ast.Name) and value.id == "subprocess":
            if func.attr in {"run", "check_output", "check_call", "Popen"}:
                yield node


def test_selected_repo_subprocess_calls_have_timeout_keyword() -> None:
    """Scripts that wrap external commands must set a timeout on every call."""

    missing: list[str] = []
    for relative in FILES_REQUIRING_SUBPROCESS_TIMEOUTS:
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(relative))
        for call in _subprocess_calls(tree):
            if not any(keyword.arg == "timeout" for keyword in call.keywords):
                missing.append(f"{relative}:{call.lineno}")

    assert missing == []
