"""
jarvis/providers/memory/base.py — Abstract Memory / RAG Provider
================================================================
Defines the interface every memory/RAG implementation must satisfy.

To add a new memory provider (e.g., Qdrant, SQLite, Pinecone):
  1. Create `jarvis/providers/memory/qdrant.py`
  2. Subclass `MemoryProvider` and implement all abstract methods.
  3. Register it in `jarvis/providers/factory.py`.
  4. Set `MEMORY_PROVIDER = "qdrant"` in `jarvis/config.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class MemoryProvider(ABC):
    """Abstract interface for conversation memory / RAG storage.

    Implementations store conversation turns as vector embeddings and
    retrieve semantically similar context to augment new LLM prompts.

    All I/O methods should be safe to call from background threads since
    the orchestrator runs them via `asyncio.to_thread()` to avoid blocking
    the voice loop.
    """

    @abstractmethod
    def load(self) -> None:
        """Connect to the storage backend and initialise the collection.

        Must be called once at startup. Must not raise on empty storage
        (i.e., first run should succeed silently).
        """
        ...

    @abstractmethod
    def add_turn(self, user_text: str, assistant_response: str) -> None:
        """Persist one conversation turn to the memory store.

        Parameters
        ----------
        user_text : str
            The user's transcribed command for this turn.
        assistant_response : str
            JARVIS's spoken response for this turn.
        """
        ...

    @abstractmethod
    def get_relevant_context(self, query: str, n_results: int = 3) -> str:
        """Retrieve semantically similar past turns for a given query.

        Parameters
        ----------
        query : str
            The current user query (used to compute similarity).
        n_results : int
            Maximum number of past turns to include in the context.

        Returns
        -------
        str
            A formatted string of relevant past turns ready to be prepended
            to the LLM prompt, or an empty string if no memory exists.
        """
        ...
