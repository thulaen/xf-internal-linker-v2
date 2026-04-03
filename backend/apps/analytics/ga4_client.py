"""Small GA4 Data API helper for FR-016 read access."""

from __future__ import annotations

GA4_READONLY_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"


def _normalize_private_key(private_key: str) -> str:
    normalized = (private_key or "").strip()
    if "\\n" in normalized:
        normalized = normalized.replace("\\n", "\n")
    return normalized


def build_ga4_data_service(
    *, 
    property_id: str, 
    project_id: str = "", 
    client_email: str = "", 
    private_key: str = "",
    refresh_token: str = "",
    client_id: str = "",
    client_secret: str = ""
):
    from google.oauth2 import service_account, credentials
    from googleapiclient.discovery import build

    if refresh_token and client_id and client_secret:
        # Build using OAuth credentials
        creds = credentials.Credentials(
            token=None,  # Will be refreshed automatically
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=[GA4_READONLY_SCOPE],
        )
    else:
        # Fall back to service account
        creds = service_account.Credentials.from_service_account_info(
            {
                "type": "service_account",
                "project_id": project_id,
                "private_key_id": "gui-saved-fr016",
                "private_key": _normalize_private_key(private_key),
                "client_email": client_email,
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=[GA4_READONLY_SCOPE],
        )
    return build("analyticsdata", "v1beta", credentials=creds, cache_discovery=False)


def test_ga4_data_api_access(*, service, property_id: str) -> dict:
    return (
        service.properties()
        .runReport(
            property=f"properties/{property_id}",
            body={
                "dateRanges": [{"startDate": "7daysAgo", "endDate": "today"}],
                "dimensions": [{"name": "date"}],
                "metrics": [{"name": "eventCount"}],
                "limit": 1,
            },
        )
        .execute()
    )
