"""Helpers for FR-016 instrumented-link review output."""

from __future__ import annotations

import hashlib
import html


def _source_label(content_type: str) -> str:
    return "wordpress" if (content_type or "").startswith("wp_") else "xenforo"


def build_suggestion_telemetry_payload(
    suggestion, *, event_schema: str = "fr016_v1"
) -> dict[str, object]:
    """Return copy-ready telemetry attributes for one suggestion."""

    anchor_text = (suggestion.anchor_edited or suggestion.anchor_phrase or "").strip()
    destination_url = (getattr(suggestion.destination, "url", "") or "").strip()
    pipeline_run_id = str(suggestion.pipeline_run_id or "")
    version_date = ""
    version_slug = ""
    if suggestion.pipeline_run and suggestion.pipeline_run.created_at:
        version_date = suggestion.pipeline_run.created_at.date().isoformat()
        version_slug = version_date.replace("-", "_")

    anchor_hash = (
        hashlib.sha256(anchor_text.lower().encode("utf-8")).hexdigest()[:12]
        if anchor_text
        else ""
    )
    status = "instrumented" if anchor_text and destination_url else "plain_manual"
    attributes = {
        "data-xfil-schema": event_schema,
        "data-xfil-suggestion-id": str(suggestion.suggestion_id),
        "data-xfil-pipeline-run-id": pipeline_run_id,
        "data-xfil-algorithm-key": "pipeline_bundle",
        "data-xfil-algorithm-version-date": version_date,
        "data-xfil-algorithm-version-slug": version_slug,
        "data-xfil-destination-id": str(
            getattr(suggestion.destination, "content_id", "")
        ),
        "data-xfil-destination-type": str(
            getattr(suggestion.destination, "content_type", "")
        ),
        "data-xfil-host-id": str(getattr(suggestion.host, "content_id", "")),
        "data-xfil-host-type": str(getattr(suggestion.host, "content_type", "")),
        "data-xfil-source-label": _source_label(
            getattr(suggestion.host, "content_type", "")
        ),
        "data-xfil-same-silo": "1"
        if getattr(suggestion, "_same_silo_cached", False)
        else "0",
        "data-xfil-link-position-bucket": "unknown",
        "data-xfil-anchor-hash": anchor_hash,
        "data-xfil-anchor-length": str(len(anchor_text)),
    }
    attrs_string = " ".join(
        f'{key}="{html.escape(value, quote=True)}"'
        for key, value in attributes.items()
        if value != ""
    )
    instrumented_markup = ""
    if status == "instrumented":
        instrumented_markup = f'<a href="{html.escape(destination_url, quote=True)}" {attrs_string}>{html.escape(anchor_text)}</a>'

    return {
        "status": status,
        "event_schema": event_schema,
        "attributes": attributes,
        "anchor_hash": anchor_hash,
        "anchor_length": len(anchor_text),
        "instrumented_markup": instrumented_markup,
    }
