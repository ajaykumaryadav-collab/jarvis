"""
tools/web_search.py — DuckDuckGo Web Search
============================================
Performs a web search using the duckduckgo-search library (no API key).
Returns a concise summary of the top 3 results suitable for spoken delivery.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MAX_RESULTS = 3
MAX_BODY_CHARS = 200  # Truncate body text so spoken response stays brief


def _search_fallback(query: str) -> str:
    """Fallback search using Wikipedia when DuckDuckGo is rate-limited."""
    try:
        import httpx  # type: ignore

        headers = {"User-Agent": "JarvisAssistant/1.0 (contact: ajay.jarvis.app@gmail.com)"}
        # 1. Search for matching titles
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "opensearch",
            "search": query,
            "limit": 3,
            "format": "json",
        }
        res = httpx.get(search_url, params=search_params, headers=headers, timeout=5.0)
        if res.status_code == 200:
            data = res.json()
            titles = data[1] if len(data) > 1 else []
            links = data[3] if len(data) > 3 else []
            if titles:
                top_title = titles[0]
                # 2. Fetch extract for the top title
                ext_params = {
                    "action": "query",
                    "prop": "extracts",
                    "exintro": True,
                    "explaintext": True,
                    "titles": top_title,
                    "format": "json",
                }
                ext_res = httpx.get(search_url, params=ext_params, headers=headers, timeout=5.0)
                if ext_res.status_code == 200:
                    pages = ext_res.json().get("query", {}).get("pages", {})
                    for page in pages.values():
                        extract = page.get("extract", "").strip()
                        if extract:
                            if len(extract) > MAX_BODY_CHARS * 2:
                                extract = extract[:MAX_BODY_CHARS * 2] + "…"
                            link = links[0] if links else ""
                            return f"From {top_title}: {extract} ({link})"

                return f"Found topic '{top_title}' ({links[0] if links else ''})."
    except Exception as e:
        logger.warning("Search fallback failed: %s", e)
    return ""


def search_web(query: str) -> str:
    """
    Search DuckDuckGo for *query* and return a text summary of top results.
    Falls back to Wikipedia if DuckDuckGo is rate-limited.

    Parameters
    ----------
    query : str
        The search query string.

    Returns
    -------
    str
        Formatted search results as a single string.
    """
    if not query.strip():
        return "Please provide a search query."

    # 1. Try DuckDuckGo
    try:
        from duckduckgo_search import DDGS  # type: ignore

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=MAX_RESULTS):
                title = r.get("title", "No title")
                body = r.get("body", "")
                href = r.get("href", "")
                if len(body) > MAX_BODY_CHARS:
                    body = body[:MAX_BODY_CHARS] + "…"
                results.append(f"• {title}: {body} ({href})")

        if results:
            logger.info("Web search for '%s' returned %d results.", query, len(results))
            header = f"Top {len(results)} results for '{query}':\n"
            return header + "\n".join(results)

    except ImportError:
        logger.warning("duckduckgo-search is not installed.")
    except Exception as exc:
        logger.warning("DuckDuckGo search error: %s — trying fallback.", exc)

    # 2. Resilient Fallback
    fallback_result = _search_fallback(query)
    if fallback_result:
        logger.info("Web search fallback succeeded for '%s'", query)
        return fallback_result

    return f"Search for '{query}' returned no results or was temporarily rate-limited."

