"""Tuning-corpus harvesting for root-cause clustering.

Gathers labeled and unlabeled error samples from many sources so the Optuna
tuner can fit the clustering parameters to real, duplicate-heavy data:

- **GlitchTip** — events grouped under one issue are genuine duplicates →
  label ``gt:{issue_id}`` (strong positive labels).
- **SonarQube** — findings sharing a rule + normalised message →
  label ``sonar:{rule}:{msghash}``.
- **Loki / OTel logs** — raw log lines as volume/distractors. They have no
  reliable external grouping, so they are *unlabeled*; they stress-test
  precision (the tuner is penalised if they get merged into a labeled family).
- **AutoIssue rows** — fallback samples; same ``canonical_fingerprint`` →
  label ``fp:{fingerprint}``.

Each source is **best-effort**: an unreachable or empty source is skipped with a
logged note, never fatal. Labels feed the precision/recall objective; unlabeled
samples participate in clustering but are excluded from scoring.

The scoring helpers (`cluster_pairs`, `precision_recall`) are pure and
deterministic so they unit-test without any network or DB.
"""
from __future__ import annotations

import hashlib
import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 12000
_NORMALIZE_HELP = "apps.auto_issues.services.clustering_features.normalize"


@dataclass
class Sample:
    """One error sample. ``label`` is None for unlabeled volume/distractors."""

    sample_id: str
    text: str
    paths: List[str] = field(default_factory=list)
    label: Optional[str] = None
    source: str = ""


# --------------------------------------------------------------------------- #
# Pure scoring core (no I/O) — the tuner objective is built on these.
# --------------------------------------------------------------------------- #
def cluster_pairs(cluster: Sequence[str]) -> List[Tuple[str, str]]:
    """All unordered member pairs within one cluster."""
    pairs: List[Tuple[str, str]] = []
    members = list(cluster)
    for i, left in enumerate(members):
        for right in members[i + 1 :]:
            pairs.append((left, right) if left <= right else (right, left))
    return pairs


def precision_recall(
    clusters: Sequence[Sequence[str]], labels: Dict[str, str]
) -> Tuple[float, float]:
    """Precision/recall of a clustering against duplicate labels.

    Only pairs where **both** ids are labeled count. Precision = labeled pairs
    placed together that truly share a label, over all labeled pairs placed
    together. Recall = labeled same-label pairs found, over all same-label pairs
    in the corpus. Unlabeled samples are ignored for scoring (but they may still
    be clustered, so merging one into a labeled family lowers precision).
    """
    true_positive = 0
    false_positive = 0
    for cluster in clusters:
        labeled = [member for member in cluster if member in labels]
        for i, left in enumerate(labeled):
            for right in labeled[i + 1 :]:
                left_label, right_label = labels[left], labels[right]
                if left_label == right_label:
                    true_positive += 1
                elif _namespace(left_label) == _namespace(right_label):
                    # Same label system, different group → a genuine over-merge.
                    false_positive += 1
                # Different label systems (e.g. gt: vs fp:) are not comparable,
                # so a cross-namespace pair is neither a hit nor a miss.
    placed = true_positive + false_positive
    precision = true_positive / placed if placed else 1.0
    label_counts = Counter(labels.values())
    total_positive = sum(n * (n - 1) // 2 for n in label_counts.values())
    recall = true_positive / total_positive if total_positive else 0.0
    return precision, recall


def _namespace(label: str) -> str:
    """The label system a label belongs to (text before the first ':')."""
    return label.split(":", 1)[0]


def _msg_hash(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=6).hexdigest()


# --------------------------------------------------------------------------- #
# Best-effort source fetchers. Each returns [] on any failure.
# --------------------------------------------------------------------------- #
def _safe(source_name: str, fetch: Callable[[], List[Sample]]) -> List[Sample]:
    try:
        samples = fetch()
        logger.info("[sample-corpus] %s contributed %d samples", source_name, len(samples))
        return samples
    except Exception as exc:  # noqa: BLE001 — sources must never be fatal
        logger.warning("[sample-corpus] %s skipped: %s", source_name, exc)
        return []


def _gt_text(obj: dict, fallback: str = "") -> str:
    """Build discriminating text from a GlitchTip issue/event.

    Includes culprit + metadata (exception type/value), not just the title, so
    two issues with similar titles but different code locations — which
    GlitchTip groups separately by stack — stay distinguishable to the
    clustering. Title-only features over-merge such issues.
    """
    meta = obj.get("metadata") or {}
    parts = [
        str(obj.get("title") or ""),
        str(obj.get("culprit") or ""),
        str(meta.get("type") or ""),
        str(meta.get("value") or ""),
    ]
    text = " ".join(part for part in parts if part).strip()
    return text or fallback


def gather_glitchtip(per_issue_events: int = 50) -> List[Sample]:
    """GlitchTip issues + their events; events of one issue are duplicates."""
    import requests

    from apps.audit.tasks import _fetch_glitchtip_issues, _glitchtip_env

    api_url, token, org, proj = _glitchtip_env()
    if not all([api_url, token, org, proj]):
        return []
    issues, err = _fetch_glitchtip_issues(api_url, token, org, proj)
    if err or not issues:
        return []
    headers = {"Authorization": f"Bearer {token}"}
    out: List[Sample] = []
    for issue in issues:
        issue_id = str(issue.get("id", ""))
        if not issue_id:
            continue
        issue_text = _gt_text(issue)
        out.append(
            Sample(f"gt-issue-{issue_id}", issue_text, [], f"gt:{issue_id}", "glitchtip")
        )
        try:
            resp = requests.get(
                f"{api_url}/api/0/issues/{issue_id}/events/",
                headers=headers,
                params={"limit": per_issue_events},
                timeout=15,
            )
            resp.raise_for_status()
            events = resp.json()
        except (requests.RequestException, ValueError):
            continue
        for event in events if isinstance(events, list) else []:
            event_id = str(event.get("id", event.get("eventID", "")))
            if event_id:
                out.append(
                    Sample(
                        f"gt-event-{event_id}",
                        _gt_text(event, issue_text),
                        [],
                        f"gt:{issue_id}",
                        "glitchtip",
                    )
                )
    return out


def gather_sonarqube() -> List[Sample]:
    """SonarQube findings; same rule + normalised message ≈ duplicate."""
    import requests

    host = os.environ.get("SONAR_HOST_URL", "http://10.10.10.91:9000").rstrip("/")
    token = os.environ.get("SONAR_TOKEN", "")
    project = os.environ.get("SONAR_PROJECT_KEY", "xf-internal-linker-v2")
    if not token:
        return []
    resp = requests.get(
        f"{host}/api/issues/search",
        params={"componentKeys": project, "ps": 500, "resolved": "false"},
        auth=(token, ""),
        timeout=20,
    )
    resp.raise_for_status()
    issues = resp.json().get("issues", [])
    out: List[Sample] = []
    for issue in issues:
        rule = issue.get("rule", "")
        message = issue.get("message", "")
        component = issue.get("component", "")
        key = issue.get("key", "")
        if not key:
            continue
        label = f"sonar:{rule}:{_msg_hash(message)}"
        out.append(Sample(f"sonar-{key}", message, [component], label, "sonarqube"))
    return out


def gather_loki(query: str = '{level=~"error|ERROR"}', max_lines: int = 4000) -> List[Sample]:
    """Raw Loki/OTel log lines as unlabeled volume/distractor samples."""
    import time

    import requests

    api = os.environ.get("LOKI_API_URL", "http://loki:3100").rstrip("/")
    end = int(time.time() * 1e9)
    start = end - 7 * 24 * 3600 * 10**9
    resp = requests.get(
        f"{api}/loki/api/v1/query_range",
        params={"query": query, "start": start, "end": end, "limit": max_lines},
        timeout=20,
    )
    resp.raise_for_status()
    streams = resp.json().get("data", {}).get("result", [])
    out: List[Sample] = []
    for stream in streams:
        for ts, line in stream.get("values", []):
            out.append(Sample(f"loki-{ts}", str(line), [], None, "loki"))
    return out


def gather_autoissues(limit: int = 4000) -> List[Sample]:
    """AutoIssue rows; same canonical_fingerprint → duplicate label."""
    from apps.auto_issues.models import AutoIssue

    rows = AutoIssue.objects.all().order_by("-last_seen")[:limit]
    out: List[Sample] = []
    for row in rows:
        label = f"fp:{row.canonical_fingerprint}" if row.canonical_fingerprint else None
        text = f"{row.title} {row.description or ''}".strip()
        out.append(
            Sample(f"ai-{row.id}", text, list(row.affected_files or []), label, "autoissue")
        )
    return out


def gather(limit: int = DEFAULT_LIMIT) -> List[Sample]:
    """Gather up to ``limit`` samples across all sources (best-effort)."""
    samples: List[Sample] = []
    for name, fetch in (
        ("glitchtip", gather_glitchtip),
        ("sonarqube", gather_sonarqube),
        ("loki", gather_loki),
        ("autoissues", gather_autoissues),
    ):
        if len(samples) >= limit:
            break
        samples.extend(_safe(name, fetch))
    return samples[:limit]
