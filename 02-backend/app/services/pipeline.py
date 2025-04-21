import logging
import uuid
from typing import Any, Dict, List

from fastapi import HTTPException

from app.utils.chunking import split
from .vertex import VertexClient
from .firestore import FirestoreRepository
from .storage import read_text_from_gcs
from app.config import get_settings

_cfg = get_settings()

class DocumentPipeline:
    """Processes PDFs & text files and performs hybrid search."""

    def __init__(self,
                 vertex: VertexClient,
                 repo: FirestoreRepository) -> None:
        self.vertex = vertex
        self.repo = repo

    # ------------------------------------------------------------------ #
    # ingest                                                             #
    # ------------------------------------------------------------------ #
    async def process_pdf(self, gcs_uri: str, *, original_name: str) -> str:
        doc_id = uuid.uuid4().hex
        text = await self.vertex.extract_pdf(gcs_uri)
        chunks = await self._chunk_and_summarise(text)
        self.repo.save_document(doc_id, original_name, "PDF", gcs_uri, chunks)
        return doc_id

    async def process_text(self, gcs_uri: str, *, original_name: str) -> str:
        doc_id = uuid.uuid4().hex
        text = await read_text_from_gcs(gcs_uri)
        chunks = await self._chunk_and_summarise(text)
        self.repo.save_document(doc_id, original_name, "TEXT", gcs_uri, chunks)
        return doc_id

    async def _chunk_and_summarise(self, text: str) -> List[Dict[str, Any]]:
        chunks_raw = split(text)
        chunks = []
        for i, c in enumerate(chunks_raw):
            summary = await self.vertex.summarise(c)
            chunks.append({
                "chunk_text": c,
                "summary": summary,
                "chunk_order": i
            })
        return chunks

    # ------------------------------------------------------------------ #
    # retrieval                                                          #
    # ------------------------------------------------------------------ #
    async def hybrid_search(self, query: str) -> List[Dict[str, Any]]:
        kw_results = self.repo.keyword_search(query, max_results=20)
        # simple version: use keyword results directly if <max_context
        return kw_results[:_cfg.max_context_chunks]

    async def answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        if not context_chunks:
            prompt = f"Answer the question using general knowledge.\n\nQuestion: {query}\n\nAnswer (Markdown):"
            return await self.vertex.generate_answer(prompt)
        ctx = "\n---\n".join(c["chunk_text"] for c in context_chunks)
        prompt = ("Answer the user's question based on the context below. "
                  "If context is insufficient, say so.\n\nContext:\n---\n{ctx}\n---\n\n"
                  "Question: {q}\n\nAnswer (Markdown):").format(ctx=ctx, q=query)
        return await self.vertex.generate_answer(prompt)
