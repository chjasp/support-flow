import logging
import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig

from app.config import get_settings

class VertexClient:
    """Thin wrapper that initialises Vertex AI once and provides helper methods for generation."""

    def __init__(self) -> None:
        s = get_settings()
        logging.info("Initialising Vertex AI client …")
        vertexai.init(project=s.gcp_project, location=s.gcp_location)
        self.generator = GenerativeModel(s.model_generation)

    # --- high‑level helpers -------------------------------------------------
    async def generate_answer(self, prompt: str) -> str:
        response = await self.generator.generate_content_async(prompt)
        if response.candidates and response.candidates[0].content.parts:
            return response.text
        return "Unable to generate answer."
