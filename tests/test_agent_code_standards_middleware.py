"""Tests for host-owned code-standards invocation middleware."""

import json
from pathlib import Path

from apps.governance.agent_middleware.code_standards import (
    CODE_STANDARDS_CONSTRAINTS,
    DEFAULT_LUA_VALIDATOR,
    _LUA_DRIVER,
    ValidationResult,
    build_retry_instruction,
    inject_code_standards,
    prompt_is_code_related,
    validate_response_with_lua,
)


def test_code_prompt_gets_constraints_once():
    prompt = "Please write a Python function for scoring."
    first = inject_code_standards("Base system.", prompt)
    second = inject_code_standards(first.system_prompt, prompt)

    assert first.code_related is True
    assert CODE_STANDARDS_CONSTRAINTS in first.system_prompt
    assert second.system_prompt.count(CODE_STANDARDS_CONSTRAINTS) == 1


def test_non_code_prompt_stays_unchanged():
    result = inject_code_standards("Base system.", "Summarize today's status.")

    assert result.code_related is False
    assert result.system_prompt == "Base system."


def test_prompt_detector_catches_paths_and_fenced_code():
    assert prompt_is_code_related("Edit backend/apps/foo.py")
    assert prompt_is_code_related("```python\nassert True\n```")


def test_default_lua_validator_points_to_hot_reloadable_script():
    assert DEFAULT_LUA_VALIDATOR.exists()
    assert DEFAULT_LUA_VALIDATOR.name == "validate_code_standards.lua"


def test_lua_validation_result_is_normalized_from_runner_output(tmp_path):
    script = tmp_path / "validate_code_standards.lua"
    script.write_text("return {}", encoding="utf-8")

    def runner(_script: Path, response_text: str) -> str:
        assert "def build()" in response_text
        return json.dumps({"valid": False, "reasons": ["You did not write tests first."]})

    result = validate_response_with_lua("def build(): pass", script_path=script, runner=runner)

    assert result == ValidationResult(
        valid=False,
        reasons=("You did not write tests first.",),
    )


def test_invalid_validation_builds_host_owned_retry_instruction():
    result = ValidationResult(valid=False, reasons=("You did not write tests first.",))

    assert build_retry_instruction(result) == (
        "Validation failed: You did not write tests first. Try again."
    )


def test_lua_driver_does_not_use_forbidden_direct_lua_io_or_loadfile():
    assert "io.read" not in _LUA_DRIVER
    assert "loadfile" not in _LUA_DRIVER
