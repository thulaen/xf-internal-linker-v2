import logging
import time
import requests
from django.conf import settings
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class XenForoAPIClient:
    """
    Read-only client for the XenForo REST API.
    Used to fetch threads, posts, and resources for content indexing.
    """

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or self._get_base_url()).rstrip("/")
        self.api_key = api_key or self._get_api_key()

        if not self.base_url:
            raise ValueError(
                "XenForo API base URL is missing (check XENFORO_BASE_URL setting)."
            )
        if not self.api_key:
            raise ValueError(
                "XenForo API key is missing (check XENFORO_API_KEY setting)."
            )

    def _get_base_url(self) -> str:
        return getattr(settings, "XENFORO_BASE_URL", "")

    def _get_api_key(self) -> str:
        return getattr(settings, "XENFORO_API_KEY", "")

    def _get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Internal helper for GET requests with exponential backoff retry."""
        url = f"{self.base_url}/api/{endpoint.lstrip('/')}"
        headers = {
            "XF-Api-Key": self.api_key,
            "Accept": "application/json",
        }

        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                last_exc = e
                if attempt < max_retries - 1:
                    wait = 2**attempt
                    logger.warning(
                        "XenForo API request failed (attempt %d/%d): %s — retrying in %ds",
                        attempt + 1,
                        max_retries,
                        e,
                        wait,
                    )
                    time.sleep(wait)

        logger.error(
            "XenForo API request failed after %d attempts: %s (URL: %s)",
            max_retries,
            last_exc,
            url,
        )
        raise last_exc

    def verify_api_key(self) -> bool:
        """Check if the API key is valid by calling a simple endpoint."""
        try:
            self._get("index/")
            return True
        except Exception:
            return False

    def get_threads(self, node_id: int, page: int = 1) -> Dict[str, Any]:
        """Fetch a page of threads from a specific forum node."""
        return self._get("threads/", params={"node_id": node_id, "page": page})

    def get_thread(self, thread_id: int) -> Dict[str, Any]:
        """Fetch a single thread by ID."""
        return self._get(f"threads/{thread_id}/")

    def get_posts(self, thread_id: int, page: int = 1) -> Dict[str, Any]:
        """Fetch a page of posts from a specific thread."""
        return self._get("posts/", params={"thread_id": thread_id, "page": page})

    def get_post(self, post_id: int) -> Dict[str, Any]:
        """Fetch a single post by ID."""
        return self._get(f"posts/{post_id}/")

    def get_resources(self, category_id: int, page: int = 1) -> Dict[str, Any]:
        """Fetch a page of resources from a specific category."""
        return self._get(
            "resources/", params={"resource_category_id": category_id, "page": page}
        )

    def get_resource_updates(self, resource_id: int) -> Dict[str, Any]:
        """Fetch updates for a specific resource."""
        # Note: endpoint structure might vary based on XF version/plugin
        return self._get(f"resources/{resource_id}/updates")
