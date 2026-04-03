"""GSC API client for FR-017 Search Outcome Attribution."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build, Resource

logger = logging.getLogger(__name__)


def build_gsc_service(*, client_email: str, private_key: str) -> Resource:
    """Build a GSC service object using service account credentials."""
    credentials = service_account.Credentials.from_service_account_info(
        {
            "client_email": client_email,
            "private_key": private_key,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )
    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)


def test_gsc_access(service: Resource, property_url: str) -> bool:
    """Test if we have access to the specified GSC property."""
    try:
        # Just try to get the site details. If this fails, we don't have access.
        service.sites().get(siteUrl=property_url).execute()
        return True
    except Exception as exc:
        logger.error(f"GSC access test failed for {property_url}: {exc}")
        raise


def fetch_gsc_performance_data(
    service: Resource, 
    property_url: str, 
    start_date: date, 
    end_date: date,
    dimensions: list[str] = ["date", "page", "query"]
) -> list[dict[str, Any]]:
    """
    Fetch search performance data from GSC.
    Returns a list of rows with keys: page, query, clicks, impressions, ctr, position.
    """
    request = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "dimensions": dimensions,
        "rowLimit": 25000,
    }
    
    response = service.searchanalytics().query(siteUrl=property_url, body=request).execute()
    return response.get("rows", [])
