"""Category helpers for AutoIssue rows."""

from __future__ import annotations

import re

from apps.auto_issues.models import AutoIssue, AutoIssueCategory


DEFAULT_CATEGORY_KEY = "uncategorized"
_CATEGORY_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

DEFAULT_CATEGORIES = (
    ("security", "Security", "Sensitive data, validation, secrets, and platform safety.", 10),
    ("performance", "Performance", "Slow paths, expensive queries, memory use, and scaling.", 20),
    ("maintainability", "Maintainability", "Small modules, reuse, separation, and simple design.", 30),
    ("readability", "Readability", "Names, comments, formatting, and dead-code cleanup.", 40),
    ("correctness", "Correctness", "Expected behavior, tests, edge cases, and logic clarity.", 50),
    ("error-handling", "Error handling", "Clear failures, useful logs, retries, and fallbacks.", 60),
    ("concurrency", "Concurrency", "Shared resources, async handling, races, and deadlocks.", 70),
    ("contract", "Contract", "API compatibility, signatures, return shapes, and validation.", 80),
    ("architecture", "Architecture", "Coupling, circular imports, globals, and third-party fit.", 90),
    ("resources", "Resources", "Files, sockets, connections, buffers, and cache invalidation.", 100),
    ("tech-debt", "Tech debt", "Tracked TODOs, magic numbers, and future refactor work.", 110),
    ("observability", "Observability", "Metrics, traces, error context, and monitoring hooks.", 120),
    ("tooling", "Tooling", "Broken, missing, or incomplete test and quality tools.", 125),
    (
        "internationalization",
        "Internationalization",
        "Translations, time zones, locales, accessibility, and right-to-left layout.",
        130,
    ),
    ("uncategorized", "Uncategorized", "Issues that still need a more specific category.", 1000),
)
_DEFAULTS_BY_KEY = {key: (label, description, order) for key, label, description, order in DEFAULT_CATEGORIES}
_SOURCE_DEFAULTS = {
    AutoIssue.SOURCE_PYROSCOPE: "performance",
    AutoIssue.SOURCE_TEMPO: "observability",
    AutoIssue.SOURCE_LOKI: "observability",
    AutoIssue.SOURCE_FARO: "observability",
    AutoIssue.SOURCE_GLITCHTIP: "observability",
    AutoIssue.SOURCE_MUTATION: "correctness",
    AutoIssue.SOURCE_FUZZ: "correctness",
    AutoIssue.SOURCE_CONTRACT: "contract",
    AutoIssue.SOURCE_GH_CI: "correctness",
    AutoIssue.SOURCE_AGENT: "tech-debt",
}


def normalize_category_key(key: str | None) -> str:
    value = (key or DEFAULT_CATEGORY_KEY).strip().lower().replace("_", "-")
    if not _CATEGORY_KEY_RE.fullmatch(value):
        raise ValueError(
            "AutoIssue category keys must use lowercase letters, numbers, and hyphens."
        )
    return value


def default_category_for_source(source: str) -> str:
    return _SOURCE_DEFAULTS.get(source, DEFAULT_CATEGORY_KEY)


def get_or_create_category(key: str | None) -> AutoIssueCategory:
    normalized = normalize_category_key(key)
    label, description, sort_order = _DEFAULTS_BY_KEY.get(
        normalized,
        (_label_from_key(normalized), "Custom AutoIssue category.", 900),
    )
    category, _ = AutoIssueCategory.objects.get_or_create(
        key=normalized,
        defaults={
            "label": label,
            "description": description,
            "sort_order": sort_order,
        },
    )
    return category


def _label_from_key(key: str) -> str:
    return key.replace("-", " ").title()
