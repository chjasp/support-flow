from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    gcp_project: str
    gcp_location: str
    model_generation: str
    model_embedding: str
    max_summary_tokens: int
    max_context_chunks: int = 5
    cors_origins: List[str] = ["http://localhost:3000", "https://YOUR_FRONTEND_CLOUD_RUN_URL"]
    google_service_account_json: Optional[str] = None

    # --- Cloud SQL Settings ---
    cloud_sql_instance: str # e.g., project:region:instance
    cloud_sql_user: str
    cloud_sql_password: str
    cloud_sql_db: str
    # Optional: Pool settings
    cloud_sql_pool_min_conn: int = 1
    cloud_sql_pool_max_conn: int = 5

    # --- Add Auth Audience ---
    auth_google_client_id: str # The Client ID used by the Next.js frontend

    # --- Chat Settings ---
    max_chat_title_length: int = 50

    # --- Processing Service Settings ---
    processing_service_url: str = "http://localhost:8080"  # Default for local development

    # --- Unified Content Processing Settings ---
    gcp_project_id: str  # For Pub/Sub topic path
    content_processing_topic: str = "content-processing-topic"  # Pub/Sub topic name

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        case_sensitive = True
        
        # Add environment variable mapping
        fields = {
            'gcp_project_id': {'env': ['GCP_PROJECT_ID', 'GOOGLE_CLOUD_PROJECT', 'gcp_project']},
        }

@lru_cache()
def get_settings():
    # Make sure AUTH_GOOGLE_CLIENT_ID is loaded from .env or environment
    return Settings()
