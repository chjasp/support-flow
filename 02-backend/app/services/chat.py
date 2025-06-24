"""Chat service – CRUD helpers + Gemini calls (stream & non-stream)."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, List

from google.cloud import firestore
from google import genai
from google.genai import types as gt

from ..models import ChatMessage, ChatSession
from ..settings import settings

logger = logging.getLogger(__name__)


class ChatService:
    """Handles chat sessions, messages and Gemini calls."""

    def __init__(self, db_client: firestore.Client, genai_client: genai.Client):
        self.db = db_client
        self.client = genai_client

    # ─────────────────────────── Chat/session helpers ───────────────────────────
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

    def _update_chat_metadata(self, chat_id: str, message: ChatMessage):
        """Update chat title & last-updated timestamp when the first user message arrives."""
        chat_ref = self.db.collection("chats").document(chat_id)
        chat_doc = chat_ref.get()
        if not chat_doc.exists:
            return

        updates = {"updated_at": message.timestamp}

        data = chat_doc.to_dict()
        if data.get("title") == "New Chat":
            preview = (message.text[:50] + "...") if len(message.text) > 50 else message.text
            updates["title"] = preview

        chat_ref.update(updates)

    def add_message(self, chat_id: str, message: ChatMessage) -> ChatMessage:
        message.id = str(uuid.uuid4())
        message.timestamp = datetime.now(timezone.utc)

        self.db.collection("chats").document(chat_id).collection("messages").document(
            message.id
        ).set(message.dict())

        # Update metadata only on user messages
        if message.sender == "user":
            self._update_chat_metadata(chat_id, message)
        return message

    # ─────────────────────────── Gemini interaction ───────────────────────────
    async def _answer_stream(self, query: str) -> AsyncGenerator[dict, None]:
        """Unified low-level stream that yields both thoughts & answer tokens."""

        stream = await self.client.aio.models.generate_content_stream(
            model=settings.model_name,
            contents=query,
            config=gt.GenerateContentConfig(
                thinking_config=gt.ThinkingConfig(include_thoughts=True),
                max_output_tokens=4096,
            ),
        )

        async for chunk in stream:
            if not chunk.candidates:
                continue
            for part in chunk.candidates[0].content.parts:
                txt = getattr(part, "text", "")
                if not txt:
                    continue
                yield {
                    "type": "thought" if getattr(part, "thought", False) else "answer",
                    "text": txt,
                }

    async def generate_response(self, query: str) -> str:
        """Return the full answer as a single string."""
        parts: list[str] = []
        async for piece in self._answer_stream(query):
            if piece["type"] == "answer":
                parts.append(piece["text"])
        return "".join(parts)

    async def stream_response(self, query: str):
        """Yield thought/answer pieces suitable for SSE streaming."""
        async for piece in self._answer_stream(query):
            if piece["type"] == "thought":
                # Emit only the first line of the internal reasoning to reduce noise
                line = re.sub(r"[*_~`]", "", piece["text"].splitlines()[0]).strip()
                yield {"type": "thought", "text": line}
            else:
                yield piece

    # ───────────────────────────── Deletion helpers ────────────────────────────
    def delete_chat(self, chat_id: str, user_id: str):
        """Delete a chat together with all nested messages (unchanged behaviour)."""
        chat_ref = self.db.collection("chats").document(chat_id)
        chat_doc = chat_ref.get()

        if not chat_doc.exists:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Chat not found")
        if chat_doc.to_dict().get("user_id") != user_id:
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="Not authorized to delete")

        # delete nested messages then the chat
        for msg in chat_ref.collection("messages").stream():
            msg.reference.delete()
        chat_ref.delete() 