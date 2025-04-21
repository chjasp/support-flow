from fastapi import Depends

from app.config import get_settings, Settings
from app.services.vertex import VertexClient
from app.services.firestore import FirestoreRepository
from app.services.pipeline import DocumentPipeline

# singletons cached by FastAPI's dependency system
def get_settings_dep() -> Settings:
    return get_settings()

def get_vertex() -> VertexClient:
    return VertexClient()

def get_repo() -> FirestoreRepository:
    return FirestoreRepository()

def get_pipeline(vertex: VertexClient = Depends(get_vertex),
                 repo: FirestoreRepository = Depends(get_repo)) -> DocumentPipeline:
    return DocumentPipeline(vertex, repo)
