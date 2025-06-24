"""Global configuration using pydantic settings management.

Values are loaded from environment variables (or an .env file) and
exposed via the singleton `settings` instance.
"""

from __future__ import annotations

import os
from typing import List

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application configuration loaded from env or defaults."""

    # Google Cloud / Vertex AI
    project_id: str = Field(default="", alias="GOOGLE_CLOUD_PROJECT")
    model_location: str = Field(default="global", alias="GCP_MODEL_LOCATION")
    model_name: str = Field(default="models/gemini-1.0-pro", alias="GCP_MODEL")

    # Authentication
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")

    # CORS - accept comma-separated string
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    @property
    def cors_origins_list(self) -> List[str]:
        """Convert comma-separated CORS origins to list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings() 