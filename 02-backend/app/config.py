from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    gcp_project: str
    gcp_location: str
    model_extraction: str
    model_summarisation: str
    model_generation: str
    max_summary_tokens: int
    max_context_chunks: int
    cors_origins: List[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache
def get_settings() -> "Settings":
    return Settings()
