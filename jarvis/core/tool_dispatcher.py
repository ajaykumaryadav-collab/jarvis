"""
jarvis/core/tool_dispatcher.py — Tool Registry and Dispatcher
=============================================================
Maps LLM tool names to Python functions and handles:
  1. Safety gate check (for tools in config.GATED_TOOLS)
  2. Function invocation with type-safe argument handling
  3. Result formatting as a string for the LLM's next turn
  4. Dynamic Gemini tool schema generation from function signatures

Adding a new tool
-----------------
1. Implement the function in `jarvis/tools/`.
2. Import it below and add an entry to `_build_registry()`.
3. Add a safety gate entry in `config.GATED_TOOLS` if destructive.

The Gemini tool schema is generated automatically from the function
signature and docstring — no manual JSON schema needed.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable

import google.generativeai.types as genai_types  # type: ignore
from google.generativeai import protos            # type: ignore

from jarvis.core import safety_gate
from jarvis.tools import (
    app_launcher,
    clipboard,
    system_info,
    volume,
    web_search,
    github_tool,
)

logger = logging.getLogger(__name__)


class ToolDispatcher:
    """Routes LLM tool calls to their Python implementations.

    The dispatcher is provider-agnostic: it receives TTS and STT providers
    as constructor arguments (needed by the safety gate) rather than
    importing them directly, keeping the dependency direction clean.
    """

    def __init__(self, tts_provider, stt_provider) -> None:
        """
        Parameters
        ----------
        tts_provider : TTSProvider
            Used by the safety gate to speak confirmation requests.
        stt_provider : STTProvider
            Used by the safety gate to capture the user's spoken confirmation.
        """
        self._tts = tts_provider
        self._stt = stt_provider
        self._registry: dict[str, Callable] = self._build_registry()

    # ------------------------------------------------------------------
    # Tool Registry
    # ------------------------------------------------------------------

    def _build_registry(self) -> dict[str, Callable]:
        """Map tool names (as exposed to the LLM) to Python functions.

        Returns
        -------
        dict[str, Callable]
            Mapping from tool name string to the callable implementation.
        """
        return {
            # Volume controls
            "get_volume":           volume.get_volume,
            "set_volume":           volume.set_volume,
            "mute_volume":          volume.mute,
            "unmute_volume":        volume.unmute,

            # Application management
            "launch_app":           app_launcher.launch_app,
            "close_app":            app_launcher.close_app,
            "list_running_apps":    app_launcher.list_running_apps,

            # System information
            "get_system_info":      system_info.get_system_info,

            # Clipboard
            "read_clipboard":       clipboard.read_clipboard,
            "write_clipboard":      clipboard.write_clipboard,

            # Web search
            "search_web":           web_search.search_web,

            # GitHub (Phase 2 stub — ready for expansion)
            "github_info":          github_tool.github_info,
        }

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(self, tool_name: str, args: dict[str, Any]) -> str:
        """Execute a tool by name after running the safety gate check.

        Parameters
        ----------
        tool_name : str
            The name of the tool as returned by the LLM.
        args : dict
            Keyword arguments to pass to the tool function.

        Returns
        -------
        str
            A string result to pass back to the LLM.
            Always a string — never raises (errors are returned as strings).
        """
        func = self._registry.get(tool_name)
        if func is None:
            logger.warning("Unknown tool requested: '%s'", tool_name)
            return f"Error: Unknown tool '{tool_name}'."

        # Safety gate check — speaks a confirmation prompt for gated tools
        allowed = safety_gate.check(tool_name, args, self._tts, self._stt)
        if not allowed:
            return f"Action '{tool_name}' was cancelled by the safety gate."

        # Execute the tool and catch all exceptions
        try:
            logger.info("Executing tool: %s(%s)", tool_name, args)
            result = func(**args)
            return str(result) if result is not None else "Done."
        except TypeError as exc:
            logger.error("Tool '%s' called with wrong args %s: %s", tool_name, args, exc)
            return f"Error: Wrong arguments for '{tool_name}': {exc}"
        except Exception as exc:
            logger.error("Tool '%s' raised an exception: %s", tool_name, exc)
            return f"Error executing '{tool_name}': {exc}"

    def available_tools(self) -> list[str]:
        """Return the list of all registered tool names.

        Returns
        -------
        list[str]
            Sorted list of tool name strings.
        """
        return sorted(self._registry.keys())

    # ------------------------------------------------------------------
    # Gemini Schema Generation
    # ------------------------------------------------------------------

    def get_gemini_tools(self) -> list:
        """Dynamically generate Gemini FunctionDeclaration schemas.

        Introspects the Python function signatures and docstrings to build
        the tool schema automatically. No manual JSON schema needed.

        Returns
        -------
        list[protos.Tool]
            A list containing a single Tool proto with all declarations.
        """
        declarations = []
        for name, func in self._registry.items():
            sig = inspect.signature(func)
            doc = inspect.getdoc(func) or ""

            properties: dict[str, protos.Schema] = {}
            required: list[str] = []

            for param_name, param in sig.parameters.items():
                # Map Python type annotations to Gemini proto types
                annotation = param.annotation
                if annotation == int:
                    param_type = protos.Type.INTEGER
                elif annotation == float:
                    param_type = protos.Type.NUMBER
                elif annotation == bool:
                    param_type = protos.Type.BOOLEAN
                else:
                    param_type = protos.Type.STRING

                properties[param_name] = protos.Schema(
                    type=param_type,
                    description=f"Parameter: {param_name}",
                )

                if param.default == inspect.Parameter.empty:
                    required.append(param_name)

            declarations.append(
                protos.FunctionDeclaration(
                    name=name,
                    # Use the first line of the docstring as the tool description
                    description=doc.split("\n")[0] if doc else f"Tool: {name}",
                    parameters=protos.Schema(
                        type=protos.Type.OBJECT,
                        properties=properties,
                        required=required,
                    ),
                )
            )

        return [protos.Tool(function_declarations=declarations)]
