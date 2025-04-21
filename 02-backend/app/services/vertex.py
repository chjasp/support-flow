import logging
import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig

from app.config import get_settings

class VertexClient:
    """Thin wrapper that initialises Vertex AI once and provides helper methods."""

    def __init__(self) -> None:
        s = get_settings()
        logging.info("Initialising Vertex AI client …")
        vertexai.init(project=s.gcp_project, location=s.gcp_location)
        self.extractor = GenerativeModel(s.model_extraction)
        self.summariser = GenerativeModel(
            s.model_summarisation,
            generation_config=GenerationConfig(max_output_tokens=s.max_summary_tokens)
        )
        self.generator = GenerativeModel(s.model_generation)

    # --- high‑level helpers -------------------------------------------------
    async def extract_pdf(self, gcs_uri: str) -> str:
        part = Part.from_uri(uri=gcs_uri, mime_type="application/pdf")
        prompt = ("Extract all text content from this PDF document, preserving paragraphs "
                  "and structure as much as possible. Output only the raw text content.")
        response = await self.extractor.generate_content_async([part, prompt])
        return response.text

    async def summarise(self, text: str) -> str:
        prompt = ( "Summarise the key information in the following text chunk "
                   "in about 10 sentences. Focus on the main topics and entities:\n\n"
                   f"{text}" )
        response = await self.summariser.generate_content_async(prompt)
        if response.candidates and response.candidates[0].content.parts:
            return response.text.strip()
        return "Summary unavailable."

    async def generate_answer(self, prompt: str) -> str:
        response = await self.generator.generate_content_async(prompt)
        if response.candidates and response.candidates[0].content.parts:
            return response.text
        return "Unable to generate answer."
