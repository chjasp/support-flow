import logging
import uuid
from typing import Any, Dict, List

from fastapi import HTTPException

from .vertex import VertexClient
from .firestore import FirestoreRepository
from app.config import get_settings

_cfg = get_settings()

class DocumentPipeline:
    """Handles RAG retrieval and answer generation."""

    def __init__(self,
                 settings,
                 repo: FirestoreRepository,
                 vertex: VertexClient) -> None:
        self.settings = settings
        self.repo = repo
        self.vertex = vertex

    # ------------------------------------------------------------------ #
    # retrieval                                                          #
    # ------------------------------------------------------------------ #
    async def hybrid_search(self, query: str) -> List[Dict[str, Any]]:
        logging.warning("Hybrid search is currently not implemented. Returning empty results.")
        return []

    async def answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        if not context_chunks:
            prompt = f"Answer the question using general knowledge.\n\nQuestion: {query}\n\nAnswer (Markdown):"
            return await self.vertex.generate_answer(prompt)

        ctx_texts = [c.get("chunk_text", "") for c in context_chunks]
        valid_ctx_texts = [text for text in ctx_texts if text]
        if not valid_ctx_texts:
            logging.warning("Received context chunks but couldn't extract text. Falling back to general knowledge.")
            prompt = f"Answer the question using general knowledge.\n\nQuestion: {query}\n\nAnswer (Markdown):"
            return await self.vertex.generate_answer(prompt)

        ctx = "\n---\n".join(valid_ctx_texts)
        prompt = ("Answer the user's question based on the context below. "
                  "If context is insufficient, say so.\n\nContext:\n---\n{ctx}\n---\n\n"
                  "Question: {q}\n\nAnswer (Markdown):").format(ctx=ctx, q=query)
        return await self.vertex.generate_answer(prompt)
