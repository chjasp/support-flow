import logging
from typing import List

from google import genai
from google.genai import types              # pydantic config classes

from app.config import get_settings


class LLMService:
    """Wrapper around the Google Gen AI SDK (generation + embeddings)."""

    def __init__(self) -> None:
        s = get_settings()
        logging.info("Initialising Google Gen AI client …")

        # One client for the whole lifetime of the service
        self.client = genai.Client(
            vertexai=True,                  # use Vertex → IAM & EU residency
            project=s.gcp_project_id,
            location="global",
        )

        self.generation_model = s.model_generation          # e.g. "gemini-2.5-flash-preview-04-17"
        self.embedding_model  = s.model_embedding           # e.g. "gemini-embedding-exp-03-07"

        logging.info(f"Generation model: {self.generation_model}")
        logging.info(f"Embedding  model: {self.embedding_model}")

    # ---------- text generation ------------------------------------------------
    async def generate_answer(self, prompt: str) -> str:
        cfg = types.GenerateContentConfig(response_mime_type="text/plain")

        try:
            # plain-string payload keeps it simple
            resp = await self.client.aio.models.generate_content(
                model=self.generation_model,
                contents=prompt,
                config=cfg,
            )

            if getattr(resp, "text", None):
                return resp.text

            if resp.candidates:
                parts = resp.candidates[0].content.parts
                if parts:
                    return parts[0].text

            logging.warning("Empty or filtered response: %s", resp)
            return "Unable to generate answer."

        except Exception as exc:
            logging.error("Gen AI error: %s", exc, exc_info=True)
            return f"Unable to generate answer: {exc}"

    # ---------- embeddings -----------------------------------------------------

    async def get_embedding(self, text: str) -> List[float]:
        """Return a single embedding vector for *text*."""
        try:
            resp = await self.client.aio.models.embed_content(
                model=self.embedding_model,
                contents=text,
            )

            # New SDK → .embedding is a ContentEmbedding object
            emb_obj = getattr(resp, "embedding", None) or (
                resp.embeddings[0] if getattr(resp, "embeddings", None) else None
            )

            if emb_obj and hasattr(emb_obj, "values"):
                return emb_obj.values          # ← plain list[float]

            raise ValueError(f"Unexpected embed response: {resp}")

        except Exception as exc:
            logging.error("Embedding error: %s", exc, exc_info=True)
            raise

