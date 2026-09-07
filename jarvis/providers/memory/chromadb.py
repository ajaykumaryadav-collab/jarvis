"""
jarvis/providers/memory/chromadb.py — ChromaDB RAG Memory Provider
===================================================================
Concrete MemoryProvider using ChromaDB for persistent, semantic conversation
memory. Embeddings are generated locally via the bundled all-MiniLM-L6-v2
ONNX model (no GPU required).

Data is stored in the directory specified by config.CHROMA_DB_PATH.
All public methods are thread-safe and designed to be called from
asyncio.to_thread() in the main event loop.

See Also
--------
ADR-006: Why ChromaDB was chosen over Pinecone / SQLite.
"""

from __future__ import annotations

import logging
import time

from jarvis.providers.memory.base import MemoryProvider
import jarvis.config as config

logger = logging.getLogger(__name__)


class ChromaDBMemoryProvider(MemoryProvider):
    """Persistent semantic memory backed by ChromaDB."""

    def __init__(self) -> None:
        self._client = None
        self._collection = None

    # ------------------------------------------------------------------
    # MemoryProvider interface
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Connect to ChromaDB and get or create the conversation collection."""
        try:
            import chromadb  # type: ignore
            self._client = chromadb.PersistentClient(path=str(config.CHROMA_DB_PATH))
            self._collection = self._client.get_or_create_collection(
                name="jarvis_memory"
            )
            logger.info("ChromaDB memory loaded ✓ (%d turns stored)", self._collection.count())
        except Exception as e:
            logger.error("Failed to load ChromaDB: %s", e)
            self._client = None
            self._collection = None

    def add_turn(self, user_text: str, assistant_response: str) -> None:
        """Persist one conversation turn as a vector embedding.

        Parameters
        ----------
        user_text : str
            The user's transcribed command.
        assistant_response : str
            JARVIS's spoken response.
        """
        if not self._collection:
            return

        # Store both sides of the conversation as a single document so
        # semantic search can retrieve context for either side.
        document = f"User: {user_text}\nJARVIS: {assistant_response}"
        doc_id = str(time.time())  # Timestamp as a unique ID

        try:
            self._collection.add(
                documents=[document],
                metadatas=[{"role": "conversation_turn"}],
                ids=[doc_id],
            )
            logger.debug("Saved conversation turn to memory.")
        except Exception as e:
            logger.error("Failed to add turn to memory: %s", e)

    def get_relevant_context(self, query: str, n_results: int = 3) -> str:
        """Retrieve semantically similar past turns for a given query.

        Parameters
        ----------
        query : str
            The current user prompt used for semantic similarity search.
        n_results : int
            Maximum number of past turns to retrieve.

        Returns
        -------
        str
            A formatted string of relevant context, ready to be prepended
            to the LLM prompt. Empty string if no memory exists.
        """
        if not self._collection or self._collection.count() == 0:
            return ""

        try:
            # Guard against requesting more results than we have stored
            results_to_fetch = min(n_results, self._collection.count())
            if results_to_fetch == 0:
                return ""

            results = self._collection.query(
                query_texts=[query],
                n_results=results_to_fetch,
            )

            documents = results.get("documents", [[]])[0]
            if not documents:
                return ""

            context = "Previous Conversation Context:\n"
            for doc in documents:
                context += f"- {doc}\n"
            return context

        except Exception as e:
            logger.error("Failed to retrieve memory context: %s", e)
            return ""
