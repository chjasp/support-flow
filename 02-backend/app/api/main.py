from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.utils.logging import configure_logging
from .routers import documents, chats, events
from .routers.chats import query_router as chat_query_router

configure_logging()
settings = get_settings()

app = FastAPI(
    title="Knowledge Base API",
    version="1.0.0",
    description="Refactored multi-module service"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(chats.router)
app.include_router(chat_query_router)
app.include_router(events.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
