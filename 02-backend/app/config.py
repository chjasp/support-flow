from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    gcp_project: str
    gcp_location: str
    model_generation: str
    max_summary_tokens: int
    max_context_chunks: int
    cors_origins: List[str] = ["http://localhost:3000"]
    google_service_account_json: Optional[str] = None
    gmail_impersonate_email: Optional[str] = None

    # --- Cloud SQL Settings ---
    cloud_sql_instance: str # e.g., project:region:instance
    cloud_sql_user: str
    cloud_sql_password: str
    cloud_sql_db: str
    # Optional: Pool settings
    cloud_sql_pool_min_conn: int = 1
    cloud_sql_pool_max_conn: int = 5

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings():
    return Settings()
