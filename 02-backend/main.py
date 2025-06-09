"""
main.py – FastAPI backend that uses **google-genai** instead of the Vertex AI SDK
"""

import logging
import uuid
import os
from datetime import datetime, timezone
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.cloud import firestore
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Configuration & initialization
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
LOCATION = os.environ.get("GCP_LOCATION")
MODEL_NAME = os.environ.get("GCP_MODEL")

# google-genai client (async companion lives under `.aio`)
genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")

# Firestore
db = firestore.Client(project=PROJECT_ID)

# Auth helper
security = HTTPBearer()

# ──────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Service Backend", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # adjust to your frontend origin(s)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    id: Optional[str] = None
    text: str
    sender: str  # "user" | "bot"
    timestamp: Optional[datetime] = None


class ChatSession(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class QueryRequest(BaseModel):
    query: str


class DocumentItem(BaseModel):
    id: str
    name: str
    content: str
    created_at: datetime


# ──────────────────────────────────────────────────────────────────────────────
# Authentication (dummy for demo only)
# ──────────────────────────────────────────────────────────────────────────────
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    # TODO: replace with real JWT verification
    return {"user_id": "demo_user", "email": "demo@example.com"}


# ──────────────────────────────────────────────────────────────────────────────
# Chat service
# ──────────────────────────────────────────────────────────────────────────────
class ChatService:
    """Handles chat sessions and messages."""

    def __init__(
        self, db_client: firestore.Client, genai_client: genai.Client, model: str
    ):
        self.db = db_client
        self.client = genai_client
        self.model = model

    # ───────────── Chat/session helpers ─────────────
    def create_chat(self, user_id: str) -> ChatSession:
        chat_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        chat_data = {
            "id": chat_id,
            "title": "New Chat",
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        self.db.collection("chats").document(chat_id).set(chat_data)
        return ChatSession(**chat_data)

    def get_chats(self, user_id: str) -> List[ChatSession]:
        docs = (
            self.db.collection("chats")
            .where("user_id", "==", user_id)
            .order_by("updated_at", direction=firestore.Query.DESCENDING)
            .limit(50)
            .stream()
        )
        return [ChatSession(**doc.to_dict()) for doc in docs]

    def get_messages(self, chat_id: str) -> List[ChatMessage]:
        docs = (
            self.db.collection("chats")
            .document(chat_id)
            .collection("messages")
            .order_by("timestamp")
            .stream()
        )
        return [ChatMessage(**doc.to_dict()) for doc in docs]

    def add_message(self, chat_id: str, message: ChatMessage) -> ChatMessage:
        message.id = str(uuid.uuid4())
        message.timestamp = datetime.now(timezone.utc)

        self.db.collection("chats").document(chat_id).collection("messages").document(
            message.id
        ).set(message.dict())

        # update chat metadata on user messages
        if message.sender == "user":
            chat_ref = self.db.collection("chats").document(chat_id)
            chat_doc = chat_ref.get()
            if chat_doc.exists:
                chat_data = chat_doc.to_dict()
                updates = {"updated_at": message.timestamp}

                # Give the chat a title based on the first user entry
                if chat_data.get("title") == "New Chat":
                    preview = (
                        (message.text[:50] + "...")
                        if len(message.text) > 50
                        else message.text
                    )
                    updates["title"] = preview

                chat_ref.update(updates)
        return message

    # ───────────── LLM call ─────────────
    async def generate_response(self, query: str) -> str:
        """Call Gemini LLM asynchronously via google-genai."""
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=query,
                config=types.GenerateContentConfig(
                    automatic_function_calling={"disable": True},
                ),
            )
            return response.text
        except Exception as e:
            logger.error(f"LLM error: {e}")
            return (
                "I’m having trouble generating a response right now—"
                "please try again in a moment."
            )

    # ───────────── Deletion helpers ─────────────
    def delete_chat(self, chat_id: str, user_id: str):
        chat_ref = self.db.collection("chats").document(chat_id)
        chat_doc = chat_ref.get()

        if not chat_doc.exists:
            raise HTTPException(status_code=404, detail="Chat not found")
        if chat_doc.to_dict().get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete")

        # delete nested messages then the chat
        for msg in chat_ref.collection("messages").stream():
            msg.reference.delete()
        chat_ref.delete()


# ──────────────────────────────────────────────────────────────────────────────
# Document service
# ──────────────────────────────────────────────────────────────────────────────
class DocumentService:
    """CRUD wrapper around 'documents' collection."""

    def __init__(self, db_client: firestore.Client):
        self.db = db_client

    def add_document(self, user_id: str, name: str, content: str) -> DocumentItem:
        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        doc_data = {
            "id": doc_id,
            "user_id": user_id,
            "name": name,
            "content": content,
            "created_at": now,
        }
        self.db.collection("documents").document(doc_id).set(doc_data)
        return DocumentItem(**doc_data)

    def get_documents(self, user_id: str) -> List[DocumentItem]:
        try:
            docs = (
                self.db.collection("documents")
                .where("user_id", "==", user_id)
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(50)
                .stream()
            )
            items = [DocumentItem(**doc.to_dict()) for doc in docs]
        except Exception as e:
            logger.warning(f"No composite index for documents, falling back: {e}")
            docs = (
                self.db.collection("documents").where("user_id", "==", user_id).stream()
            )
            items = [DocumentItem(**doc.to_dict()) for doc in docs]
            items.sort(key=lambda x: x.created_at, reverse=True)
        return items

    def delete_document(self, doc_id: str, user_id: str):
        doc_ref = self.db.collection("documents").document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc.to_dict().get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete")
        doc_ref.delete()


# ──────────────────────────────────────────────────────────────────────────────
# Instantiate services
# ──────────────────────────────────────────────────────────────────────────────
chat_service = ChatService(db, genai_client, MODEL_NAME)
document_service = DocumentService(db)


# ──────────────────────────────────────────────────────────────────────────────
# API routes — chats
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/chats", response_model=ChatSession)
async def create_chat(user=Depends(get_current_user)):
    return chat_service.create_chat(user["user_id"])


@app.get("/chats", response_model=List[ChatSession])
async def get_chats(user=Depends(get_current_user)):
    return chat_service.get_chats(user["user_id"])


@app.get("/chats/{chat_id}/messages", response_model=List[ChatMessage])
async def get_chat_messages(chat_id: str, user=Depends(get_current_user)):
    # (user validation could be added here)
    return chat_service.get_messages(chat_id)


@app.post("/chats/{chat_id}/messages")
async def send_message(
    chat_id: str, query: QueryRequest, user=Depends(get_current_user)
):
    try:
        user_msg = ChatMessage(text=query.query, sender="user")
        saved_user_msg = chat_service.add_message(chat_id, user_msg)

        ai_text = await chat_service.generate_response(query.query)
        bot_msg = ChatMessage(text=ai_text, sender="bot")
        saved_bot_msg = chat_service.add_message(chat_id, bot_msg)

        return {"user_message": saved_user_msg, "bot_message": saved_bot_msg}
    except Exception as e:
        logger.error(f"Message processing failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to process message")


@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, user=Depends(get_current_user)):
    chat_service.delete_chat(chat_id, user["user_id"])
    return {"message": "Chat deleted successfully"}


# ──────────────────────────────────────────────────────────────────────────────
# API routes — documents
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/documents", response_model=DocumentItem)
async def add_document(name: str, content: str, user=Depends(get_current_user)):
    return document_service.add_document(user["user_id"], name, content)


@app.get("/documents", response_model=List[DocumentItem])
async def get_documents(user=Depends(get_current_user)):
    return document_service.get_documents(user["user_id"])


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user=Depends(get_current_user)):
    document_service.delete_document(doc_id, user["user_id"])
    return {"message": "Document deleted successfully"}


# ──────────────────────────────────────────────────────────────────────────────
# Misc
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Service is running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
