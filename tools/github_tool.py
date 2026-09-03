"""
tools/github_tool.py — GitHub Repository Analysis (Phase 2 Stub)
=================================================================
This module is a stub for Phase 2 GitHub integration. Currently it
returns an informative placeholder so that Gemini can still call it
without crashing JARVIS.

Phase 2 implementation will:
  - Authenticate via GitHub PAT from .env
  - List user repositories, recent commits, open issues, and PRs
  - Analyse repository structure and README
  - Provide coding suggestions based on repo content

To activate: set GITHUB_PAT in .env and implement the functions below.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def github_info(repo: str = "", action: str = "summary") -> str:
    """
    [PHASE 2 STUB] Retrieve GitHub repository information.

    Parameters
    ----------
    repo : str
        Repository name in "owner/repo" format (e.g., "AjayYadav/my-project").
    action : str
        Action to perform: "summary", "issues", "commits", "prs".

    Returns
    -------
    str
        Repository information or stub message.
    """
    pat = os.environ.get("GITHUB_PAT", "").strip()
    if not pat:
        return (
            "GitHub integration is not yet configured. "
            "Set GITHUB_PAT in your .env file to enable Phase 2 features. "
            f"Requested: {action} for '{repo or 'unknown repo'}'."
        )

    # Phase 2: implement with PyGithub or httpx + GitHub REST API
    logger.info("[STUB] github_info called: repo=%s, action=%s", repo, action)
    return f"[Phase 2 Stub] GitHub {action} for '{repo}' — not yet implemented."
