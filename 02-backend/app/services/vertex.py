import logging
import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from vertexai.language_models import TextEmbeddingModel
from typing import List

from app.config import get_settings

class VertexClient:
    """Thin wrapper that initialises Vertex AI once and provides helper methods for generation and embedding."""

    def __init__(self) -> None:
        s = get_settings()
        logging.info("Initialising Vertex AI client …")
        vertexai.init(project=s.gcp_project, location=s.gcp_location)
        self.generator = GenerativeModel(s.model_generation)
        logging.info(f"Initializing embedding model: {s.model_embedding}")
        self.embedder = TextEmbeddingModel.from_pretrained(s.model_embedding)

    # --- high‑level helpers -------------------------------------------------
    async def generate_answer(self, prompt: str) -> str:
        response = await self.generator.generate_content_async(prompt)
        try:
            return response.text
        except ValueError:
            if response.candidates and response.candidates[0].content.parts:
                return response.candidates[0].content.parts[0].text
            else:
                logging.warning("Vertex AI response structure unexpected or empty.")
                return "Unable to generate answer."
        except Exception as e:
            logging.error(f"Error processing Vertex AI generation response: {e}", exc_info=True)
            return "Unable to generate answer."

    async def get_embedding(self, text: str) -> List[float]:
        """Generates embedding for a single piece of text."""
        try:
            embeddings = self.embedder.get_embeddings([text])
            if embeddings:
                return embeddings[0].values
            else:
                logging.error("Failed to generate embedding, received empty list.")
                raise ValueError("Embedding generation failed.")
        except Exception as e:
            logging.error(f"Error generating embedding: {e}", exc_info=True)
            raise
