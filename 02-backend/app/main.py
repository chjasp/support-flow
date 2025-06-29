"""FastAPI entrypoint - thin layer that wires together services & routes.

All heavy lifting now lives in sibling modules:
  • settings.py        - env/config
  • auth.py            - authentication dependency
  • models.py          - Pydantic schemas
  • services/          - ChatService
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import firestore
from google import genai
from pydantic import BaseModel

from .auth import get_current_user
from .models import ChatMessage, ChatSession, QueryRequest
from .services.chat import ChatService
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

# Collections
_MODELS_COLLECTION = "models"

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
# Notebook routes
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/notebooks", response_model=ChatSession)
async def create_chat(user=Depends(get_current_user)):
    return _chat_service.create_chat(user["user_id"])


@app.get("/notebooks", response_model=List[ChatSession])
async def get_chats(user=Depends(get_current_user)):
    return _chat_service.get_chats(user["user_id"])


@app.get("/notebooks/{chat_id}/messages", response_model=List[ChatMessage])
async def get_chat_messages(chat_id: str, user=Depends(get_current_user)):
    # (user validation could be added here)
    return _chat_service.get_messages(chat_id)


@app.post("/notebooks/{chat_id}/messages")
async def send_message(chat_id: str, query: QueryRequest, user=Depends(get_current_user)):
    # Store user message
    user_msg = ChatMessage(text=query.query, sender="user")
    saved_user_msg = _chat_service.add_message(chat_id, user_msg)

    # Resolve model_id by model_name from Firestore
    model_id: Optional[str] = None

    try:
        doc = (
            _db.collection(_MODELS_COLLECTION)
            .where("name", "==", query.model_name)
            .limit(1)
            .get()
        )
        if doc:
            doc_data = doc[0].to_dict()
            if doc_data.get("active") is not False:
                model_id = doc_data.get("model_id") or doc_data.get("id")
                
    except Exception as exc:
        logger.error("Error fetching model_id for '%s': %s", query.model_name, exc)

    if not model_id:
        raise HTTPException(status_code=400, detail="Invalid or inactive model selected")

    ai_text = await _chat_service.generate_response(query.query, model_id)
    bot_msg = ChatMessage(text=ai_text, sender="bot")
    saved_bot_msg = _chat_service.add_message(chat_id, bot_msg)

    return {"user_message": saved_user_msg, "bot_message": saved_bot_msg}


@app.delete("/notebooks/{chat_id}")
async def delete_chat(chat_id: str, user=Depends(get_current_user)):
    _chat_service.delete_chat(chat_id, user["user_id"])
    return {"message": "Chat deleted successfully"}


# ──────────────────────────────────────────────────────────────────────────────
# Rename notebook route
# ──────────────────────────────────────────────────────────────────────────────


class RenameRequest(BaseModel):
    title: str


@app.patch("/notebooks/{chat_id}", response_model=ChatSession)
async def rename_chat(chat_id: str, payload: RenameRequest, user=Depends(get_current_user)):
    new_title = payload.title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    return _chat_service.rename_chat(chat_id, user["user_id"], new_title)



# ──────────────────────────────────────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Service is running"}


# ──────────────────────────────────────────────────────────────────────────────
# Model list route
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/models", response_model=List[str])
async def get_available_models(user=Depends(get_current_user)):
    """Return the list of **display names** for available Gemini models.

    Data source: Firestore collection ``models`` where each document contains
    at minimum a ``name`` field (display label) and optionally a ``model_id``
    and an ``active`` boolean.  Only documents with ``active`` == True (or
    missing) are returned, ordered alphabetically by ``name``.
    """

    try:
        collection_ref = _db.collection(_MODELS_COLLECTION)

        # Fetch all docs; we'll filter by 'active' flag in Python so that
        # documents without the field are treated as active.
        docs_iter = collection_ref.stream()

        models_info = []
        for doc in docs_iter:
            data = doc.to_dict()
            # Skip if explicit active flag set to False
            if data.get("active") is False:
                continue

            name = data.get("name")
            if not name:
                continue  # Display name required

            order_val_raw = data.get("order")
            # Ensure numeric order; default large value
            try:
                order_val = int(order_val_raw)
            except (TypeError, ValueError):
                order_val = 1_000_000

            models_info.append({"name": name, "order": order_val, "model_id": data.get("model_id") or data.get("id")})

        # Sort first by order then alphabetically by name for stability
        models_info.sort(key=lambda x: (x["order"], x["name"].lower()))

        names: List[str] = [m["name"] for m in models_info]

        return names

    except Exception as exc:
        # Log and fall back to env var list for resiliency
        logger.error("Failed to fetch models from Firestore: %s", exc)
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
