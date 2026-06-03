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
            logger.warning(
                "GA4 credentials not configured. Set them on the Settings page."
            )
            return None, None
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


def _compute_pair_scores(
    co_count: int,
    a_total: int,
    b_total: int,
    total_sessions: int,
) -> dict:
    """Compute Jaccard, lift, G², PMI, NPMI for a single co-occurrence pair.

    Pick #24 — PMI (Church & Hanks 1990) and NPMI computed from the same
    counts as G² (Dunning 1993) so all five scores cost one pass.
    """
    from apps.sources.collocations import normalised_pmi as _npmi
    from apps.sources.collocations import pmi as _pmi

    union = a_total + b_total - co_count
    jaccard = co_count / union if union > 0 else 0.0
    p_a = a_total / total_sessions if total_sessions else 0.0
    p_b = b_total / total_sessions if total_sessions else 0.0
    p_ab = co_count / total_sessions if total_sessions else 0.0
    lift = p_ab / (p_a * p_b) if (p_a * p_b) > 0 else 1.0
    g2 = _compute_log_likelihood(co_count, a_total, b_total, total_sessions)
    pmi_v = _pmi(
        joint_count=co_count, count_a=a_total, count_b=b_total, total=total_sessions
    )
    npmi_v = _npmi(
        joint_count=co_count, count_a=a_total, count_b=b_total, total=total_sessions
    )
    return {"jaccard": jaccard, "lift": lift, "g2": g2, "pmi": pmi_v, "npmi": npmi_v}


def _upsert_cooccurrence_pairs(
    co_counts: dict[tuple[int, int], int],
    marginal_counts: dict[int, int],
    total_sessions: int,
    min_co_session_count: int,
    min_jaccard: float,
    window_start: date,
    window_end: date,
) -> int:
    """Filter pairs, compute all five co-occurrence scores, and upsert to DB."""
    from .models import SessionCoOccurrencePair

    pairs_written = 0
    for (a_id, b_id), co_count in co_counts.items():
        if co_count < min_co_session_count:
            continue
        a_total = marginal_counts.get(a_id, co_count)
        b_total = marginal_counts.get(b_id, co_count)
        scores = _compute_pair_scores(co_count, a_total, b_total, total_sessions)
        if scores["jaccard"] < min_jaccard:
            continue
        SessionCoOccurrencePair.objects.update_or_create(
            source_content_item_id=a_id,
            dest_content_item_id=b_id,
            defaults={
                "co_session_count": co_count,
                "source_session_count": a_total,
                "dest_session_count": b_total,
                "jaccard_similarity": round(scores["jaccard"], 6),
                "lift": round(scores["lift"], 4),
                "log_likelihood_score": round(scores["g2"], 4),
                "pmi_score": round(scores["pmi"], 4),
                "npmi_score": round(scores["npmi"], 4),
                "data_window_start": window_start,
                "data_window_end": window_end,
            },
        )
        pairs_written += 1
    return pairs_written


def _make_ga4_report_body(
    window_start: date,
    window_end: date,
    limit: int,
    offset: int,
) -> dict:
    """Build the GA4 runReport request body for session co-occurrence fetching."""
    return {
        "dateRanges": [
            {"startDate": window_start.isoformat(), "endDate": window_end.isoformat()}
        ],
        "dimensions": [{"name": "sessionId"}, {"name": "pagePath"}],
        "metrics": [{"name": "sessions"}],
        "limit": limit,
        "offset": offset,
    }


def _process_ga4_rows(rows: list, session_paths: dict[str, set[str]]) -> None:
    """Parse GA4 dimension rows into session → page-path mappings."""
    for row in rows:
        dims = row.get("dimensionValues", [])
        if len(dims) < 2:
            continue
        session_id = dims[0].get("value", "")
        page_path = dims[1].get("value", "").split("?")[0].rstrip("/") or "/"
        if session_id:
            session_paths[session_id].add(page_path)


def _fetch_ga4_session_paths(
    service,
    property_id: str,
    window_start: date,
    window_end: date,
) -> tuple[dict[str, set[str]], int]:
    """Paginate through GA4 to build a sessionId → page-paths mapping."""
    ga4_rows_fetched = 0
    session_paths: dict[str, set[str]] = defaultdict(set)
    offset = 0
    limit = 10_000

    while True:
        try:
            response = (
                service.properties()
                .runReport(
                    property=f"properties/{property_id}",
                    body=_make_ga4_report_body(window_start, window_end, limit, offset),
                )
                .execute()
            )
        except Exception as exc:
            logger.error("GA4 session fetch failed at offset %d: %s", offset, exc)
            raise

        rows = response.get("rows", [])
        ga4_rows_fetched += len(rows)
        _process_ga4_rows(rows, session_paths)

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
    return session_paths, ga4_rows_fetched


def _build_cooccurrence_counts(
    session_paths: dict[str, set[str]],
    path_to_id: dict[str, int],
) -> tuple[dict, dict, int]:
    """Build co-occurrence and marginal counts from session → path mappings.

    Returns (co_counts, marginal_counts, sessions_processed).
    Sessions with only one known page are counted in marginals but not pairs.
    """
    co_counts: dict[tuple[int, int], int] = defaultdict(int)
    marginal_counts: dict[int, int] = defaultdict(int)
    sessions_processed = 0

    for paths in session_paths.values():
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

    return co_counts, marginal_counts, sessions_processed


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
    if not service:
        logger.warning(
            "Skipping co-occurrence matrix build: GA4 credentials not configured."
        )
        return 0, 0, 0

    window_end = date.today()
    window_start = window_end - timedelta(days=data_window_days)

    session_paths, ga4_rows_fetched = _fetch_ga4_session_paths(
        service, property_id, window_start, window_end
    )

    all_paths: set[str] = set()
    for paths in session_paths.values():
        all_paths.update(paths)
    path_to_id = _resolve_paths_to_content_ids(all_paths)

    co_counts, marginal_counts, sessions_processed = _build_cooccurrence_counts(
        session_paths, path_to_id
    )
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


def _fallback_signal_diagnostics(fallback: float) -> dict:
    """Build the diagnostics dict returned when the co-occurrence signal falls back."""
    return {
        "co_occurrence_signal": fallback,
        "co_session_count": 0,
        "jaccard_similarity": 0.0,
        "log_likelihood_score": 0.0,
        "lift": 1.0,
        "co_occurrence_method": "llr_sigmoid_v1",
        "co_occurrence_fallback_used": True,
    }


def _llr_sigmoid(g2: float, alpha: float, beta: float) -> float:
    """Map G² (Dunning 1993) to [0, 1]: 1 / (1 + exp(-alpha*(g2 - beta)))."""
    exponent = max(
        -50.0, min(50.0, -alpha * (g2 - beta))
    )  # clamp prevents exp() overflow
    return 1.0 / (1.0 + math.exp(exponent))


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

    diagnostics = _fallback_signal_diagnostics(fallback)

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

    signal = _llr_sigmoid(
        pair.log_likelihood_score, llr_sigmoid_alpha, llr_sigmoid_beta
    )
    diagnostics.update(
        {
            "co_occurrence_signal": round(signal, 6),
            "co_session_count": pair.co_session_count,
            "jaccard_similarity": round(pair.jaccard_similarity, 6),
            "log_likelihood_score": round(pair.log_likelihood_score, 4),
            "lift": round(pair.lift, 4),
            "co_occurrence_fallback_used": False,
        }
    )
    return signal, diagnostics


# ---------------------------------------------------------------------------
# Behavioral hub detection
# ---------------------------------------------------------------------------


def _build_adjacency_graph(pairs) -> dict[int, set[int]]:
    """Build an undirected adjacency dict from (node_a, node_b) pairs."""
    graph: dict[int, set[int]] = defaultdict(set)
    for a_id, b_id in pairs:
        graph[a_id].add(b_id)
        graph[b_id].add(a_id)
    return graph


def _find_connected_components(
    graph: dict[int, set[int]],
    min_members: int,
) -> list[set[int]]:
    """BFS over an adjacency dict; return only components with ≥ min_members nodes."""
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
        if len(component) >= min_members:
            components.append(component)

    return components


def _compute_member_strengths(
    component_list: list[int],
    all_pairs: dict[tuple[int, int], float],
) -> dict[int, float]:
    """For each node, average its Jaccard to all other members in the component."""
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
    return strengths


def _create_hub_with_memberships(
    i: int,
    component_list: list[int],
    strengths: dict[int, float],
    removed_memberships: set[tuple[int, int]],
    hub_min_jaccard: float,
) -> tuple[int, int]:
    """Create one BehavioralHub and its BehavioralHubMembership rows; return (1, members_added)."""
    from .models import BehavioralHub, BehavioralHubMembership

    top_member_id = max(component_list, key=lambda n: strengths.get(n, 0.0))
    hub = BehavioralHub.objects.create(
        name=f"Hub {i} (anchor: content {top_member_id})",
        detection_method=BehavioralHub.METHOD_THRESHOLD,
        min_jaccard_used=hub_min_jaccard,
        member_count=0,
    )

    memberships = []
    members_added = 0
    for node in component_list:
        if (hub.hub_id, node) in removed_memberships:
            continue
        memberships.append(
            BehavioralHubMembership(
                hub=hub,
                content_item_id=node,
                membership_source=BehavioralHubMembership.SOURCE_AUTO,
                co_occurrence_strength=round(strengths.get(node, 0.0), 6),
            )
        )
        members_added += 1

    BehavioralHubMembership.objects.bulk_create(memberships, ignore_conflicts=True)
    hub.member_count = members_added
    hub.save(update_fields=["member_count", "updated_at"])
    return 1, members_added


def detect_behavioral_hubs(
    hub_min_jaccard: float = 0.15,
    hub_min_members: int = 3,
) -> tuple[int, int]:
    """Detect behavioral hubs via threshold-based connected components.

    Returns (hubs_created_or_updated, total_members_assigned).
    Preserves manual_remove_override memberships.
    """
    from .models import SessionCoOccurrencePair, BehavioralHubMembership

    pairs = SessionCoOccurrencePair.objects.filter(
        jaccard_similarity__gte=hub_min_jaccard
    ).values_list("source_content_item_id", "dest_content_item_id")

    graph = _build_adjacency_graph(pairs)
    if not graph:
        return 0, 0

    components = _find_connected_components(graph, hub_min_members)
    logger.info(
        "Hub detection: %d qualifying components (min_jaccard=%.3f, min_members=%d)",
        len(components),
        hub_min_jaccard,
        hub_min_members,
    )

    all_pairs: dict[tuple[int, int], float] = {
        (a, b): j
        for a, b, j in SessionCoOccurrencePair.objects.filter(
            jaccard_similarity__gte=hub_min_jaccard
        ).values_list(
            "source_content_item_id", "dest_content_item_id", "jaccard_similarity"
        )
    }
    removed_memberships: set[tuple[int, int]] = set(
        BehavioralHubMembership.objects.filter(
            membership_source=BehavioralHubMembership.SOURCE_MANUAL_REMOVE
        ).values_list("hub_id", "content_item_id")
    )

    total_hubs = 0
    total_members = 0
    for i, component in enumerate(components, start=1):
        component_list = sorted(component)
        strengths = _compute_member_strengths(component_list, all_pairs)
        hub_count, member_count = _create_hub_with_memberships(
            i, component_list, strengths, removed_memberships, hub_min_jaccard
        )
        total_hubs += hub_count
        total_members += member_count
    return total_hubs, total_members


# ---------------------------------------------------------------------------
# Value model scoring (post-pipeline pass)
# ---------------------------------------------------------------------------


def _extract_content_signals(suggestion: "Suggestion") -> dict[str, float]:
    """Read the five content signals from a Suggestion and its destination page."""
    dest = suggestion.destination
    return {
        "relevance": float(suggestion.score_semantic or 0.5),
        "traffic": float(getattr(dest, "content_value_score", 0.5) or 0.5),
        "freshness": float(getattr(dest, "link_freshness_score", 0.5) or 0.5),
        "authority": float(getattr(dest, "march_2026_pagerank_score", 0.5) or 0.5),
        "engagement": float(getattr(dest, "engagement_quality_score", 0.5) or 0.5),
    }


def _resolve_penalty_signal(suggestion: "Suggestion") -> float:
    """Compute the graduated penalty signal; returns 0.0 on any error."""
    from apps.pipeline.services.penalty import compute_penalty_signal

    host = suggestion.host
    host_content_id = host.pk if host is not None else None
    anchor_text = getattr(suggestion, "anchor_phrase", None) or None
    sentence_position = None
    host_sentence = getattr(suggestion, "host_sentence", None)
    if host_sentence is not None:
        sentence_position = getattr(host_sentence, "position", None)
    try:
        if host_content_id is not None:
            return compute_penalty_signal(
                host_content_id=host_content_id,
                anchor_text=anchor_text,
                sentence_position=sentence_position,
            )
        return 0.0
    except Exception:
        logger.debug(
            "Penalty signal computation failed; defaulting to 0.0", exc_info=True
        )
        return 0.0


def _extract_co_settings(settings: dict) -> tuple[int, float, bool, float, float]:
    """Extract co-occurrence algorithm settings from the scoring settings dict."""
    return (
        int(settings.get("co_occurrence_min_co_sessions", 5)),
        float(settings.get("co_occurrence_fallback_value", 0.5)),
        bool(settings.get("co_occurrence_signal_enabled", True)),
        float(settings.get("co_occurrence.llr_sigmoid_alpha", 0.1)),
        float(settings.get("co_occurrence.llr_sigmoid_beta", 10.0)),
    )


def _extract_signal_weights(settings: dict) -> dict[str, float]:
    """Extract the seven signal weights from the scoring settings dict."""
    return {
        "w_relevance": float(settings.get("w_relevance", 0.35)),
        "w_traffic": float(settings.get("w_traffic", 0.25)),
        "w_freshness": float(settings.get("w_freshness", 0.1)),
        "w_authority": float(settings.get("w_authority", 0.1)),
        "w_engagement": float(settings.get("w_engagement", 0.08)),
        "w_cooccurrence": float(settings.get("w_cooccurrence", 0.12)),
        "w_penalty": float(settings.get("w_penalty", 0.5)),
    }


def _disabled_co_signal(fallback: float) -> tuple[float, dict]:
    """Return the fallback co-signal and diagnostics used when co-occurrence is disabled."""
    return fallback, {
        "co_occurrence_signal": fallback,
        "co_session_count": 0,
        "jaccard_similarity": 0.0,
        "lift": 1.0,
        "co_occurrence_fallback_used": True,
    }


def _compute_weighted_score(
    signals: dict[str, float], weights: dict[str, float]
) -> float:
    """Apply signal weights and clamp result to [0, 1].

    signals must contain: relevance, traffic, freshness, authority, engagement, co, penalty.
    """
    raw = (
        weights["w_relevance"] * signals["relevance"]
        + weights["w_traffic"] * signals["traffic"]
        + weights["w_freshness"] * signals["freshness"]
        + weights["w_authority"] * signals["authority"]
        + weights["w_engagement"] * signals["engagement"]
        + weights["w_cooccurrence"] * signals["co"]
        - weights["w_penalty"] * signals["penalty"]
    )
    return max(0.0, min(1.0, raw))


def _build_value_model_diagnostics(
    signals: dict[str, float],
    weights: dict[str, float],
    co_diagnostics: dict,
) -> dict:
    """Assemble the per-suggestion diagnostics dict for compute_value_model_score."""
    return {
        "relevance_signal": round(signals["relevance"], 6),
        "traffic_signal": round(signals["traffic"], 6),
        "freshness_signal": round(signals["freshness"], 6),
        "authority_signal": round(signals["authority"], 6),
        "engagement_signal": round(signals["engagement"], 6),
        "penalty_signal": round(signals["penalty"], 6),
        "w_relevance": weights["w_relevance"],
        "w_traffic": weights["w_traffic"],
        "w_freshness": weights["w_freshness"],
        "w_authority": weights["w_authority"],
        "w_engagement": weights["w_engagement"],
        "w_cooccurrence": weights["w_cooccurrence"],
        "w_penalty": weights["w_penalty"],
        **co_diagnostics,
    }


def compute_value_model_score(
    suggestion: "Suggestion",
    settings: dict,
    site_max_jaccard: float = 1.0,
) -> tuple[float, dict]:
    """Compute the 7-signal value model score for a suggestion.

    Returns (score_value_model, value_model_diagnostics).
    Signals: relevance (semantic), traffic, freshness, authority, engagement,
    co-occurrence (LLR sigmoid), penalty (density/anchor/cluster).

    Signal mapping:
      relevance    → suggestion.score_semantic (embedding cosine similarity)
      traffic      → dest.content_value_score (GA4/GSC composite)
      freshness    → dest.link_freshness_score
      authority    → dest.march_2026_pagerank_score
      engagement   → dest.engagement_quality_score (GA4 behavioural quality)
      cooccurrence → SessionCoOccurrencePair LLR sigmoid (pairwise)
      penalty      → composite of density / anchor-overshoot / cluster proximity
    """
    signals = _extract_content_signals(suggestion)
    signals["penalty"] = _resolve_penalty_signal(suggestion)

    min_co_sessions, fallback, co_enabled, llr_alpha, llr_beta = _extract_co_settings(
        settings
    )
    if (
        co_enabled
        and suggestion.host is not None
        and suggestion.destination is not None
    ):
        co_signal, co_diagnostics = compute_co_occurrence_signal(
            source_id=suggestion.host.pk,
            dest_id=suggestion.destination.pk,
            min_co_sessions=min_co_sessions,
            fallback=fallback,
            site_max_jaccard=site_max_jaccard,
            llr_sigmoid_alpha=llr_alpha,
            llr_sigmoid_beta=llr_beta,
        )
    else:
        co_signal, co_diagnostics = _disabled_co_signal(fallback)

    signals["co"] = co_signal
    weights = _extract_signal_weights(settings)
    score = _compute_weighted_score(signals, weights)
    diagnostics = _build_value_model_diagnostics(signals, weights, co_diagnostics)
    return round(score, 6), diagnostics
