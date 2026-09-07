"""
jarvis/tools/web_search.py — Web Search Tool
=============================================
Performs a web search using DuckDuckGo (no API key required).
Falls back to Wikipedia if DuckDuckGo is rate-limited.

Returns a concise, spoken-friendly text summary of the top 3 results.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MAX_RESULTS = 3
MAX_BODY_CHARS = 200  # Truncate snippets so spoken response stays brief


def _search_fallback(query: str) -> str:
    """Fallback to the Wikipedia OpenSearch API when DuckDuckGo is rate-limited.

    Parameters
    ----------
    query : str
        The search query.

    Returns
    -------
    str
        A brief Wikipedia summary, or empty string on failure.
    """
    try:
        import httpx  # type: ignore

        headers = {"User-Agent": "JarvisAssistant/1.0 (github.com/doomsday-the/Jarvis)"}
        search_url = "https://en.wikipedia.org/w/api.php"

        # Step 1: Find matching article titles
        search_res = httpx.get(
            search_url,
            params={"action": "opensearch", "search": query, "limit": 3, "format": "json"},
            headers=headers, timeout=5.0,
        )
        if search_res.status_code != 200:
            return ""

        data = search_res.json()
        titles = data[1] if len(data) > 1 else []
        links = data[3] if len(data) > 3 else []
        if not titles:
            return ""

        top_title = titles[0]

        # Step 2: Fetch the article extract
        ext_res = httpx.get(
            search_url,
            params={
                "action": "query", "prop": "extracts", "exintro": True,
                "explaintext": True, "titles": top_title, "format": "json",
            },
            headers=headers, timeout=5.0,
        )
        if ext_res.status_code == 200:
            pages = ext_res.json().get("query", {}).get("pages", {})
            for page in pages.values():
                extract = page.get("extract", "").strip()
                if extract:
                    if len(extract) > MAX_BODY_CHARS * 2:
                        extract = extract[:MAX_BODY_CHARS * 2] + "..."
                    link = links[0] if links else ""
                    return f"From {top_title}: {extract} ({link})"

        return f"Found topic '{top_title}' ({links[0] if links else ''})."

    except Exception as e:
        logger.warning("Wikipedia fallback failed: %s", e)
    return ""


def search_web(query: str) -> str:
    """Search DuckDuckGo for *query* and return a text summary of top results.

    Falls back to Wikipedia if DuckDuckGo is rate-limited or unavailable.

    Parameters
    ----------
    query : str
        The search query string.

    Returns
    -------
    str
        Formatted search results as a single multi-line string.
    """
    if not query.strip():
        return "Please provide a search query."

    # Primary: DuckDuckGo
    try:
        from duckduckgo_search import DDGS  # type: ignore

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=MAX_RESULTS):
                title = r.get("title", "No title")
                body = r.get("body", "")
                href = r.get("href", "")
                if len(body) > MAX_BODY_CHARS:
                    body = body[:MAX_BODY_CHARS] + "..."
                results.append(f"- {title}: {body} ({href})")

        if results:
            logger.info("DuckDuckGo search for '%s' returned %d results.", query, len(results))
            return f"Top {len(results)} results for '{query}':\n" + "\n".join(results)

    except ImportError:
        logger.warning("duckduckgo-search is not installed.")
    except Exception as exc:
        logger.warning("DuckDuckGo search error: %s — trying fallback.", exc)

    # Fallback: Wikipedia
    fallback_result = _search_fallback(query)
    if fallback_result:
        logger.info("Wikipedia fallback succeeded for '%s'.", query)
        return fallback_result

    return f"Search for '{query}' returned no results or was temporarily unavailable."
