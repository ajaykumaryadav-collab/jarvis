"""
core/agent.py — Gemini Intelligence Engine
===========================================
Manages the conversation loop with the Gemini API, including:
  - Persistent multi-turn chat history (rolling window)
  - Tool/function-calling schema registration
  - Parsing Gemini's tool_call responses and forwarding to tool_dispatcher
  - Async execution and parallel tool calling
  - RAG Memory integration and Model Routing
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import google.generativeai as genai  # type: ignore
import google.generativeai.protos as protos  # type: ignore

import config
from core.memory import Memory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = f"""You are {config.ASSISTANT_NAME}, a highly capable AI desktop assistant
created exclusively for {config.USER_NAME}. You run locally on {config.USER_NAME}'s
Windows 11 machine and have direct access to system controls via tools.

Personality & Style:
- You are efficient, intelligent, and subtly witty — think JARVIS from Iron Man.
- Keep spoken responses concise (1–3 sentences max) since they will be read aloud.
- Address the user as "{config.USER_NAME}" naturally but not excessively.
- For complex explanations, summarise verbally and offer to elaborate.

Context:
- {config.USER_NAME} is a web programmer and college student.
- Prioritise helping with coding questions, web development, and academic tasks.
- You have real-time access to system tools (volume, apps, clipboard, web search).

Safety Rules:
- NEVER execute destructive actions without explicit user confirmation.
- If a request seems risky or ambiguous, ask for clarification before acting.
- You cannot access files or the filesystem beyond clipboard unless given a tool to do so.

Routing Instructions:
- If the user asks a complex coding question, requests heavy reasoning, or asks you to write a script, you MUST call the `delegate_to_pro` tool with their exact prompt. You are the fast flash model. Let the pro model handle the heavy lifting.
"""


# ---------------------------------------------------------------------------
# Agent Class
# ---------------------------------------------------------------------------

class Agent:
    """Gemini-powered conversational agent with tool-calling support."""

    def __init__(self, tool_dispatcher) -> None:
        self._dispatcher = tool_dispatcher
        self._memory = Memory()
        self._chat = None
        self._model = None
        self._pro_model = None

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Authenticate with Gemini API, load memory, and start chat."""
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key or api_key == "your_gemini_api_key_here":
            raise ValueError(
                "GEMINI_API_KEY is not set. Edit your .env file with a real API key."
            )

        genai.configure(api_key=api_key)
        self._memory.load()

        # Build tools dynamically from the dispatcher
        tools = self._dispatcher.get_gemini_tools()
        
        # Add the router tool
        router_tool = protos.FunctionDeclaration(
            name="delegate_to_pro",
            description="Delegate complex coding or reasoning tasks to the advanced Pro model.",
            parameters=protos.Schema(
                type=protos.Type.OBJECT,
                properties={
                    "query": protos.Schema(
                        type=protos.Type.STRING,
                        description="The full user query to send to the Pro model."
                    )
                },
                required=["query"],
            )
        )
        
        # Extend the tools list with the router tool
        if tools and isinstance(tools[0], protos.Tool):
            tools[0].function_declarations.append(router_tool)

        self._model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT,
            tools=tools,
            generation_config=genai.GenerationConfig(
                temperature=config.GEMINI_TEMPERATURE,
                max_output_tokens=config.GEMINI_MAX_TOKENS,
            ),
        )
        
        self._pro_model = genai.GenerativeModel(
            model_name=config.PRO_GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT,
            # Pro model does not get OS tools in this architecture, only reasoning capability
            generation_config=genai.GenerationConfig(
                temperature=config.GEMINI_TEMPERATURE,
            ),
        )

        self._chat = self._model.start_chat(history=[])
        logger.info("Gemini agent loaded ✓ (model: %s)", config.GEMINI_MODEL)

    # ------------------------------------------------------------------
    # Main Process Method
    # ------------------------------------------------------------------

    async def process(self, user_text: str) -> str:
        """
        Send *user_text* to Gemini and handle the response.
        """
        if self._chat is None:
            raise RuntimeError("Agent not loaded. Call load() first.")

        if not user_text.strip():
            return "I didn't catch that. Could you repeat?"

        logger.info("User: '%s'", user_text)
        
        # Inject RAG Context (run in thread to avoid blocking event loop)
        context = await asyncio.to_thread(self._memory.get_relevant_context, user_text)
        augmented_prompt = f"{context}\n\nUser: {user_text}" if context else user_text

        try:
            # Enforce sliding window history
            self._trim_history()
            
            response = await self._chat.send_message_async(augmented_prompt)
            final_text = await self._handle_response(response)
            
            # Save to RAG memory in the background so it doesn't block TTS
            asyncio.create_task(asyncio.to_thread(self._memory.add_turn, user_text, final_text))
            return final_text
        except Exception as exc:
            logger.error("Gemini API error: %s", exc)
            return f"I encountered an error talking to Gemini: {exc}"

    def _trim_history(self):
        """Keep chat history within the CONVERSATION_HISTORY_LIMIT."""
        if not self._chat:
            return
        # A turn is usually a user message + model response (2 parts)
        max_items = config.CONVERSATION_HISTORY_LIMIT * 2
        if len(self._chat.history) > max_items:
            self._chat.history = self._chat.history[-max_items:]

    async def _handle_response(self, response) -> str:
        """Recursively handle tool calls, supporting parallel execution."""
        tool_calls = []
        for part in response.parts:
            if hasattr(part, "function_call") and part.function_call.name:
                tool_calls.append(part.function_call)

        if tool_calls:
            function_responses = []
            for fc in tool_calls:
                tool_name = fc.name
                tool_args = dict(fc.args) if fc.args else {}
                logger.info("Gemini requested tool: %s(%s)", tool_name, tool_args)
                
                # Check for Model Router
                if tool_name == "delegate_to_pro":
                    logger.info("Routing query to Pro model...")
                    query = tool_args.get("query", "")
                    try:
                        # Send context to pro model too
                        context = self._memory.get_relevant_context(query)
                        pro_prompt = f"{context}\n\nUser: {query}" if context else query
                        pro_response = await self._pro_model.generate_content_async(pro_prompt)
                        result = pro_response.text
                    except Exception as e:
                        logger.error(f"Pro model failed: {e}")
                        result = f"Error from Pro model: {e}"
                else:
                    # Normal OS tool dispatch
                    # (Safety gate handles confirmation interactively)
                    # We run this sync inside async - in a full rewrite we might run this in an executor
                    result = self._dispatcher.dispatch(tool_name, tool_args)
                
                logger.info("Tool %s result: %s", tool_name, str(result)[:200])
                
                function_responses.append(
                    protos.Part(
                        function_response=protos.FunctionResponse(
                            name=tool_name,
                            response={"result": str(result)},
                        )
                    )
                )

            # Send ALL tool results back at once
            follow_up = await self._chat.send_message_async(protos.Content(parts=function_responses))
            return await self._handle_response(follow_up)

        # Pure text response
        text = response.text.strip() if response.text else ""
        if not text:
            text = "Done."
        logger.info("JARVIS: '%s'", text[:120])
        return text

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def reset_history(self) -> None:
        """Clear conversation history (start fresh)."""
        if self._chat:
            self._chat.history.clear()
        logger.info("Conversation history cleared.")
