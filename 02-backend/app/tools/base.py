from __future__ import annotations

"""Common contract for external system integrations ("tools").

Each ToolNode must declare minimal metadata so that we can expose it to the
LLM as a function-calling manifest and provide a pluggable `run_tool()`
method understood by the router.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class ToolNode(ABC):
    """Abstract base class for pluggable tools.

    Sub-classes **must** override `tool_name`, `tool_desc`, `openai_schema` and
    implement :py:meth:`exec`.
    """

    # ---------------------------------------------------------------------
    # LLM-visible metadata (override in subclass)
    # ---------------------------------------------------------------------
    tool_name: str = ""
    tool_desc: str = ""
    openai_schema: Dict[str, Any] | None = None  # JSON schema for fn-calling

    # ---------------------------------------------------------------------
    # Optional lifecycle hooks
    # ---------------------------------------------------------------------
    def prep(self, shared_store: Dict[str, Any]):
        """Optional pre-processing stage.

        Override when you need to enrich user arguments (e.g. inject default
        dates).  The *return value* is merged into the *kwargs* received by
        :py:meth:`exec` so you can populate additional parameters.
        """
        return {}

    @abstractmethod
    def exec(self, **kwargs):  # noqa: D401  (imperative style)
        """Perform the actual work.

        Must be implemented by every subclass.  Expected to return a JSON-
        serialisable object (or something the calling layer can serialise).
        """

    def post(self, shared_store: Dict[str, Any], input_kwargs: Dict[str, Any], result: Any):
        """Optional post-processing stage – persist results into shared store."""
        shared_store[self.tool_name] = result

    # ------------------------------------------------------------------
    # Convenience runner combining the three lifecycle phases
    # ------------------------------------------------------------------
    def run_tool(self, shared_store: Dict[str, Any], **kwargs):
        # Merge prep output with explicit kwargs (explicit wins)
        prep_kwargs = self.prep(shared_store) or {}
        merged = {**prep_kwargs, **kwargs}

        result = self.exec(**merged)
        self.post(shared_store, merged, result)
        return result 