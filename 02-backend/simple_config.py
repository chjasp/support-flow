"""
Simplified configuration for the AI Customer Service Backend
"""
import os
from typing import List

class SimpleConfig:
    """Simple configuration class using environment variables"""
    
    # Google Cloud Project Settings
    PROJECT_ID: str = os.getenv("GOOGLE_CLOUD_PROJECT", "your-project-id")
    LOCATION: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    
    # CORS Settings
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001", 
        "https://your-frontend-domain.com"
    ]
    
    # LLM Settings
    MODEL_NAME: str = os.getenv("MODEL_NAME", "gemini-1.5-flash")
    
    # Development Settings
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    @classmethod
    def get_cors_origins(cls) -> List[str]:
        """Get CORS origins from environment or use defaults"""
        env_origins = os.getenv("CORS_ORIGINS")
        if env_origins:
            return [origin.strip() for origin in env_origins.split(",")]
        return cls.CORS_ORIGINS

# Global config instance
config = SimpleConfig() 