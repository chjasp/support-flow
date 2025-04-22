import logging
from functools import lru_cache
from fastapi import Depends

from app.config import get_settings, Settings
from app.services.vertex import VertexClient
from app.services.firestore import FirestoreRepository
from app.services.pipeline import DocumentPipeline
from app.services.gmail import GmailService

# --- Caching Setup ---
# Use lru_cache to initialize clients/repositories only once.
@lru_cache()
def get_cached_settings():
    return get_settings()

@lru_cache()
def get_repo_cached(settings: Settings = Depends(get_cached_settings)) -> FirestoreRepository:
    logging.info("Initializing FirestoreRepository...")
    return FirestoreRepository()

@lru_cache()
def get_vertex_cached(settings: Settings = Depends(get_cached_settings)) -> VertexClient:
    logging.info("Initializing VertexClient...")
    return VertexClient()

@lru_cache()
def get_gmail_service_cached() -> GmailService:
    logging.info("Initializing GmailService...")
    resolved_settings = get_cached_settings()
    return GmailService(resolved_settings)

@lru_cache()
def get_pipeline_cached(
    settings: Settings = Depends(get_cached_settings),
    repo: FirestoreRepository = Depends(get_repo_cached),
    vertex: VertexClient = Depends(get_vertex_cached)
) -> DocumentPipeline:
    logging.info("Initializing DocumentPipeline...")
    return DocumentPipeline(settings, repo, vertex)

# --- Dependency Functions ---
# These are the functions that FastAPI will call for dependency injection.
def get_settings_dep() -> Settings:
    return get_cached_settings()

def get_repo() -> FirestoreRepository:
    return get_repo_cached()

def get_vertex() -> VertexClient:
    return get_vertex_cached()

def get_gmail_service() -> GmailService:
    return get_gmail_service_cached()

def get_pipeline() -> DocumentPipeline:
    return get_pipeline_cached()
