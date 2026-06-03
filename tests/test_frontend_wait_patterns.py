"""Static checks for bounded browser-test waits."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_playwright_tests_do_not_wait_for_networkidle() -> None:
    """Browser tests should wait for visible UI, not quiet network traffic."""

    hits: list[str] = []
    for path in sorted((REPO_ROOT / "frontend" / "tests").rglob("*.ts")):
        text = path.read_text(encoding="utf-8")
        if "waitForLoadState('networkidle')" in text or 'waitForLoadState("networkidle")' in text:
            hits.append(path.relative_to(REPO_ROOT).as_posix())

    assert hits == []
