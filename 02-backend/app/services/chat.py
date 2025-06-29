"""Chat service – CRUD helpers + Gemini calls (stream & non-stream)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List

from google.cloud import firestore
from google import genai
from google.genai import types as gt

from ..models import ChatMessage, ChatSession
from ..settings import settings
from ..tools.bigquery_node import BigQueryNode
from ..tools.router import Router

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
            "title": "Untitled Notebook",
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

        # Only update the last-activity timestamp – the title will be handled explicitly
        # via a dedicated rename endpoint on the frontend.
        chat_ref.update({"updated_at": message.timestamp})

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
    async def generate_response(self, query: str, model_id: str) -> str:
        """Generate a response that *may* involve tool execution via Router.

        The call order is:
        1. Ask Gemini with *function calling* enabled to see if it wants to
           trigger one of the registered ToolNodes (currently BigQuery).
        2. If Gemini returns ``finish_reason == TOOL_USE`` we execute the tool
           and let Gemini do a *follow-up* summarisation so the final answer is
           user-friendly.
        3. Fallback – no tool call → we return Gemini's direct answer.
        """

        # 1) Try router-based invocation first (sync call inside async func)
        try:
            router = Router(
                llm_client=self.client,
                tools=[BigQueryNode(project=settings.project_id)],
                model_id=model_id,
            )

            # Router.process uses blocking client; run in thread to avoid
            # blocking the event-loop.
            import anyio

            routed_text = await anyio.to_thread.run_sync(router.process, query)
            if routed_text:
                return routed_text
        except Exception as exc:  # pragma: no cover – router failure
            logger.error("Router failed → falling back to pure LLM: %s", exc, exc_info=False)

        # 2) Pure LLM fallback (existing behaviour)
        resp = await self.client.aio.models.generate_content(
            model=model_id,
            contents=query,
            config=gt.GenerateContentConfig(max_output_tokens=4096),
        )

        return resp.text or ""

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

    # ────────────────────────── Title rename helper ──────────────────────────
    def rename_chat(self, chat_id: str, user_id: str, new_title: str) -> ChatSession:
        """Rename a chat/notebook after validating ownership."""

        from fastapi import HTTPException  # Local import to avoid circular deps

        chat_ref = self.db.collection("chats").document(chat_id)
        chat_doc = chat_ref.get()

        if not chat_doc.exists:
            raise HTTPException(status_code=404, detail="Chat not found")

        data = chat_doc.to_dict()
        if data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to rename")

        now = datetime.now(timezone.utc)
        chat_ref.update({"title": new_title, "updated_at": now})

        updated = chat_ref.get().to_dict()
        return ChatSession(**updated) 