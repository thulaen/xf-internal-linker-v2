import httpx
import logging

logger = logging.getLogger(__name__)

DOCS_SEARCH_URL = "http://localhost:3000/search-doc.json"

def fetch_docs_search(query: str):
    """
    Fetches the Docusaurus search index and performs a naive string search.
    """
    if not query:
        return []

    query_lower = query.lower()
    results = []

    try:
        # Use a short timeout since it's an internal container
        response = httpx.get(DOCS_SEARCH_URL, timeout=3.0)
        response.raise_for_status()
        docs = response.json().get("documents", [])

        # The search-doc.json from Docusaurus lunr looks like:
        # {"documents": [{"id": 0, "title": "...", "content": "...", "route": "..."}, ...]}
        
        for doc in docs:
            title = doc.get("title", "").lower()
            content = doc.get("content", "").lower()
            if query_lower in title or query_lower in content:
                # Add highlighting or just return the doc
                results.append({
                    "id": doc.get("id"),
                    "title": doc.get("title"),
                    "url": doc.get("route", ""), # docusaurus lunr usually uses 'route'
                    "snippet": doc.get("content", "")[:150] + "..." # basic snippet
                })
        
        return results

    except Exception as e:
        logger.error(f"Failed to fetch or search docs index: {e}")
        return []

def federated_search(query: str):
    """
    Combines internal Django search with Docusaurus documentation search.
    """
    # Stub for internal database search
    internal_results = [
        # {"id": 1, "title": "Internal App Record matching query", "type": "record"}
    ]

    docs_results = fetch_docs_search(query)

    return {
        "internal_results": internal_results,
        "documentation_results": docs_results
    }
