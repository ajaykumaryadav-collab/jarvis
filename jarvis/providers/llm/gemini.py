"""
jarvis/providers/llm/gemini.py — Google Gemini LLM Provider
============================================================
Concrete LLMProvider using the Google Generative AI SDK.

Two-Model Routing Strategy
---------------------------
Two Gemini models are loaded:
  - Flash model (fast, cheap): handles all routine conversation + tool dispatch.
  - Pro model (smart, slow): handles complex coding/reasoning tasks delegated
    via the `delegate_to_pro` internal tool.

The Flash model decides when to delegate — it calls `delegate_to_pro(query=...)`
and the Pro model responds. This minimises API costs while preserving quality
for hard problems.

Memory Integration
------------------
Relevant past conversation turns are retrieved from the MemoryProvider and
prepended to each prompt. Both retrieval and storage are offloaded to
background threads to avoid blocking the voice event loop.

See Also
--------
ADR-005: Why Gemini was chosen over OpenAI / Ollama.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import google.generativeai as genai          # type: ignore
import google.generativeai.protos as protos  # type: ignore

import jarvis.config as config
from jarvis.providers.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = f"""You are {config.ASSISTANT_NAME}, a highly capable AI desktop assistant
created exclusively for {config.USER_NAME}. You run locally on {config.USER_NAME}'s
Windows 11 machine and have direct access to system controls via tools.

Personality & Style:
- You are efficient, intelligent, and subtly witty — think JARVIS from Iron Man.
- Keep spoken responses concise (1-3 sentences max) since they will be read aloud.
- Address the user as "{config.USER_NAME}" naturally but not excessively.
- For complex explanations, summarise verbally and offer to elaborate.

Context:
- {config.USER_NAME} is a web programmer and college student.
- Prioritise helping with coding questions, web development, and academic tasks.
- You have real-time access to system tools (volume, apps, clipboard, web search).

Safety Rules:
- NEVER execute destructive actions without explicit user confirmation.
- If a request seems risky or ambiguous, ask for clarification before acting.

Routing Instructions:
- If the user asks a complex coding question, requests heavy reasoning, or asks
  you to write a script, you MUST call the `delegate_to_pro` tool with their
  exact prompt. You are the fast Flash model — let the Pro model handle heavy lifting.
"""


# ---------------------------------------------------------------------------
# Gemini Provider
# ---------------------------------------------------------------------------

class GeminiProvider(LLMProvider):
    """Google Gemini Flash + Pro two-model LLM provider."""

    def __init__(self) -> None:
        self._dispatcher = None
        self._memory = None
        self._chat = None
        self._flash_model = None
        self._pro_model = None

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    def load(self, tool_dispatcher: Any) -> None:
        """Authenticate with Gemini, load memory, and start the chat session.

        Parameters
        ----------
        tool_dispatcher : ToolDispatcher
            Provides OS tool schemas (for Gemini) and the dispatch() method.
        """
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key or api_key == "your_gemini_api_key_here":
            raise ValueError(
                "GEMINI_API_KEY is not set. Edit your .env file with a real API key."
            )

        genai.configure(api_key=api_key)
        self._dispatcher = tool_dispatcher

        # Load the memory provider via factory to stay decoupled
        from jarvis.providers.factory import create_memory_provider
        self._memory = create_memory_provider()
        self._memory.load()

        # Build tool schemas dynamically from the dispatcher's registry
        tools = tool_dispatcher.get_gemini_tools()

        # Inject the internal model-router tool into the schema list
        router_tool = protos.FunctionDeclaration(
            name="delegate_to_pro",
            description="Delegate a complex coding or reasoning task to the advanced Pro model.",
            parameters=protos.Schema(
                type=protos.Type.OBJECT,
                properties={
                    "query": protos.Schema(
                        type=protos.Type.STRING,
                        description="The full user query to send to the Pro model.",
                    )
                },
                required=["query"],
            ),
        )
        if tools and isinstance(tools[0], protos.Tool):
            tools[0].function_declarations.append(router_tool)

        # Flash model: fast, cheap, for routine interactions
        self._flash_model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT,
            tools=tools,
            generation_config=genai.GenerationConfig(
                temperature=config.GEMINI_TEMPERATURE,
                max_output_tokens=config.GEMINI_MAX_TOKENS,
            ),
        )

        # Pro model: smarter, for complex tasks (no OS tools — reasoning only)
        self._pro_model = genai.GenerativeModel(
            model_name=config.PRO_GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT,
            generation_config=genai.GenerationConfig(
                temperature=config.GEMINI_TEMPERATURE,
            ),
        )

        self._chat = self._flash_model.start_chat(history=[])
        logger.info("Gemini provider loaded ✓ (flash: %s, pro: %s)",
                    config.GEMINI_MODEL, config.PRO_GEMINI_MODEL)

    async def process(self, user_text: str) -> str:
        """Send user text to Gemini and return the final spoken response.

        Handles RAG context injection, history trimming, tool calls (including
        model routing), and error handling.

        Parameters
        ----------
        user_text : str
            Raw transcribed command from the user.

        Returns
        -------
        str
            Final plain-text response after all tool calls are resolved.
        """
        if self._chat is None:
            raise RuntimeError("Gemini provider not loaded. Call load() first.")
        if not user_text.strip():
            return "I didn't catch that. Could you repeat?"

        logger.info("User: '%s'", user_text)

        # Retrieve relevant past turns from memory (offloaded to thread)
        context = await asyncio.to_thread(self._memory.get_relevant_context, user_text)
        augmented_prompt = f"{context}\n\nUser: {user_text}" if context else user_text

        try:
            self._trim_history()
            response = await self._chat.send_message_async(augmented_prompt)
            final_text = await self._handle_response(response)

            # Persist this turn to memory in the background — do not block TTS
            asyncio.create_task(
                asyncio.to_thread(self._memory.add_turn, user_text, final_text)
            )
            return final_text

        except Exception as exc:
            logger.error("Gemini API error: %s", exc)
            return f"I encountered an error talking to Gemini: {exc}"

    def reset_history(self) -> None:
        """Clear the chat history and start a fresh session."""
        if self._chat:
            self._chat.history.clear()
        logger.info("Conversation history cleared.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _trim_history(self) -> None:
        """Enforce sliding window on chat history to prevent context overflow."""
        if not self._chat:
            return
        # Each turn = user message + model response (2 items)
        max_items = config.CONVERSATION_HISTORY_LIMIT * 2
        if len(self._chat.history) > max_items:
            self._chat.history = self._chat.history[-max_items:]

    async def _handle_response(self, response) -> str:
        """Recursively resolve tool calls and return the final text response.

        Parameters
        ----------
        response : GenerateContentResponse
            The raw Gemini response object, which may contain tool calls.

        Returns
        -------
        str
            Final text response with all tool calls resolved.
        """
        # Collect all function calls from this response
        tool_calls = [
            part.function_call
            for part in response.parts
            if hasattr(part, "function_call") and part.function_call.name
        ]

        if not tool_calls:
            # Pure text response — return it directly
            text = response.text.strip() if response.text else ""
            logger.info("JARVIS: '%s'", text[:120])
            return text or "Done."

        # Dispatch all tool calls (supports parallel calls in a single turn)
        function_responses = []
        for fc in tool_calls:
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}
            logger.info("Tool call: %s(%s)", tool_name, tool_args)

            if tool_name == "delegate_to_pro":
                # Route to the Pro model for complex reasoning
                result = await self._delegate_to_pro(tool_args.get("query", ""))
            else:
                # Normal OS tool — dispatched synchronously inside the async loop
                result = self._dispatcher.dispatch(tool_name, tool_args)

            logger.info("Tool result: %s → %s", tool_name, str(result)[:200])
            function_responses.append(
                protos.Part(
                    function_response=protos.FunctionResponse(
                        name=tool_name,
                        response={"result": str(result)},
                    )
                )
            )

        # Send all tool results back to Gemini in a single follow-up turn
        follow_up = await self._chat.send_message_async(
            protos.Content(parts=function_responses)
        )
        return await self._handle_response(follow_up)

    async def _delegate_to_pro(self, query: str) -> str:
        """Send a query to the Pro model and return its response.

        Parameters
        ----------
        query : str
            The user's complex query to be handled by the Pro model.

        Returns
        -------
        str
            The Pro model's text response.
        """
        logger.info("Routing query to Pro model: '%s'", query[:80])
        try:
            context = await asyncio.to_thread(self._memory.get_relevant_context, query)
            pro_prompt = f"{context}\n\nUser: {query}" if context else query
            pro_response = await self._pro_model.generate_content_async(pro_prompt)
            return pro_response.text
        except Exception as e:
            logger.error("Pro model error: %s", e)
            return f"The advanced model encountered an error: {e}"
