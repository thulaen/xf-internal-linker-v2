#!/usr/bin/env python3
"""Rule H.H10 — run `python manage.py check --deploy` for production safety.

File-scoped: only fires when settings, ASGI/WSGI config, or production
URL routing changes. Shells out to the existing Django command which
audits HTTPS, HSTS, CSRF, SECURE_BROWSER_XSS_FILTER, etc.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_TRIGGER_PATHS = (
    "backend/config/settings/",
    "backend/config/asgi.py",
    "backend/config/wsgi.py",
    "backend/config/urls.py",
)
_IGNORED_TRIGGER_PATHS = {
    "backend/config/settings/test.py",
}


def _staged_relevant() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            timeout=10, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    files: list[str] = []
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        if line in _IGNORED_TRIGGER_PATHS:
            continue
        if any(line.startswith(p) or line == p for p in _TRIGGER_PATHS):
            files.append(line)
    return files


def main() -> int:
    relevant = _staged_relevant()
    if not relevant:
        return 0
    cmd = [
        "docker", "compose", "exec", "-T",
        "-e", "DJANGO_SETTINGS_MODULE=config.settings.production",
        "-e", "DJANGO_SECRET_KEY=deploy-check-secret-key-with-more-than-fifty-unique-characters-2026",
        "-e", "DJANGO_SECURE_SSL_REDIRECT=1",
        "-e", "DJANGO_SESSION_COOKIE_SECURE=1",
        "-e", "DJANGO_CSRF_COOKIE_SECURE=1",
        "backend",
        "python", "manage.py", "check", "--deploy",
        "--tag", "security",
        "--fail-level", "WARNING",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
            encoding="utf-8",
            errors="replace",
                                timeout=60, check=False)
    except FileNotFoundError:
        sys.stderr.write(
            "FAIL check-django-deploy: docker not on PATH.\n"
            "WHY: Rule H.H10 runs `python manage.py check --deploy` inside "
            "the backend container to audit HTTPS, HSTS, CSRF, "
            "SECURE_BROWSER_XSS_FILTER, and related production safety "
            "settings. Skipping this check could ship an insecure config.\n"
            "UNBLOCK: Start Docker Desktop and the backend container, then "
            "re-attempt the commit.\n"
        )
        return 2
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "FAIL check-django-deploy: command timed out after 60s.\n"
            "WHY: The backend container may be unhealthy or starting.\n"
            "UNBLOCK: Wait for `docker compose ps` to show backend healthy, "
            "then re-attempt.\n"
        )
        return 2
    if result.returncode != 0:
        sys.stderr.write(
            "FAIL check-django-deploy: `manage.py check --deploy` reported "
            "production-safety issues.\n"
            "WHY: Rule H.H10 blocks commits that introduce or fail to "
            "address production-config concerns (SECURE_SSL_REDIRECT, "
            "SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE, X_FRAME_OPTIONS, "
            "etc.). Settings or urls files were touched, so the deploy "
            "check must be green.\n"
            "UNBLOCK: Read the warnings in the command's output below; fix "
            "the named settings in `backend/config/settings/base.py` (or "
            "the per-environment file), then re-commit. If a warning is a "
            "false positive (e.g. ALLOWED_HOSTS warning in a deliberately-"
            "open dev setup), file:\n"
            "  docker compose exec -T backend python manage.py "
            "report_hook_false_positive --hook check-django-deploy "
            "--context \"<explanation>\"\n"
            f"\nDjango output:\n{result.stdout}\n{result.stderr}\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
