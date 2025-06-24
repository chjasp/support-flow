"""FastAPI entrypoint - thin layer that wires together services & routes.

All heavy lifting now lives in sibling modules:
  • settings.py        - env/config
  • auth.py            - authentication dependency
  • models.py          - Pydantic schemas
  • services/          - ChatService & DocumentService
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google.cloud import firestore
from google import genai

from .auth import get_current_user
from .models import ChatMessage, ChatSession, DocumentItem, QueryRequest
from .services.chat import ChatService
from .services.docs import DocumentService
from .settings import settings

# ──────────────────────────────────────────────────────────────────────────────
# Init logging & external clients
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google GenAI
_genai_client = genai.Client(vertexai=True, project=settings.project_id, location=settings.model_location)

# Firestore
_db = firestore.Client(project=settings.project_id)

# Services
_chat_service = ChatService(db_client=_db, genai_client=_genai_client)
_document_service = DocumentService(db_client=_db)

# ──────────────────────────────────────────────────────────────────────────────
# FastAPI application
# ──────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Service Backend", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────────────────
# Chat routes
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/chats", response_model=ChatSession)
async def create_chat(user=Depends(get_current_user)):
    return _chat_service.create_chat(user["user_id"])


@app.get("/chats", response_model=List[ChatSession])
async def get_chats(user=Depends(get_current_user)):
    return _chat_service.get_chats(user["user_id"])


@app.get("/chats/{chat_id}/messages", response_model=List[ChatMessage])
async def get_chat_messages(chat_id: str, user=Depends(get_current_user)):
    # (user validation could be added here)
    return _chat_service.get_messages(chat_id)


@app.post("/chats/{chat_id}/messages")
async def send_message(chat_id: str, query: QueryRequest, user=Depends(get_current_user)):
    user_msg = ChatMessage(text=query.query, sender="user")
    saved_user_msg = _chat_service.add_message(chat_id, user_msg)

    ai_text = await _chat_service.generate_response(query.query)
    bot_msg = ChatMessage(text=ai_text, sender="bot")
    saved_bot_msg = _chat_service.add_message(chat_id, bot_msg)

    logger.debug("BOT-LEN %s", len(ai_text))
    logger.debug("BOT-TEXT %s", ai_text[-120:])

    return {"user_message": saved_user_msg, "bot_message": saved_bot_msg}


@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, user=Depends(get_current_user)):
    _chat_service.delete_chat(chat_id, user["user_id"])
    return {"message": "Chat deleted successfully"}


# ──────────────────────────────────────────────────────────────────────────────
# Document routes
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/documents", response_model=DocumentItem)
async def add_document(name: str, content: str, user=Depends(get_current_user)):
    return _document_service.add_document(user["user_id"], name, content)


@app.get("/documents", response_model=List[DocumentItem])
async def get_documents(user=Depends(get_current_user)):
    return _document_service.get_documents(user["user_id"])


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user=Depends(get_current_user)):
    _document_service.delete_document(doc_id, user["user_id"])
    return {"message": "Document deleted successfully"}


# ──────────────────────────────────────────────────────────────────────────────
# Streaming route
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/chats/{chat_id}/messages/stream")
async def stream_message(chat_id: str, query: QueryRequest, user=Depends(get_current_user)):
    """Stream thought lines and answer tokens as Server-Sent Events."""
    logger.info("STREAM /chats/%s/messages/stream", chat_id)
    logger.info("QUERY: %s", query.query)

    # Persist user question upfront
    user_msg = ChatMessage(text=query.query, sender="user")
    _chat_service.add_message(chat_id, user_msg)

    async def event_generator():
        logger.info("Starting event generator for chat %s", chat_id)
        answer_parts: list[str] = []

        async for piece in _chat_service.stream_response(query.query):
            if piece["type"] == "thought":
                yield f"event:thought\ndata:{piece['text']}\n\n"
            else:
                answer_parts.append(piece["text"])

        # After streaming finished, persist full answer (not streamed)
        full_answer = "".join(answer_parts)
        bot_msg = ChatMessage(text=full_answer, sender="bot")
        _chat_service.add_message(chat_id, bot_msg)

        logger.info("Finished streaming for chat %s, saving full answer.", chat_id)
        logger.debug("BOT-LEN %s", len(full_answer))
        logger.debug("BOT-TEXT %s", full_answer[-120:])

        # Indicate completion only
        yield "event:end\ndata:done\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ──────────────────────────────────────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Service is running"}


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
