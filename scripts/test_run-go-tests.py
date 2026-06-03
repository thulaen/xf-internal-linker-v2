from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "run-go-tests.sh"


def test_go_tests_has_sidecars_skeleton_baseline():
    text = SCRIPT.read_text()

    assert '*"/services/sidecars") echo "3" ;;' in text


def test_go_tests_has_startupd_service_baseline():
    text = SCRIPT.read_text()

    assert '*"/services/startupd") echo "70" ;;' in text
