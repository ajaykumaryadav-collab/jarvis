"""
jarvis/providers/llm/base.py — Abstract LLM Provider
=====================================================
Defines the interface every large language model implementation must satisfy.

To add a new LLM provider (e.g., OpenAI, Ollama, Anthropic):
  1. Create `jarvis/providers/llm/openai.py`
  2. Subclass `LLMProvider` and implement all abstract methods.
  3. Register it in `jarvis/providers/factory.py`.
  4. Set `LLM_PROVIDER = "openai"` in `jarvis/config.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Abstract interface for the LLM / conversational AI backend.

    The LLM provider is responsible for:
      - Maintaining multi-turn conversation history.
      - Accepting a tool dispatcher so it can invoke OS-level tools.
      - Returning a plain text response string to the caller.

    The agent orchestrator in `jarvis/core/agent.py` calls only the
    methods defined here, guaranteeing that swapping providers requires
    no changes to the orchestrator.
    """

    @abstractmethod
    def load(self, tool_dispatcher: Any) -> None:
        """Authenticate with the LLM API and prepare the chat session.

        Parameters
        ----------
        tool_dispatcher : ToolDispatcher
            The tool dispatcher to invoke when the LLM requests a tool call.
            Passed here rather than at construction to avoid circular imports.

        Raises on missing API key or connection failure.
        """
        ...

    @abstractmethod
    async def process(self, user_text: str) -> str:
        """Send user text to the LLM and return its response.

        This is the main entry point for each conversational turn.
        Implementations must handle:
          - Injecting relevant memory/RAG context into the prompt.
          - Multi-turn history management (sliding window trim).
          - Tool call detection and dispatch.
          - Error handling and timeouts.

        Parameters
        ----------
        user_text : str
            The raw transcribed user command.

        Returns
        -------
        str
            The final plain-text response from the LLM, after all tool
            calls have been resolved.
        """
        ...

    @abstractmethod
    def reset_history(self) -> None:
        """Clear all conversation history and start a fresh session.

        Called on repeated errors or when the user explicitly requests a
        fresh start.
        """
        ...
