from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    gcp_project: str
    gcp_location: str
    model_extraction: str
    model_summarisation: str
    model_generation: str
    max_summary_tokens: int
    max_context_chunks: int
    cors_origins: List[str] = ["http://localhost:3000"]
    google_service_account_json: Optional[str] = None
    gmail_impersonate_email: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache
def get_settings() -> "Settings":
    return Settings()
