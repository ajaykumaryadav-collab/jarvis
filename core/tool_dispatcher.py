"""
core/tool_dispatcher.py — Tool Registry and Dispatcher
=======================================================
Maps Gemini tool names → Python functions and handles:
  1. Safety gate check (for gated tools)
  2. Function invocation with error handling
  3. Result formatting as a string for Gemini's next turn

Adding a new tool
-----------------
1. Implement the function in tools/.
2. Import it below.
3. Add an entry to _TOOL_REGISTRY.
4. Add the tool schema to core/agent.py's TOOL_SCHEMAS list.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable

import google.generativeai.types as genai_types
from google.generativeai import protos

from core import safety_gate
from tools import (
    app_launcher,
    clipboard,
    system_info,
    volume,
    web_search,
    github_tool,
)

logger = logging.getLogger(__name__)


class ToolDispatcher:
    """Routes tool calls from the Gemini agent to the appropriate tool module."""

    def __init__(self, speaker, transcriber) -> None:
        """
        Parameters
        ----------
        speaker : Speaker
            Used by the safety gate for spoken confirmations.
        transcriber : Transcriber
            Used by the safety gate to capture user's spoken confirmation.
        """
        self._speaker = speaker
        self._transcriber = transcriber
        self._registry: dict[str, Callable] = self._build_registry()

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    def _build_registry(self) -> dict[str, Callable]:
        """Map tool names to their Python implementations."""
        return {
            # Volume controls
            "get_volume":       volume.get_volume,
            "set_volume":       volume.set_volume,
            "mute_volume":      volume.mute,
            "unmute_volume":    volume.unmute,

            # Application management
            "launch_app":       app_launcher.launch_app,
            "close_app":        app_launcher.close_app,
            "list_running_apps": app_launcher.list_running_apps,

            # System information
            "get_system_info":  system_info.get_system_info,

            # Clipboard
            "read_clipboard":   clipboard.read_clipboard,
            "write_clipboard":  clipboard.write_clipboard,

            # Web search
            "search_web":       web_search.search_web,

            # GitHub (Phase 2 stub)
            "github_info":      github_tool.github_info,
        }

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(self, tool_name: str, args: dict[str, Any]) -> str:
        """
        Execute a tool by name with given arguments.

        Parameters
        ----------
        tool_name : str
            The name of the tool as returned by Gemini.
        args : dict
            Keyword arguments to pass to the tool function.

        Returns
        -------
        str
            A string result (success or error message) to pass back to Gemini.
        """
        func = self._registry.get(tool_name)
        if func is None:
            logger.warning("Unknown tool requested: '%s'", tool_name)
            return f"Error: Unknown tool '{tool_name}'."

        # Safety gate check
        allowed = safety_gate.check(
            tool_name, args, self._speaker, self._transcriber
        )
        if not allowed:
            return f"Action '{tool_name}' was cancelled by the safety gate."

        # Execute the tool
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
        """Return the list of registered tool names."""
        return list(self._registry.keys())

    def get_gemini_tools(self) -> list:
        """Dynamically generate Gemini tool schemas from the Python function signatures."""
        declarations = []
        for name, func in self._registry.items():
            sig = inspect.signature(func)
            doc = inspect.getdoc(func) or ""
            
            properties = {}
            required = []
            
            for param_name, param in sig.parameters.items():
                # Default to string type if not specified
                param_type = protos.Type.STRING
                if param.annotation == int:
                    param_type = protos.Type.INTEGER
                elif param.annotation == float:
                    param_type = protos.Type.NUMBER
                elif param.annotation == bool:
                    param_type = protos.Type.BOOLEAN
                
                properties[param_name] = protos.Schema(
                    type=param_type,
                    description=f"Parameter {param_name}" # In a full version, we'd parse docstring
                )
                
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)
                    
            declarations.append(
                protos.FunctionDeclaration(
                    name=name,
                    description=doc.split("\n")[0] if doc else f"Tool: {name}",
                    parameters=protos.Schema(
                        type=protos.Type.OBJECT,
                        properties=properties,
                        required=required,
                    )
                )
            )
            
        return [protos.Tool(function_declarations=declarations)]
