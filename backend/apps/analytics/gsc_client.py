"""GSC API client for FR-017 Search Outcome Attribution."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


def build_gsc_service(
    *,
    client_email: str = "",
    private_key: str = "",
    refresh_token: str = "",
    client_id: str = "",
    client_secret: str = "",
) -> Any:
    """Build a GSC service object using service account or OAuth credentials."""
    from google.oauth2 import credentials, service_account
    from googleapiclient.discovery import build

    if refresh_token and client_id and client_secret:
        # Build using OAuth credentials
        creds = credentials.Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )
    else:
        # Fall back to service account
        creds = service_account.Credentials.from_service_account_info(
            {
                "client_email": client_email,
                "private_key": private_key,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def test_gsc_access(service: Any, property_url: str) -> bool:
    """Test if we have access to the specified GSC property."""
    try:
        # Just try to get the site details. If this fails, we don't have access.
        service.sites().get(siteUrl=property_url).execute()
        return True
    except Exception as exc:
        logger.error(f"GSC access test failed for {property_url}: {exc}")
        raise


def fetch_gsc_performance_data(
    service: Any,
    property_url: str,
    start_date: date,
    end_date: date,
    dimensions: list[str] = ["date", "page"],
    excluded_country_codes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch search performance data from GSC for a specific date range.
    Returns a list of rows. Typical keys: 'keys' (list of dimensions), 'clicks', 'impressions', 'ctr', 'position'.
    """
    logger.info(
        f"Fetching GSC performance for {property_url} from {start_date} to {end_date} (dimensions: {dimensions})"
    )

    request = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "dimensions": dimensions,
        "rowLimit": 25000,
    }
    if excluded_country_codes:
        request["dimensionFilterGroups"] = [
            {
                "groupType": "and",
                "filters": [
                    {
                        "dimension": "country",
                        "operator": "notEquals",
                        "expression": country_code,
                    }
                    for country_code in excluded_country_codes
                ],
            }
        ]

    try:
        response = (
            service.searchanalytics()
            .query(siteUrl=property_url, body=request)
            .execute()
        )
        rows = response.get("rows", [])
        logger.info(f"Retrieved {len(rows)} rows from GSC API.")
        return rows
    except Exception as exc:
        logger.error(f"GSC query failed: {exc}")
        raise
