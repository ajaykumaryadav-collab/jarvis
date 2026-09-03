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


def search_web(query: str) -> str:
    """
    Search DuckDuckGo for *query* and return a text summary of top results.

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

        if not results:
            return f"No results found for '{query}'."

        logger.info("Web search for '%s' returned %d results.", query, len(results))
        header = f"Top {len(results)} results for '{query}':\n"
        return header + "\n".join(results)

    except ImportError:
        return "duckduckgo-search is not installed. Run: pip install duckduckgo-search"
    except Exception as exc:
        logger.error("Web search error: %s", exc)
        return f"Search failed: {exc}"
