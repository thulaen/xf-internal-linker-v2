#!/usr/bin/env python3
"""Rule H.H10 — run `python manage.py check --deploy` for production safety.

File-scoped: only fires when settings, ASGI/WSGI config, or production
URL routing changes. Shells out to the Kubernetes backend command which
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
    result = _run_deploy_check()
    if result == "missing":
        return _fail_missing_helper()
    if result == "timeout":
        return _fail_timeout()
    if result.returncode != 0:
        return _fail_deploy_warnings(result)
    return 0


def _deploy_check_command() -> list[str]:
    return [
        sys.executable, str(REPO_ROOT / "scripts" / "backend_manage.py"),
        "--env", "DJANGO_SETTINGS_MODULE=config.settings.production",
        "--env", "DJANGO_SECRET_KEY=deploy-check-secret-key-with-more-than-fifty-unique-characters-2026",
        "--env", "DJANGO_SECURE_SSL_REDIRECT=1",
        "--env", "DJANGO_SECURE_HSTS_SECONDS=1",
        "--env", "DJANGO_SESSION_COOKIE_SECURE=1",
        "--env", "DJANGO_CSRF_COOKIE_SECURE=1",
        "--",
        "check", "--deploy",
        "--tag", "security",
        "--fail-level", "WARNING",
    ]


def _run_deploy_check() -> subprocess.CompletedProcess[str] | str:
    try:
        return subprocess.run(
            _deploy_check_command(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except FileNotFoundError:
        return "missing"
    except subprocess.TimeoutExpired:
        return "timeout"


def _fail_missing_helper() -> int:
    sys.stderr.write(
        "FAIL check-django-deploy: backend command helper is missing.\n"
        "WHY: Rule H.H10 runs `python manage.py check --deploy` inside "
        "the Kubernetes backend pod to audit HTTPS, HSTS, CSRF, "
        "SECURE_BROWSER_XSS_FILTER, and related production safety "
        "settings. Skipping this check could ship an insecure config.\n"
        "UNBLOCK: restore scripts/backend_manage.py and cluster access, then "
        "re-attempt the commit.\n"
    )
    return 2


def _fail_timeout() -> int:
    sys.stderr.write(
        "FAIL check-django-deploy: command timed out after 60s.\n"
        "WHY: The Kubernetes backend pod may be unhealthy or starting.\n"
        "UNBLOCK: Wait for `kubectl -n xf-app get pods -l app=backend` "
        "to show the backend pod Ready, "
        "then re-attempt.\n"
    )
    return 2


def _fail_deploy_warnings(result: subprocess.CompletedProcess[str]) -> int:
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
        "  python scripts/backend_manage.py "
        "report_hook_false_positive --hook check-django-deploy "
        "--context \"<explanation>\"\n"
        f"\nDjango output:\n{result.stdout}\n{result.stderr}\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
