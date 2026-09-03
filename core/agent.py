"""
core/agent.py — Gemini Intelligence Engine
===========================================
Manages the conversation loop with the Gemini API, including:
  - Persistent multi-turn chat history (rolling window)
  - Tool/function-calling schema registration
  - Parsing Gemini's tool_call responses and forwarding to tool_dispatcher

Architecture
------------
User utterance
    → agent.process(text)
        → Gemini API (with tool schemas + history)
            → text response       → return to caller
            → tool_call response  → tool_dispatcher.dispatch()
                                  → result back to Gemini
                                  → final text response → return to caller
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini Tool Schemas
# ---------------------------------------------------------------------------
# Each entry maps to a function in tools/. Gemini uses these to decide when
# to call a tool instead of generating a text response.

TOOL_SCHEMAS = [
    {
        "name": "get_volume",
        "description": "Get the current system audio volume level (0–100).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "set_volume",
        "description": "Set the system audio volume to a specific level.",
        "parameters": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "integer",
                    "description": "Volume level from 0 (mute) to 100 (max).",
                }
            },
            "required": ["level"],
        },
    },
    {
        "name": "mute_volume",
        "description": "Mute the system audio.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "unmute_volume",
        "description": "Unmute the system audio.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "launch_app",
        "description": "Launch an application by its friendly name (e.g., 'VS Code', 'Chrome', 'Spotify').",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Friendly application name."}
            },
            "required": ["name"],
        },
    },
    {
        "name": "close_app",
        "description": "Close/kill a running application by its process name.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Friendly app name or process name."}
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_running_apps",
        "description": "List currently running applications.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_system_info",
        "description": "Get CPU usage, RAM stats, and GPU VRAM/temperature.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_clipboard",
        "description": "Read and return the current clipboard text content.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "write_clipboard",
        "description": "Write text to the Windows clipboard.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to write to clipboard."}
            },
            "required": ["text"],
        },
    },
    {
        "name": "search_web",
        "description": "Search the web using DuckDuckGo and return a summary of the top results.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."}
            },
            "required": ["query"],
        },
    },
]

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
"""


# ---------------------------------------------------------------------------
# Agent Class
# ---------------------------------------------------------------------------

class Agent:
    """Gemini-powered conversational agent with tool-calling support."""

    def __init__(self, tool_dispatcher) -> None:
        """
        Parameters
        ----------
        tool_dispatcher : ToolDispatcher
            Instance used to execute tool calls returned by Gemini.
        """
        self._dispatcher = tool_dispatcher
        self._client = None
        self._chat = None

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Authenticate with Gemini API and start a new chat session."""
        import google.generativeai as genai  # type: ignore

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key or api_key == "your_gemini_api_key_here":
            raise ValueError(
                "GEMINI_API_KEY is not set. Edit your .env file with a real API key."
            )

        genai.configure(api_key=api_key)

        # Build Gemini-compatible tool declarations
        tools = self._build_tools()

        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT,
            tools=tools,
            generation_config=genai.GenerationConfig(
                temperature=config.GEMINI_TEMPERATURE,
                max_output_tokens=config.GEMINI_MAX_TOKENS,
            ),
        )
        self._chat = model.start_chat(history=[])
        logger.info("Gemini agent loaded ✓ (model: %s)", config.GEMINI_MODEL)

    def _build_tools(self) -> list:
        """Convert TOOL_SCHEMAS dicts into Gemini FunctionDeclaration objects."""
        import google.generativeai.types as genai_types  # type: ignore
        from google.generativeai import protos  # type: ignore

        declarations = []
        for schema in TOOL_SCHEMAS:
            declarations.append(
                protos.FunctionDeclaration(
                    name=schema["name"],
                    description=schema["description"],
                    parameters=protos.Schema(
                        type=protos.Type.OBJECT,
                        properties={
                            k: protos.Schema(
                                type=protos.Type.STRING
                                if v.get("type") == "string"
                                else protos.Type.INTEGER,
                                description=v.get("description", ""),
                            )
                            for k, v in schema["parameters"]
                            .get("properties", {})
                            .items()
                        },
                        required=schema["parameters"].get("required", []),
                    ),
                )
            )
        return [protos.Tool(function_declarations=declarations)]

    # ------------------------------------------------------------------
    # Main Process Method
    # ------------------------------------------------------------------

    def process(self, user_text: str) -> str:
        """
        Send *user_text* to Gemini and handle the response.

        Handles multi-turn tool calling: if Gemini returns a function call,
        the tool is dispatched, the result is fed back, and the cycle
        repeats until a final text response is generated.

        Returns the final spoken response string.
        """
        if self._chat is None:
            raise RuntimeError("Agent not loaded. Call load() first.")

        if not user_text.strip():
            return "I didn't catch that. Could you repeat?"

        logger.info("User: '%s'", user_text)

        try:
            response = self._chat.send_message(user_text)
            return self._handle_response(response)
        except Exception as exc:
            logger.error("Gemini API error: %s", exc)
            return f"I encountered an error talking to Gemini: {exc}"

    def _handle_response(self, response) -> str:
        """
        Recursively handle Gemini responses that may include tool calls.
        """
        # Check for function call parts
        for part in response.parts:
            if hasattr(part, "function_call") and part.function_call.name:
                fc = part.function_call
                tool_name = fc.name
                tool_args = dict(fc.args) if fc.args else {}

                logger.info("Gemini requested tool: %s(%s)", tool_name, tool_args)

                # Dispatch the tool (safety gate is inside dispatcher)
                tool_result = self._dispatcher.dispatch(tool_name, tool_args)

                logger.info("Tool result: %s", str(tool_result)[:200])

                # Send tool result back to Gemini for final response
                import google.generativeai.protos as protos  # type: ignore

                follow_up = self._chat.send_message(
                    protos.Content(
                        parts=[
                            protos.Part(
                                function_response=protos.FunctionResponse(
                                    name=tool_name,
                                    response={"result": str(tool_result)},
                                )
                            )
                        ]
                    )
                )
                return self._handle_response(follow_up)

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
