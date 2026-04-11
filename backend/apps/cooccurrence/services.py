"""FR-025 — Co-occurrence and behavioral hub service functions.

All database-heavy operations are here. Tasks in tasks.py call these.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import date, timedelta
from itertools import combinations
from typing import TYPE_CHECKING

from django.db.models import Max

if TYPE_CHECKING:
    from apps.suggestions.models import Suggestion

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dunning 1993 log-likelihood ratio (G-squared) for co-occurrence pairs
# ---------------------------------------------------------------------------


def _compute_log_likelihood(
    co_count: int,
    a_total: int,
    b_total: int,
    total_sessions: int,
) -> float:
    """Compute the Dunning 1993 log-likelihood ratio (G-squared).

    The 2x2 contingency table is:
        k11 = co_count          (both A and B)
        k12 = a_total - co      (A without B)
        k21 = b_total - co      (B without A)
        k22 = N - a - b + co    (neither)

    G^2 = 2 * sum(k_ij * ln(k_ij * N / (R_i * C_j))) for non-zero cells.

    Returns 0.0 when the table is degenerate (zero margins).
    """
    n = total_sessions
    if n <= 0:
        return 0.0

    k11 = co_count
    k12 = a_total - co_count
    k21 = b_total - co_count
    k22 = n - a_total - b_total + co_count

    # Row and column totals
    r1 = k11 + k12  # a_total
    r2 = k21 + k22  # n - a_total
    c1 = k11 + k21  # b_total
    c2 = k12 + k22  # n - b_total

    if r1 <= 0 or r2 <= 0 or c1 <= 0 or c2 <= 0:
        return 0.0

    g2 = 0.0
    for k_ij, r_i, c_j in [
        (k11, r1, c1),
        (k12, r1, c2),
        (k21, r2, c1),
        (k22, r2, c2),
    ]:
        if k_ij > 0:
            expected = (r_i * c_j) / n
            g2 += k_ij * math.log(k_ij / expected)

    return max(2.0 * g2, 0.0)


# ---------------------------------------------------------------------------
# GA4 credential helpers (mirrors pattern in apps.analytics.sync)
# ---------------------------------------------------------------------------


def _build_ga4_service():
    """Return an authenticated GA4 Data API service object using stored credentials."""
    from apps.analytics.ga4_client import build_ga4_data_service
    from apps.analytics.views import (  # type: ignore[import]
        get_ga4_telemetry_settings,
        _google_oauth_client_secret,
        _google_oauth_refresh_token,
        _read_setting,
    )

    settings = get_ga4_telemetry_settings()
    property_id = str(settings.get("property_id") or "").strip()
    project_id = str(settings.get("read_project_id") or "").strip()
    client_email = str(settings.get("read_client_email") or "").strip()
    private_key = _read_setting("analytics.ga4_read_private_key", "") or ""

    refresh_token = settings.get("oauth_connected") and _google_oauth_refresh_token()
    client_id = settings.get("google_oauth_client_id")
    client_secret = _google_oauth_client_secret()

    if refresh_token and client_id and client_secret:
        service = build_ga4_data_service(
            property_id=property_id,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
    else:
        if not property_id or not project_id or not client_email or not private_key:
            raise RuntimeError(
                "GA4 credentials not configured. Set them on the Settings page."
            )
        service = build_ga4_data_service(
            property_id=property_id,
            project_id=project_id,
            client_email=client_email,
            private_key=private_key,
        )

    return service, property_id


# ---------------------------------------------------------------------------
# GA4 session co-occurrence data pipeline
# ---------------------------------------------------------------------------


def _upsert_cooccurrence_pairs(
    co_counts: dict[tuple[int, int], int],
    marginal_counts: dict[int, int],
    total_sessions: int,
    min_co_session_count: int,
    min_jaccard: float,
    window_start: date,
    window_end: date,
) -> int:
    """Compute Jaccard, lift, G-squared and upsert co-occurrence pairs."""
    from .models import SessionCoOccurrencePair

    pairs_written = 0
    for (a_id, b_id), co_count in co_counts.items():
        if co_count < min_co_session_count:
            continue

        a_total = marginal_counts.get(a_id, co_count)
        b_total = marginal_counts.get(b_id, co_count)

        union = a_total + b_total - co_count
        jaccard = co_count / union if union > 0 else 0.0
        if jaccard < min_jaccard:
            continue

        p_a = a_total / total_sessions if total_sessions else 0.0
        p_b = b_total / total_sessions if total_sessions else 0.0
        p_ab = co_count / total_sessions if total_sessions else 0.0
        lift = p_ab / (p_a * p_b) if (p_a * p_b) > 0 else 1.0
        g2 = _compute_log_likelihood(co_count, a_total, b_total, total_sessions)

        SessionCoOccurrencePair.objects.update_or_create(
            source_content_item_id=a_id,
            dest_content_item_id=b_id,
            defaults={
                "co_session_count": co_count,
                "source_session_count": a_total,
                "dest_session_count": b_total,
                "jaccard_similarity": round(jaccard, 6),
                "lift": round(lift, 4),
                "log_likelihood_score": round(g2, 4),
                "data_window_start": window_start,
                "data_window_end": window_end,
            },
        )
        pairs_written += 1
    return pairs_written


def _resolve_paths_to_content_ids(all_paths: set[str]) -> dict[str, int]:
    """Map page paths to ContentItem PKs via exact URL then path-portion match."""
    from apps.content.models import ContentItem

    path_to_id: dict[str, int] = {}
    for ci in ContentItem.objects.filter(url__in=all_paths).values("id", "url"):
        url = (ci["url"] or "").split("?")[0].rstrip("/") or "/"
        path_to_id[url] = ci["id"]
    for ci in ContentItem.objects.values("id", "url"):
        raw = ci["url"] or ""
        if "://" in raw:
            try:
                path = "/" + raw.split("://", 1)[1].split("/", 1)[1]
            except IndexError:
                path = "/"
        else:
            path = raw
        path = path.split("?")[0].rstrip("/") or "/"
        if path in all_paths and path not in path_to_id:
            path_to_id[path] = ci["id"]
    return path_to_id


def fetch_ga4_session_cooccurrence(
    data_window_days: int = 90,
    min_co_session_count: int = 5,
    min_jaccard: float = 0.05,
) -> tuple[int, int, int]:
    """Fetch GA4 session-level page-view sequences and build co-occurrence pairs.

    Returns (sessions_processed, pairs_written, ga4_rows_fetched).
    Session IDs are used only for grouping and discarded after aggregation.
    """
    service, property_id = _build_ga4_service()

    window_end = date.today()
    window_start = window_end - timedelta(days=data_window_days)

    # Fetch (sessionId, pagePath) pairs from GA4
    ga4_rows_fetched = 0
    # Map sessionId → set of page paths
    session_paths: dict[str, set[str]] = defaultdict(set)

    offset = 0
    limit = 10_000

    while True:
        try:
            response = (
                service.properties()
                .runReport(
                    property=f"properties/{property_id}",
                    body={
                        "dateRanges": [
                            {
                                "startDate": window_start.isoformat(),
                                "endDate": window_end.isoformat(),
                            }
                        ],
                        "dimensions": [
                            {"name": "sessionId"},
                            {"name": "pagePath"},
                        ],
                        "metrics": [{"name": "sessions"}],
                        "limit": limit,
                        "offset": offset,
                    },
                )
                .execute()
            )
        except Exception as exc:
            logger.error("GA4 session fetch failed at offset %d: %s", offset, exc)
            raise

        rows = response.get("rows", [])
        ga4_rows_fetched += len(rows)

        for row in rows:
            dims = row.get("dimensionValues", [])
            if len(dims) < 2:
                continue
            session_id = dims[0].get("value", "")
            page_path = dims[1].get("value", "").split("?")[0].rstrip("/") or "/"
            if session_id:
                session_paths[session_id].add(page_path)

        if len(rows) < limit:
            break
        offset += limit

    logger.info(
        "GA4 session fetch: %d rows, %d sessions, window %s–%s",
        ga4_rows_fetched,
        len(session_paths),
        window_start,
        window_end,
    )

    all_paths: set[str] = set()
    for paths in session_paths.values():
        all_paths.update(paths)
    path_to_id = _resolve_paths_to_content_ids(all_paths)

    # Build co-occurrence counts
    # co_counts[(a_id, b_id)] = co_session_count
    # marginal_counts[id] = session count
    co_counts: dict[tuple[int, int], int] = defaultdict(int)
    marginal_counts: dict[int, int] = defaultdict(int)
    sessions_processed = 0

    for session_id, paths in session_paths.items():
        item_ids = sorted({path_to_id[p] for p in paths if p in path_to_id})
        if len(item_ids) < 2:
            if len(item_ids) == 1:
                marginal_counts[item_ids[0]] += 1
            continue
        sessions_processed += 1
        for item_id in item_ids:
            marginal_counts[item_id] += 1
        for a_id, b_id in combinations(item_ids, 2):
            co_counts[(a_id, b_id)] += 1
            co_counts[(b_id, a_id)] += 1

    logger.info(
        "Co-occurrence matrix: %d sessions processed, %d raw pairs",
        sessions_processed,
        len(co_counts),
    )

    total_sessions = len(session_paths)
    pairs_written = _upsert_cooccurrence_pairs(
        co_counts,
        marginal_counts,
        total_sessions,
        min_co_session_count,
        min_jaccard,
        window_start,
        window_end,
    )

    logger.info("Co-occurrence upsert complete: %d pairs written", pairs_written)
    return sessions_processed, pairs_written, ga4_rows_fetched


# ---------------------------------------------------------------------------
# Co-occurrence signal
# ---------------------------------------------------------------------------


def get_site_max_jaccard() -> float:
    """Return the maximum Jaccard similarity across all stored pairs (for normalization)."""
    from .models import SessionCoOccurrencePair

    result = SessionCoOccurrencePair.objects.aggregate(Max("jaccard_similarity"))
    return float(result["jaccard_similarity__max"] or 1.0)


def compute_co_occurrence_signal(
    source_id: int,
    dest_id: int,
    min_co_sessions: int = 5,
    fallback: float = 0.5,
    site_max_jaccard: float = 1.0,
    llr_sigmoid_alpha: float = 0.1,
    llr_sigmoid_beta: float = 10.0,
) -> tuple[float, dict]:
    """Return (signal_value, diagnostics) for a source->dest pair.

    Uses sigmoid-normalized Dunning 1993 log-likelihood ratio (G-squared)
    instead of site-max Jaccard normalization.  The sigmoid maps the
    unbounded G-squared into [0, 1]:  signal = 1 / (1 + exp(-alpha*(g2 - beta))).

    ``site_max_jaccard`` is kept for backward compatibility but no longer
    affects the signal value.
    """
    from .models import SessionCoOccurrencePair

    diagnostics: dict = {
        "co_occurrence_signal": fallback,
        "co_session_count": 0,
        "jaccard_similarity": 0.0,
        "log_likelihood_score": 0.0,
        "lift": 1.0,
        "co_occurrence_method": "llr_sigmoid_v1",
        "co_occurrence_fallback_used": True,
    }

    try:
        pair = SessionCoOccurrencePair.objects.get(
            source_content_item_id=source_id,
            dest_content_item_id=dest_id,
        )
    except SessionCoOccurrencePair.DoesNotExist:
        return fallback, diagnostics

    if pair.co_session_count < min_co_sessions:
        diagnostics["co_session_count"] = pair.co_session_count
        diagnostics["jaccard_similarity"] = pair.jaccard_similarity
        diagnostics["log_likelihood_score"] = pair.log_likelihood_score
        diagnostics["lift"] = pair.lift
        return fallback, diagnostics

    # Sigmoid normalization of G-squared (Dunning 1993)
    g2 = pair.log_likelihood_score
    exponent = -llr_sigmoid_alpha * (g2 - llr_sigmoid_beta)
    # Clamp to avoid overflow in exp()
    exponent = max(-50.0, min(50.0, exponent))
    signal = 1.0 / (1.0 + math.exp(exponent))

    diagnostics.update(
        {
            "co_occurrence_signal": round(signal, 6),
            "co_session_count": pair.co_session_count,
            "jaccard_similarity": round(pair.jaccard_similarity, 6),
            "log_likelihood_score": round(g2, 4),
            "lift": round(pair.lift, 4),
            "co_occurrence_fallback_used": False,
        }
    )
    return signal, diagnostics


# ---------------------------------------------------------------------------
# Behavioral hub detection
# ---------------------------------------------------------------------------


def detect_behavioral_hubs(
    hub_min_jaccard: float = 0.15,
    hub_min_members: int = 3,
) -> tuple[int, int]:
    """Detect behavioral hubs via threshold-based connected components.

    Returns (hubs_created_or_updated, total_members_assigned).
    Preserves manual_remove_override memberships.
    """
    from .models import SessionCoOccurrencePair, BehavioralHub, BehavioralHubMembership

    # Build undirected adjacency list
    pairs = SessionCoOccurrencePair.objects.filter(
        jaccard_similarity__gte=hub_min_jaccard
    ).values_list("source_content_item_id", "dest_content_item_id")

    graph: dict[int, set[int]] = defaultdict(set)
    for a_id, b_id in pairs:
        graph[a_id].add(b_id)
        graph[b_id].add(a_id)

    if not graph:
        return 0, 0

    # BFS to find connected components
    visited: set[int] = set()
    components: list[set[int]] = []

    for node in graph:
        if node in visited:
            continue
        component: set[int] = set()
        queue = [node]
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            queue.extend(graph[current] - visited)
        if len(component) >= hub_min_members:
            components.append(component)

    logger.info(
        "Hub detection: %d qualifying components (min_jaccard=%.3f, min_members=%d)",
        len(components),
        hub_min_jaccard,
        hub_min_members,
    )

    # Load all pairs for strength computation
    all_pairs: dict[tuple[int, int], float] = {
        (a, b): j
        for a, b, j in SessionCoOccurrencePair.objects.filter(
            jaccard_similarity__gte=hub_min_jaccard
        ).values_list(
            "source_content_item_id", "dest_content_item_id", "jaccard_similarity"
        )
    }

    # Load existing manual_remove_override memberships so we can skip them
    removed_memberships: set[tuple[int, int]] = set(
        BehavioralHubMembership.objects.filter(
            membership_source=BehavioralHubMembership.SOURCE_MANUAL_REMOVE
        ).values_list("hub_id", "content_item_id")
    )

    # Mark existing auto-detected hubs for potential cleanup
    # (we identify hubs by their frozenset of auto members to avoid drift)
    total_hubs = 0
    total_members = 0

    for i, component in enumerate(components, start=1):
        component_list = sorted(component)

        # Compute average Jaccard for each member to the rest of the component
        strengths: dict[int, float] = {}
        for node in component_list:
            neighbor_jaccards = [
                all_pairs.get((node, other), all_pairs.get((other, node), 0.0))
                for other in component_list
                if other != node
            ]
            strengths[node] = (
                sum(neighbor_jaccards) / len(neighbor_jaccards)
                if neighbor_jaccards
                else 0.0
            )

        # Find or create a hub for this component
        # Use a stable name based on top-strength member's content item ID
        top_member_id = max(component_list, key=lambda n: strengths.get(n, 0.0))
        auto_name = f"Hub {i} (anchor: content {top_member_id})"

        hub = BehavioralHub.objects.create(
            name=auto_name,
            detection_method=BehavioralHub.METHOD_THRESHOLD,
            min_jaccard_used=hub_min_jaccard,
            member_count=0,
        )

        memberships_to_create = []
        members_added = 0
        for node in component_list:
            if (hub.hub_id, node) in removed_memberships:
                continue
            memberships_to_create.append(
                BehavioralHubMembership(
                    hub=hub,
                    content_item_id=node,
                    membership_source=BehavioralHubMembership.SOURCE_AUTO,
                    co_occurrence_strength=round(strengths.get(node, 0.0), 6),
                )
            )
            members_added += 1

        BehavioralHubMembership.objects.bulk_create(
            memberships_to_create, ignore_conflicts=True
        )
        hub.member_count = members_added
        hub.save(update_fields=["member_count", "updated_at"])

        total_hubs += 1
        total_members += members_added

    return total_hubs, total_members


# ---------------------------------------------------------------------------
# Value model scoring (post-pipeline pass)
# ---------------------------------------------------------------------------


def compute_value_model_score(
    suggestion: "Suggestion",
    settings: dict,
    site_max_jaccard: float = 1.0,
) -> tuple[float, dict]:
    """Compute the 7-signal value model score for a suggestion.

    Returns (score_value_model, value_model_diagnostics).

    Signal mapping:
      relevance    → suggestion.score_semantic (embedding cosine similarity)
      traffic      → dest.content_value_score (GA4/GSC composite)
      freshness    → dest.link_freshness_score
      authority    → dest.march_2026_pagerank_score
      engagement   → dest.engagement_quality_score (GA4 behavioural quality)
      cooccurrence → SessionCoOccurrencePair Jaccard (pairwise)
      penalty      → composite of density / anchor-overshoot / cluster proximity
    """
    from apps.pipeline.services.penalty import compute_penalty_signal

    dest = suggestion.destination
    host = suggestion.host

    relevance_signal = float(suggestion.score_semantic or 0.5)
    traffic_signal = float(getattr(dest, "content_value_score", 0.5) or 0.5)
    freshness_signal = float(getattr(dest, "link_freshness_score", 0.5) or 0.5)
    authority_signal = float(getattr(dest, "march_2026_pagerank_score", 0.5) or 0.5)
    engagement_signal = float(getattr(dest, "engagement_quality_score", 0.5) or 0.5)

    # Graduated penalty signal — falls back to 0.0 on any error.
    try:
        host_content_id = host.pk if host is not None else None
        anchor_text = getattr(suggestion, "anchor_phrase", None) or None
        sentence_position = None
        host_sentence = getattr(suggestion, "host_sentence", None)
        if host_sentence is not None:
            sentence_position = getattr(host_sentence, "position", None)
        if host_content_id is not None:
            penalty_signal = compute_penalty_signal(
                host_content_id=host_content_id,
                anchor_text=anchor_text,
                sentence_position=sentence_position,
            )
        else:
            penalty_signal = 0.0
    except Exception:
        logger.debug(
            "Penalty signal computation failed; defaulting to 0.0", exc_info=True
        )
        penalty_signal = 0.0

    min_co_sessions = int(settings.get("co_occurrence_min_co_sessions", 5))
    fallback = float(settings.get("co_occurrence_fallback_value", 0.5))
    co_enabled = bool(settings.get("co_occurrence_signal_enabled", True))
    llr_alpha = float(settings.get("co_occurrence.llr_sigmoid_alpha", 0.1))
    llr_beta = float(settings.get("co_occurrence.llr_sigmoid_beta", 10.0))

    if co_enabled and host is not None and dest is not None:
        co_signal, co_diagnostics = compute_co_occurrence_signal(
            source_id=host.pk,
            dest_id=dest.pk,
            min_co_sessions=min_co_sessions,
            fallback=fallback,
            site_max_jaccard=site_max_jaccard,
            llr_sigmoid_alpha=llr_alpha,
            llr_sigmoid_beta=llr_beta,
        )
    else:
        co_signal = fallback
        co_diagnostics = {
            "co_occurrence_signal": fallback,
            "co_session_count": 0,
            "jaccard_similarity": 0.0,
            "lift": 1.0,
            "co_occurrence_fallback_used": True,
        }

    w_relevance = float(settings.get("w_relevance", 0.35))
    w_traffic = float(settings.get("w_traffic", 0.25))
    w_freshness = float(settings.get("w_freshness", 0.1))
    w_authority = float(settings.get("w_authority", 0.1))
    w_engagement = float(settings.get("w_engagement", 0.08))
    w_cooccurrence = float(settings.get("w_cooccurrence", 0.12))
    w_penalty = float(settings.get("w_penalty", 0.5))

    score = (
        w_relevance * relevance_signal
        + w_traffic * traffic_signal
        + w_freshness * freshness_signal
        + w_authority * authority_signal
        + w_engagement * engagement_signal
        + w_cooccurrence * co_signal
        - w_penalty * penalty_signal
    )
    score = max(0.0, min(1.0, score))

    diagnostics = {
        "relevance_signal": round(relevance_signal, 6),
        "traffic_signal": round(traffic_signal, 6),
        "freshness_signal": round(freshness_signal, 6),
        "authority_signal": round(authority_signal, 6),
        "engagement_signal": round(engagement_signal, 6),
        "penalty_signal": round(penalty_signal, 6),
        "w_relevance": w_relevance,
        "w_traffic": w_traffic,
        "w_freshness": w_freshness,
        "w_authority": w_authority,
        "w_engagement": w_engagement,
        "w_cooccurrence": w_cooccurrence,
        "w_penalty": w_penalty,
        **co_diagnostics,
    }
    return round(score, 6), diagnostics
