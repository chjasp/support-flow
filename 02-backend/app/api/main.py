import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.utils.logging import configure_logging
from .routers import documents, chats, web_processing
from .routers.chats import query_router as chat_query_router

configure_logging()
settings = get_settings()

app = FastAPI(
    title="AI Customer Service Backend",
    description="API endpoints for managing documents, chats, and generating replies.",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins, # Origins from your settings
    allow_credentials=True,
    allow_methods=["*"], # Allow all standard methods
    allow_headers=["*", "Authorization"], # IMPORTANT: Allow all headers OR explicitly add "Authorization"
)

app.include_router(documents.router)
app.include_router(chats.router)
app.include_router(chat_query_router)
app.include_router(web_processing.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
