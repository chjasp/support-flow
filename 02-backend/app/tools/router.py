from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Sequence

from google import genai
from google.genai import types as gt

from .base import ToolNode

logger = logging.getLogger(__name__)


class Router:
    """LLM-powered router that picks the right ToolNode for a user message."""

    def __init__(
        self,
        llm_client: genai.Client,
        tools: Sequence[ToolNode],
        model_id: str,
    ):
        self.llm_client = llm_client
        self.tools: List[ToolNode] = list(tools)
        self.model_id = model_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def process(self, user_msg: str, shared_store: Dict[str, Any] | None = None) -> str:
        """Route *user_msg* to the best ToolNode (if any) or return raw LLM text.

        Parameters
        ----------
        user_msg: str
            The user input (natural-language or structured).
        shared_store: dict, optional
            Mutable dict shared across nodes during a single request so that
            multiple pieces of information can be stitched together.
        """

        shared_store = shared_store or {}

        # 1) Build function manifest from ToolNode metadata
        # Convert internal metadata → genai FunctionDeclaration objects
        fn_decls = [
            gt.FunctionDeclaration(
                name=tool.tool_name,
                description=tool.tool_desc,
                parameters=tool.openai_schema,
            )
            for tool in self.tools
        ]

        tool_cfg = gt.Tool(function_declarations=fn_decls)

        # 2) Fire a *sync* Gemini request with function calling
        try:
            resp = self.llm_client.models.generate_content(
                model=self.model_id,
                contents=[{"role": "user", "parts": [{"text": user_msg}]}],
                config=gt.GenerateContentConfig(max_output_tokens=2048, tools=[tool_cfg]),
            )
        except Exception as exc:  # pragma: no cover – network error
            logger.error("GenAI router call failed → %s", exc, exc_info=False)
            raise

        candidate = resp.candidates[0]
        
        logger.info(candidate)

        tool_call_fc = None
        content_obj = getattr(candidate, "content", None)
        if content_obj is not None:
            for part in getattr(content_obj, "parts", []):
                fc = getattr(part, "function_call", None)
                if fc is not None:
                    tool_call_fc = fc
                    break
            
        logger.info("TOOL_CALL_FC: %s", tool_call_fc)

        # 3) If model decided on *tool call* branch we dispatch to the node
        if tool_call_fc:
            tool_name = tool_call_fc.name
            args: Dict[str, Any] = tool_call_fc.args or {}

            logger.info("Router chose tool %s with args %s", tool_name, args)

            tool = self._get_tool_by_name(tool_name)
            
            logger.info("TOOL: %s", tool)
            
            result = tool.run_tool(shared_store, **args)
            
            logger.info("RESULT: %s", result)

            # 3b) Return raw tool result directly (JSON-serialisable)
            return json.dumps(result, default=str)[:20_000]

        # 4) Default: treat LLM text as final answer
        return self._candidate_to_text(candidate)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_tool_by_name(self, name: str) -> ToolNode:
        for tool in self.tools:
            if tool.tool_name == name:
                return tool
        raise ValueError(f"Unknown tool selected by LLM: {name}")

    def _tool_result_to_llm(self, user_msg: str, tool_name: str, tool_result: Any, args: Dict[str, Any] | None = None) -> str:
        """Let Gemini summarise *tool_result* by sending a proper tool response message."""
        args = args or {}

        # Gemini expects: USER -> TOOL (function_response), then MODEL will answer.

        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "parts": [{"text": user_msg}],
            },
            # Reproduce the model's function_call turn so that counts match
            {
                "role": "model",
                "parts": [
                    {
                        "function_call": {
                            "name": tool_name,
                            "args": {},
                        }
                    }
                ],
            },
            {
                "role": "tool",
                "parts": [
                    {
                        "function_response": {
                            "name": tool_name,
                            "response": {"rows": tool_result},
                        }
                    }
                ],
            },
        ]

        resp = self.llm_client.models.generate_content(
            model=self.model_id,
            contents=messages,
            config=gt.GenerateContentConfig(max_output_tokens=2048),
        )

        return self._candidate_to_text(resp.candidates[0])

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    @staticmethod
    def _candidate_to_text(candidate) -> str:
        texts = []
        for content in getattr(candidate, "content", []):
            for part in getattr(content, "parts", []):
                t = getattr(part, "text", None)
                if t:
                    texts.append(t)
        return "\n".join(texts).strip() 