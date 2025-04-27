import logging
import uuid
from typing import Any, Dict, List

from fastapi import HTTPException

from .vertex import VertexClient
from .firestore import FirestoreRepository
from .cloudsql import CloudSqlRepository
from app.config import get_settings, Settings

_cfg = get_settings()

class DocumentPipeline:
    """Handles RAG retrieval and answer generation."""

    def __init__(self,
                 settings: Settings,
                 repo: FirestoreRepository,
                 vertex: VertexClient,
                 sql_repo: CloudSqlRepository) -> None:
        self.settings = settings
        self.repo = repo
        self.vertex = vertex
        self.sql_repo = sql_repo

    # ------------------------------------------------------------------ #
    # retrieval                                                          #
    # ------------------------------------------------------------------ #
    async def hybrid_search(self, query: str) -> List[Dict[str, Any]]:
        """
        Performs vector search to retrieve relevant document chunks from Cloud SQL.
        Note: Currently only vector search is implemented, not true hybrid (keyword + vector).
        """
        logging.info(f"Performing vector search for query: '{query[:50]}...'")
        try:
            # 1. Get query embedding
            query_embedding = await self.vertex.get_embedding(query)
            if not query_embedding:
                logging.error("Failed to get query embedding.")
                return [] # Return empty if embedding fails

            # 2. Perform vector search using CloudSqlRepository
            limit = self.settings.max_context_chunks # Get limit from settings
            retrieved_chunks = self.sql_repo.vector_search(query_embedding, limit)

            logging.info(f"Retrieved {len(retrieved_chunks)} chunks via vector search.")
            # The vector_search method already formats the results as List[Dict]
            # Ensure the dictionary keys include 'chunk_text' as needed by answer()
            return retrieved_chunks

        except Exception as e:
            logging.error(f"Error during hybrid (vector) search: {e}", exc_info=True)
            # Depending on desired behavior, could raise HTTPException or return empty
            # Returning empty allows fallback to general knowledge in answer()
            return []

    async def answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        if not context_chunks:
            logging.warning("No context chunks provided for RAG. Falling back to general knowledge.")
            prompt = f"Answer the question using general knowledge.\n\nQuestion: {query}\n\nAnswer (Markdown):"
            # Use await for the async call
            return await self.vertex.generate_answer(prompt)

        # Extract text, ensuring 'chunk_text' key exists and value is not None
        ctx_texts = [c.get("chunk_text", "") for c in context_chunks if c and c.get("chunk_text")]
        valid_ctx_texts = [text for text in ctx_texts if text.strip()] # Filter out empty/whitespace-only strings

        if not valid_ctx_texts:
            logging.warning("Received context chunks but couldn't extract valid text. Falling back to general knowledge.")
            prompt = f"Answer the question using general knowledge.\n\nQuestion: {query}\n\nAnswer (Markdown):"
            # Use await for the async call
            return await self.vertex.generate_answer(prompt)

        # Combine valid context texts
        ctx = "\n---\n".join(valid_ctx_texts)

        # Construct the RAG prompt
        prompt = ("Answer the user's question based *only* on the context provided below. "
                  "If the context is insufficient or doesn't contain the answer, "
                  "state that you cannot answer based on the provided documents.\n\n"
                  "Context:\n---\n{ctx}\n---\n\n"
                  "Question: {q}\n\nAnswer (Markdown):").format(ctx=ctx, q=query)

        logging.info(f"Generating RAG answer with {len(valid_ctx_texts)} context chunks.")
        # Use await for the async call
        return await self.vertex.generate_answer(prompt)
