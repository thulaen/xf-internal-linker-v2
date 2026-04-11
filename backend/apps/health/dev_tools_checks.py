"""
Dev Tools Health Checkers
=========================
Registers health checks for software engineering tools under the "Dev Tools"
category on the /health page.

Each checker answers one plain-English question:
  "Is this tool set up so AI agents can work safely in this area?"

Path resolution:
  _BACKEND_DIR  → /app            (backend/ directory, always mounted in Docker)
  _REPO_ROOT    → REPO_ROOT env   (repo root, mounted read-only as /repo)
                → BASE_DIR.parent (repo root when running locally without Docker)

No checker should raise an unhandled exception — they always return a
ServiceHealthResult so the registry can continue running the other checks.
"""

import os
import logging
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import ServiceHealthRecord
from .services import HealthCheckRegistry, ServiceHealthResult

logger = logging.getLogger(__name__)

# ── Path resolution ───────────────────────────────────────────────────────────

_BACKEND_DIR: Path = settings.BASE_DIR

# REPO_ROOT env var is set by docker-compose (REPO_ROOT=/repo).
# Falls back to BASE_DIR.parent when running locally without Docker.
_REPO_ROOT: Path = Path(os.environ.get("REPO_ROOT", str(settings.BASE_DIR.parent)))


def _repo(*parts: str) -> Path:
    """Return a path relative to the repo root."""
    return _REPO_ROOT.joinpath(*parts)


def _backend(*parts: str) -> Path:
    """Return a path relative to the backend/ directory."""
    return _BACKEND_DIR.joinpath(*parts)


def _file_contains(path: Path, text: str) -> bool:
    """Return True if path exists and its text contains the given string."""
    try:
        return path.exists() and text in path.read_text(encoding="utf-8")
    except OSError:
        return False


# ── EditorConfig ──────────────────────────────────────────────────────────────


@HealthCheckRegistry.register(
    "dev_tools.editorconfig",
    name="EditorConfig",
    description="Ensures all AI agents use the same whitespace and line-ending rules.",
)
def check_editorconfig() -> ServiceHealthResult:
    if _repo(".editorconfig").exists():
        return ServiceHealthResult(
            service_key="dev_tools.editorconfig",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="EditorConfig is present.",
            issue_description="All AI agents use the same spacing and line endings. No inconsistent whitespace in diffs.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
        )
    return ServiceHealthResult(
        service_key="dev_tools.editorconfig",
        status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
        status_label="EditorConfig file is missing.",
        issue_description=(
            "Your repo has no .editorconfig file. Different AI agents (Claude, Codex, Copilot) "
            "produce slightly different whitespace, which makes diffs messy and hard to review."
        ),
        suggested_fix="Ask your AI agent to create a .editorconfig file in the repo root. Takes about five minutes.",
    )


# ── Prettier ──────────────────────────────────────────────────────────────────


@HealthCheckRegistry.register(
    "dev_tools.prettier",
    name="Prettier (Angular formatter)",
    description="Auto-formats all TypeScript, HTML, and SCSS so agents stop arguing about style.",
)
def check_prettier() -> ServiceHealthResult:
    if _repo("frontend", ".prettierrc.json").exists():
        return ServiceHealthResult(
            service_key="dev_tools.prettier",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Prettier config is present.",
            issue_description="Angular code is automatically formatted. No whitespace debates between agents.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
        )
    return ServiceHealthResult(
        service_key="dev_tools.prettier",
        status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
        status_label="Prettier is not configured.",
        issue_description=(
            "Your Angular codebase has no Prettier config. AI agents make different formatting "
            "choices on every edit, leading to noisy diffs and wasted review time."
        ),
        suggested_fix="Ask your AI agent to add frontend/.prettierrc.json and install Prettier as a dev dependency.",
    )


# ── pytest.ini ────────────────────────────────────────────────────────────────


@HealthCheckRegistry.register(
    "dev_tools.pytest_ini",
    name="pytest.ini (Python test config)",
    description="Tells AI agents the canonical way to run Python tests.",
)
def check_pytest_ini() -> ServiceHealthResult:
    if _backend("pytest.ini").exists():
        return ServiceHealthResult(
            service_key="dev_tools.pytest_ini",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="pytest.ini is configured.",
            issue_description="Python tests have a single canonical configuration. AI agents know exactly how to run them.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
        )
    return ServiceHealthResult(
        service_key="dev_tools.pytest_ini",
        status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
        status_label="pytest.ini is missing.",
        issue_description=(
            "Your backend has no pytest.ini. AI agents have to guess at test flags and paths, "
            "which leads to inconsistent test runs and missed coverage."
        ),
        suggested_fix="Ask your AI agent to create backend/pytest.ini with test paths, coverage flags, and Django settings.",
    )


# ── Python coverage threshold ─────────────────────────────────────────────────


@HealthCheckRegistry.register(
    "dev_tools.coverage_threshold_python",
    name="Python Coverage Threshold",
    description="Fails CI if Python test coverage drops below the minimum percentage.",
)
def check_python_coverage_threshold() -> ServiceHealthResult:
    if _file_contains(_backend("pytest.ini"), "--cov-fail-under"):
        return ServiceHealthResult(
            service_key="dev_tools.coverage_threshold_python",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Python coverage threshold is enforced.",
            issue_description="CI will fail automatically if Python test coverage drops below the configured minimum.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
        )
    return ServiceHealthResult(
        service_key="dev_tools.coverage_threshold_python",
        status=ServiceHealthRecord.STATUS_WARNING,
        status_label="No Python coverage minimum is set.",
        issue_description=(
            "AI agents can write new Python code with zero tests and CI will still pass. "
            "There is no minimum coverage floor — bugs can ship undetected."
        ),
        suggested_fix="Ask your AI agent to add --cov-fail-under=75 to backend/pytest.ini.",
    )


# ── Angular coverage threshold ────────────────────────────────────────────────


@HealthCheckRegistry.register(
    "dev_tools.coverage_threshold_angular",
    name="Angular Coverage Threshold",
    description="Fails CI if Angular unit test coverage drops below the minimum percentage.",
)
def check_angular_coverage_threshold() -> ServiceHealthResult:
    if _file_contains(_repo("frontend", "karma.conf.cjs"), "thresholds"):
        return ServiceHealthResult(
            service_key="dev_tools.coverage_threshold_angular",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Angular coverage threshold is enforced.",
            issue_description="CI will fail automatically if Angular test coverage drops below the configured minimum.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
        )
    return ServiceHealthResult(
        service_key="dev_tools.coverage_threshold_angular",
        status=ServiceHealthRecord.STATUS_WARNING,
        status_label="No Angular coverage minimum is set.",
        issue_description=(
            "AI agents can write Angular components with zero unit tests and CI will still pass. "
            "Currently only 7 spec files cover the entire Angular app."
        ),
        suggested_fix="Ask your AI agent to add a thresholds block to frontend/karma.conf.cjs.",
    )


# ── responses library ─────────────────────────────────────────────────────────


@HealthCheckRegistry.register(
    "dev_tools.responses_library",
    name="responses (HTTP mock library)",
    description="Lets AI agents write tests for the crawler and analytics apps without real internet calls.",
)
def check_responses_library() -> ServiceHealthResult:
    if _file_contains(_backend("requirements-dev.txt"), "responses"):
        return ServiceHealthResult(
            service_key="dev_tools.responses_library",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="responses library is installed.",
            issue_description="AI agents can write safe, offline tests for the crawler and analytics HTTP calls.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
        )
    return ServiceHealthResult(
        service_key="dev_tools.responses_library",
        status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
        status_label="HTTP mock library (responses) is missing.",
        issue_description=(
            "Your crawler and analytics apps make real HTTP calls. Without the 'responses' library, "
            "AI agents cannot write safe tests for them — tests would require a live internet connection."
        ),
        suggested_fix="Ask your AI agent to add 'responses' to backend/requirements-dev.txt.",
    )


# ── OpenAPI schema ────────────────────────────────────────────────────────────


@HealthCheckRegistry.register(
    "dev_tools.openapi_schema",
    name="OpenAPI Schema (drf-spectacular)",
    description="Auto-generates API docs so AI agents understand every endpoint without reading source code.",
)
def check_openapi_schema() -> ServiceHealthResult:
    if _file_contains(_backend("requirements.txt"), "drf-spectacular"):
        return ServiceHealthResult(
            service_key="dev_tools.openapi_schema",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="drf-spectacular is installed.",
            issue_description="AI agents can read a full API reference at /api/schema/swagger-ui/ instead of scanning dozens of view files.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
        )
    return ServiceHealthResult(
        service_key="dev_tools.openapi_schema",
        status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
        status_label="OpenAPI schema generation is not set up.",
        issue_description=(
            "AI agents working on the frontend or writing API tests must read many Python view files "
            "to understand the API. drf-spectacular would generate a single readable reference automatically."
        ),
        suggested_fix=(
            "Ask your AI agent to install drf-spectacular and add /api/schema/swagger-ui/ "
            "to the URL config."
        ),
    )


# ── clang-format ──────────────────────────────────────────────────────────────


@HealthCheckRegistry.register(
    "dev_tools.clang_format",
    name="clang-format (C++ style)",
    description="Auto-formats C++ code so all AI agents produce the same style.",
)
def check_clang_format() -> ServiceHealthResult:
    if _repo(".clang-format").exists():
        return ServiceHealthResult(
            service_key="dev_tools.clang_format",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="clang-format config is present.",
            issue_description="C++ code is formatted consistently by all AI agents. No style debates in reviews.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
        )
    return ServiceHealthResult(
        service_key="dev_tools.clang_format",
        status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
        status_label="clang-format config is missing.",
        issue_description=(
            "Your C++ extensions have no formatting rules. Different AI agents produce C++ with "
            "different brace styles and indentation, making code reviews difficult."
        ),
        suggested_fix="Ask your AI agent to create a .clang-format file in the repo root.",
    )


# ── clang-tidy ────────────────────────────────────────────────────────────────


@HealthCheckRegistry.register(
    "dev_tools.clang_tidy",
    name="clang-tidy (C++ deep linter)",
    description="Catches semantic C++ bugs that the basic cppcheck linter misses.",
)
def check_clang_tidy() -> ServiceHealthResult:
    if _repo(".clang-tidy").exists():
        return ServiceHealthResult(
            service_key="dev_tools.clang_tidy",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="clang-tidy config is present.",
            issue_description="C++ extensions are checked for unsafe casts, uninitialized memory, and incorrect TBB usage.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
        )
    return ServiceHealthResult(
        service_key="dev_tools.clang_tidy",
        status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
        status_label="clang-tidy is not configured.",
        issue_description=(
            "Your CI only runs cppcheck, which catches very few real C++ bugs. "
            "clang-tidy finds unsafe casts, incorrect TBB usage, and uninitialized memory — "
            "bugs that could crash the app silently in production."
        ),
        suggested_fix=(
            "Ask your AI agent to create a .clang-tidy file in the repo root "
            "and add a clang-tidy step to CI."
        ),
    )


# ── C++ unit tests ────────────────────────────────────────────────────────────


@HealthCheckRegistry.register(
    "dev_tools.cpp_tests",
    name="C++ Unit Tests (GoogleTest)",
    description="Validates C++ extension logic at the native level before it reaches Python.",
)
def check_cpp_tests() -> ServiceHealthResult:
    tests_dir = _backend("extensions", "tests")
    if tests_dir.exists():
        cpp_files = list(tests_dir.glob("*.cpp"))
        if cpp_files:
            return ServiceHealthResult(
                service_key="dev_tools.cpp_tests",
                status=ServiceHealthRecord.STATUS_HEALTHY,
                status_label=f"C++ unit tests present ({len(cpp_files)} file(s)).",
                issue_description=(
                    f"Your C++ extensions have {len(cpp_files)} unit test file(s). "
                    "AI agents can validate new C++ code before it reaches Python."
                ),
                suggested_fix="No action needed.",
                last_success_at=timezone.now(),
                metadata={"test_file_count": len(cpp_files)},
            )
    return ServiceHealthResult(
        service_key="dev_tools.cpp_tests",
        status=ServiceHealthRecord.STATUS_ERROR,
        status_label="No C++ unit tests exist.",
        issue_description=(
            "Your 13 C++ extensions (including scoring and similarity search) have zero unit tests. "
            "AI agents writing new C++ code have nothing to validate against — "
            "bugs can silently reach production."
        ),
        suggested_fix=(
            "Ask your AI agent to create backend/extensions/tests/ and set up GoogleTest. "
            "Start with tests for scoring.cpp and simsearch.cpp."
        ),
    )


# ── AddressSanitizer in CI ────────────────────────────────────────────────────


@HealthCheckRegistry.register(
    "dev_tools.asan_ci",
    name="AddressSanitizer in CI",
    description="Detects C++ memory errors (buffer overflows, use-after-free) during automated testing.",
)
def check_asan_ci() -> ServiceHealthResult:
    if _file_contains(_repo(".github", "workflows", "ci.yml"), "fsanitize=address"):
        return ServiceHealthResult(
            service_key="dev_tools.asan_ci",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="AddressSanitizer is active in CI.",
            issue_description="C++ memory errors are automatically caught in CI before code ships.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
        )
    return ServiceHealthResult(
        service_key="dev_tools.asan_ci",
        status=ServiceHealthRecord.STATUS_ERROR,
        status_label="AddressSanitizer is NOT configured in CI.",
        issue_description=(
            "Your CPP-RULES.md requires AddressSanitizer before any C++ merge, "
            "but it is not set up in CI. An AI agent can write memory-unsafe C++ "
            "and it will pass CI today — this could crash the app in production."
        ),
        suggested_fix=(
            "Ask your AI agent to add an ASAN build job to .github/workflows/ci.yml "
            "with -fsanitize=address,undefined compiler flags."
        ),
    )


# ── GlitchTip error tracking ──────────────────────────────────────────────────


@HealthCheckRegistry.register(
    "dev_tools.glitchtip",
    name="GlitchTip (Error Tracking)",
    description="Captures Python and C++ extension errors in real time so AI agents can find and fix them.",
)
def check_glitchtip() -> ServiceHealthResult:
    dsn = os.environ.get("GLITCHTIP_DSN", "").strip()
    if not dsn:
        return ServiceHealthResult(
            service_key="dev_tools.glitchtip",
            status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
            status_label="GlitchTip is not configured.",
            issue_description=(
                "Errors that happen in the live app are invisible. "
                "Without error tracking, you have to notice problems yourself "
                "instead of being told about them automatically."
            ),
            suggested_fix=(
                "Ask your AI agent to add the GlitchTip Docker service, "
                "set GLITCHTIP_DSN in .env, and configure sentry-sdk in Django settings."
            ),
        )
    try:
        import requests as _req
        from urllib.parse import urlparse

        parsed = urlparse(dsn)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        resp = _req.get(f"{base_url}/api/", timeout=5)
        if resp.status_code < 500:
            return ServiceHealthResult(
                service_key="dev_tools.glitchtip",
                status=ServiceHealthRecord.STATUS_HEALTHY,
                status_label="GlitchTip is reachable.",
                issue_description="Error tracking is active. Python and C++ extension errors are captured automatically.",
                suggested_fix="No action needed.",
                last_success_at=timezone.now(),
            )
        return ServiceHealthResult(
            service_key="dev_tools.glitchtip",
            status=ServiceHealthRecord.STATUS_WARNING,
            status_label=f"GlitchTip returned HTTP {resp.status_code}.",
            issue_description="GlitchTip is configured but returned an unexpected response. Error tracking may not be working correctly.",
            suggested_fix="Check that the GlitchTip Docker container is running and healthy: docker-compose ps glitchtip.",
            last_error_at=timezone.now(),
        )
    except Exception as exc:
        return ServiceHealthResult(
            service_key="dev_tools.glitchtip",
            status=ServiceHealthRecord.STATUS_DOWN,
            status_label="GlitchTip is unreachable.",
            issue_description="GlitchTip is configured but the server is not responding. Errors are not being captured.",
            suggested_fix="Check that the GlitchTip Docker container is running.",
            last_error_at=timezone.now(),
            last_error_message=str(exc),
        )


# ── Dependabot ────────────────────────────────────────────────────────────────


@HealthCheckRegistry.register(
    "dev_tools.dependabot",
    name="Dependabot (Dependency Updates)",
    description="Automatically opens pull requests when Python, npm, or Actions dependencies need updates.",
)
def check_dependabot() -> ServiceHealthResult:
    if _repo(".github", "dependabot.yml").exists():
        return ServiceHealthResult(
            service_key="dev_tools.dependabot",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="Dependabot is configured.",
            issue_description="GitHub will automatically open pull requests when dependencies have security updates or new versions.",
            suggested_fix="No action needed.",
            last_success_at=timezone.now(),
        )
    return ServiceHealthResult(
        service_key="dev_tools.dependabot",
        status=ServiceHealthRecord.STATUS_NOT_CONFIGURED,
        status_label="Dependabot is not configured.",
        issue_description=(
            "Outdated or vulnerable dependencies will not be flagged automatically. "
            "You would only find out about security issues if you happened to check."
        ),
        suggested_fix="Ask your AI agent to create .github/dependabot.yml to enable automatic dependency update pull requests.",
    )
