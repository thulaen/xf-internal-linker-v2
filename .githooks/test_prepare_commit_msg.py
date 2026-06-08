"""Tests for the prepare-commit-msg findings footer hook."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


HOOK = Path(".githooks/prepare-commit-msg")


def _msys_path(path: Path) -> str:
    text = path.resolve().as_posix()
    if len(text) >= 3 and text[1:3] == ":/":
        return f"/{text[0].lower()}{text[2:]}"
    return text


def _bash_executable() -> str:
    for path in (
        os.environ.get("GIT_BASH"),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        shutil.which("bash"),
    ):
        if path and Path(path).exists():
            return path
    return "bash"


def _run_hook(message_file: Path, transcript: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "XF_FINDINGS_TRANSCRIPT": _msys_path(transcript)}
    return subprocess.run(
        [_bash_executable(), HOOK.as_posix(), _msys_path(message_file), "message"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


def test_appends_footer_when_transcript_has_findings(tmp_path: Path) -> None:
    message_file = tmp_path / "COMMIT_EDITMSG"
    transcript = tmp_path / "findings.txt"
    message_file.write_text("Fix hook transcript\n\nBody stays here.\n", encoding="utf-8")
    transcript.write_text("1234\n1235\n1236\n1237\n1238\n", encoding="utf-8")

    result = _run_hook(message_file, transcript)

    assert result.returncode == 0
    assert (
        "[FINDINGS FILED: 5 AutoIssues created — #1234, #1235, #1236, #1237, #1238]"
        in message_file.read_text(encoding="utf-8")
    )


def test_no_footer_when_zero_findings(tmp_path: Path) -> None:
    message_file = tmp_path / "COMMIT_EDITMSG"
    transcript = tmp_path / "findings.txt"
    original = "Clean commit\n\nNo findings.\n"
    message_file.write_text(original, encoding="utf-8")
    transcript.write_text("", encoding="utf-8")

    result = _run_hook(message_file, transcript)

    assert result.returncode == 0
    assert message_file.read_text(encoding="utf-8") == original


def test_preserves_user_body_above_footer(tmp_path: Path) -> None:
    message_file = tmp_path / "COMMIT_EDITMSG"
    transcript = tmp_path / "findings.txt"
    original = "Subject\n\nUser typed body.\n"
    message_file.write_text(original, encoding="utf-8")
    transcript.write_text("#42\n", encoding="utf-8")

    result = _run_hook(message_file, transcript)

    assert result.returncode == 0
    assert message_file.read_text(encoding="utf-8").startswith(original)


def test_removes_transcript_after_consuming(tmp_path: Path) -> None:
    message_file = tmp_path / "COMMIT_EDITMSG"
    transcript = tmp_path / "findings.txt"
    message_file.write_text("Subject\n", encoding="utf-8")
    transcript.write_text("42\n43\n", encoding="utf-8")

    result = _run_hook(message_file, transcript)

    assert result.returncode == 0
    assert not transcript.exists()


def test_handles_missing_transcript_silently(tmp_path: Path) -> None:
    message_file = tmp_path / "COMMIT_EDITMSG"
    transcript = tmp_path / "missing.txt"
    original = "Subject\n\nBody.\n"
    message_file.write_text(original, encoding="utf-8")

    result = _run_hook(message_file, transcript)

    assert result.returncode == 0
    assert result.stderr == ""
    assert message_file.read_text(encoding="utf-8") == original
