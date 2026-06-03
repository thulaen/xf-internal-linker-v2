"""Lighthouse → AutoIssue picker.

Runs Google Lighthouse (via the Node.js CLI installed in the frontend-dev
container) against the local frontend dev server and promotes any metric
that falls below the configured threshold into an AutoIssue.

Lighthouse (https://github.com/GoogleChrome/lighthouse) measures five
categories for a web page:
  - Performance  (LCP, FCP, TBT, CLS, Speed Index)
  - Accessibility (ARIA, colour contrast, keyboard nav)
  - Best Practices (HTTPS, console errors, deprecated APIs)
  - SEO           (meta tags, crawlability)
  - PWA           (service worker, manifest)

Each category returns a score from 0 to 1 (displayed as 0–100).
We file an AutoIssue whenever a score drops below its threshold so that
agents must investigate and fix the underlying web-vitals regression
before a commit lands.

Design decisions:
  - We run Lighthouse in headless Chrome via `--headless` to avoid needing
    a display server inside Docker containers.
  - Scores are stable to ±0.03 run-to-run; thresholds are set 0.05 below
    Google's "Good" band so minor noise does not generate false positives.
  - One AutoIssue per failing category per URL, keyed on
    `lighthouse:<category>:<url_slug>` for cross-session dedup.
  - Source = SOURCE_LIGHTHOUSE so the quota gate tracks these separately
    from generic agent findings.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess  # nosec B404
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
# Google "Good" band starts at 0.90 for most categories.
# We use 0.85 (5-point buffer) so genuine regressions surface without noise.
_THRESHOLDS: dict[str, float] = {
    "performance": 0.85,
    "accessibility": 0.85,
    "best-practices": 0.85,
    "seo": 0.85,
}

# Max categories we file per Lighthouse run (anti-bloat).
_MAX_PER_RUN = 5

# Default URL — the local Angular dev server exposed on the Docker network.
_DEFAULT_FRONTEND_URL = "http://10.10.10.10:4200"


@dataclass(frozen=True)
class LighthouseScore:
    """One category result from a Lighthouse run."""

    category: str
    score: float          # 0.0–1.0
    display_score: int    # 0–100
    url: str


def _url_slug(url: str) -> str:
    """Stable short identifier for a URL — used in external_id."""
    return hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:8]


def _external_id(category: str, url: str) -> str:
    return f"lighthouse:{category}:{_url_slug(url)}"


def _severity(score: float) -> str:
    if score < 0.50:
        return AutoIssue.SEVERITY_CRITICAL
    if score < 0.70:
        return AutoIssue.SEVERITY_HIGH
    if score < 0.85:
        return AutoIssue.SEVERITY_MEDIUM
    return AutoIssue.SEVERITY_LOW


def _priority(score: float) -> float:
    """Map score deficit to priority — worse score = higher priority."""
    return round(max(0.0, 1.0 - score), 4)


def _run_lighthouse(url: str) -> dict[str, Any] | None:
    """Run Lighthouse CLI and return the parsed JSON report, or None on failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.json"
        cmd = [
            "npx", "--yes", "lighthouse",
            url,
            "--output=json",
            f"--output-path={output_path}",
            "--chrome-flags=--headless --no-sandbox --disable-dev-shm-usage",
            "--quiet",
            "--only-categories=performance,accessibility,best-practices,seo",
        ]
        try:
            result = subprocess.run(  # noqa: S603  # nosec B603
                cmd,
                capture_output=True,
                check=False,
                text=True,
                timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("[lighthouse_picker] CLI unavailable or timed out: %s", exc)
            return None

        if result.returncode != 0:
            logger.warning(
                "[lighthouse_picker] lighthouse exited %d: %s",
                result.returncode, result.stderr[:400],
            )
            return None

        try:
            return json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("[lighthouse_picker] could not read report: %s", exc)
            return None


def _scores_from_report(report: dict[str, Any], url: str) -> list[LighthouseScore]:
    """Extract per-category scores from a Lighthouse JSON report."""
    scores: list[LighthouseScore] = []
    categories = (report.get("categories") or {})
    for key, thres in _THRESHOLDS.items():
        cat = categories.get(key) or {}
        raw = cat.get("score")
        if raw is None:
            continue
        # Clamp defensively — Lighthouse should never exceed 1.0 but guard anyway.
        score = max(0.0, min(1.0, float(raw)))
        scores.append(LighthouseScore(
            category=key,
            score=score,
            display_score=round(score * 100),
            url=url,
        ))
    return scores


def _failing(scores: list[LighthouseScore]) -> list[LighthouseScore]:
    return [s for s in scores if s.score < _THRESHOLDS[s.category]]


def _upsert_score(s: LighthouseScore) -> str:
    # Compute once — used in both title and description.
    threshold_pct = round(_THRESHOLDS[s.category] * 100)
    title = (
        f"Lighthouse {s.category} score {s.display_score}/100 "
        f"(threshold {threshold_pct}) at {s.url}"
    )
    description = (
        f"Lighthouse measured the **{s.category}** category at "
        f"{s.display_score}/100 — below the project threshold of "
        f"{threshold_pct}/100.\n\n"
        f"URL: {s.url}\n\n"
        f"Run `npx lighthouse {s.url} --view` locally to see the full "
        f"audit report with actionable recommendations."
    )
    canonical = canonical_fingerprint(title, "")
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_LIGHTHOUSE,
        external_id=_external_id(s.category, s.url),
        fingerprint=_external_id(s.category, s.url),
        title=title,
        description=description,
        affected_files=[],
        severity=_severity(s.score),
        priority_score=_priority(s.score),
        occurrence_count=1,
    )
    return outcome


def pick_lighthouse_scores(
    *,
    url: str = _DEFAULT_FRONTEND_URL,
    limit: int = _MAX_PER_RUN,
) -> dict[str, Any]:
    """Run Lighthouse against *url* and file AutoIssues for failing categories.

    Returns a result dict with keys: status, url, measured, failing, promoted.
    If Lighthouse CLI is unavailable (e.g. frontend container not running),
    returns status='unavailable' without raising so the picker loop continues.
    """
    report = _run_lighthouse(url)
    if report is None:
        logger.info("[lighthouse_picker] no report produced for %s — skipping", url)
        return {"status": "unavailable", "url": url, "measured": 0, "failing": 0, "promoted": 0}

    scores = _scores_from_report(report, url)
    failures = _failing(scores)[:limit]

    counts: dict[str, int] = {"created": 0, "merged": 0, "updated": 0}
    for s in failures:
        outcome = _upsert_score(s)
        counts[outcome] = counts.get(outcome, 0) + 1

    logger.info(
        "[lighthouse_picker] url=%s measured=%d failing=%d promoted=%d",
        url, len(scores), len(failures), sum(counts.values()),
    )
    return {
        "status": "ok",
        "url": url,
        "measured": len(scores),
        "failing": len(failures),
        "promoted": sum(counts.values()),
        **counts,
    }
