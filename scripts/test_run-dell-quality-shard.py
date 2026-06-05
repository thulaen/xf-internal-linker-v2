"""TDD guard for scripts/run-dell-quality-shard.sh."""
from __future__ import annotations

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SCRIPT = SCRIPTS / "run-dell-quality-shard.sh"


def _text() -> str:
    return SCRIPT.read_text()


def test_dell_runner_file_exists():
    assert SCRIPT.exists(), "scripts/run-dell-quality-shard.sh must exist"


def test_dell_runner_reads_dell_megalinter_paths():
    t = _text()
    assert "dell_megalinter_paths" in t


def test_dell_runner_uses_docker_context_dell_for_megalinter():
    t = _text()
    assert "docker --context dell run --rm" in t
    assert "oxsecurity/megalinter:v8" in t


def test_dell_runner_backgrounds_language_and_megalinter_jobs():
    t = _text()
    assert "pids+=" in t
    assert 'for pid in "${pids[@]}"' in t


def test_dell_runner_replaces_stale_source_before_megalinter():
    t = _text()
    assert "rm -rf /repo/backend /repo/services /repo/scripts /repo/.githooks /repo/tools" in t
    assert "--exclude=backend/coverage-html" in t
    assert "--exclude=backend/extensions/build_tests" in t
    assert "--exclude=backend/reports" in t
