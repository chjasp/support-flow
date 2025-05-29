import datetime as _dt
import logging
import re
from typing import Any, Dict, List, Tuple, Optional

from google.cloud import firestore
from google.api_core.exceptions import NotFound
from google.cloud.firestore import SERVER_TIMESTAMP # Import SERVER_TIMESTAMP

from app.config import get_settings
from app.models.domain import ChatMessage, ChatMetadata, DocumentSource # Import chat models and DocumentSource

_DEFAULT_CHAT_TITLE = "New Chat"




class FirestoreRepository:
    """Repository for interacting with Chat data in Firestore."""
    def __init__(self, project_id: str, db_name: str = "(default)") -> None:
        self.db = firestore.Client(project=project_id, database=db_name)
        self._chats_coll = self.db.collection("chats") # Chat collection reference
        logging.info(f"FirestoreRepository initialized for project '{project_id}', database '{db_name}'")

    # --------------------------------------------------------------------- #
    # document persistence methods removed
    # (save_document_metadata, list_documents, delete_document)
    # --------------------------------------------------------------------- #


    # --------------------------------------------------------------------- #
    # Chat Persistence
    # --------------------------------------------------------------------- #
    def create_chat(self, initial_message: Optional[ChatMessage] = None) -> ChatMetadata:
        """Creates a new chat session, optionally with an initial message."""
        now = _dt.datetime.now(_dt.timezone.utc)
        chat_ref = self._chats_coll.document() # Generate ref first to get ID
        chat_data = {
            "title": _DEFAULT_CHAT_TITLE,
            "createdAt": now,
            "lastActivity": now,
        }
        chat_ref.set(chat_data)
        logging.info(f"Created new chat with ID: {chat_ref.id}")

        if initial_message:
            # Use the updated add_message_to_chat which handles timestamp etc.
            self.add_message_to_chat(chat_ref.id, initial_message)
            # Note: This won't update the lastActivity of the main chat doc unless called explicitly
            # For simplicity, we might rely on the first user message to set lastActivity later

        return ChatMetadata(
            id=chat_ref.id,
            title=_DEFAULT_CHAT_TITLE,
            createdAt=now,
            lastActivity=now
        )

    def list_chats(self) -> List[ChatMetadata]:
        """Lists all chat sessions, ordered by most recent activity."""
        chats_stream = self._chats_coll.order_by("lastActivity", direction=firestore.Query.DESCENDING).stream()
        chats = []
        for chat in chats_stream:
            data = chat.to_dict()
            # Ensure timestamps are datetime objects
            created_at = data.get("createdAt")
            last_activity = data.get("lastActivity")
            if not isinstance(created_at, _dt.datetime):
                 created_at = None # Or handle potential string conversion if needed
            if not isinstance(last_activity, _dt.datetime):
                 last_activity = None

            chats.append(ChatMetadata(
                id=chat.id,
                title=data.get("title", _DEFAULT_CHAT_TITLE),
                createdAt=created_at,
                lastActivity=last_activity
            ))
        return chats

    def get_chat_messages(self, chat_id: str) -> List[ChatMessage]:
        """Retrieves all messages for a given chat, ordered by timestamp."""
        chat_ref = self._chats_coll.document(chat_id)
        # Check if chat exists before querying subcollection
        if not chat_ref.get().exists:
             raise NotFound(f"Chat with ID {chat_id} not found")

        messages_stream = chat_ref.collection("messages").order_by("timestamp", direction=firestore.Query.ASCENDING).stream()
        messages = []
        for msg in messages_stream:
            data = msg.to_dict()
            src_raw = data.get("sources") or []
            sources = [DocumentSource(**s) for s in src_raw] if src_raw else None

            messages.append(
                ChatMessage(
                    id=msg.id,
                    text=data.get("text", ""),
                    sender=data.get("sender", "bot"),
                    timestamp=data.get("timestamp"),
                    sources=sources,
                )
            )
        return messages

    def add_message_to_chat(self, chat_id: str, message: ChatMessage) -> ChatMessage:
        """
        Adds a message to a chat's subcollection, updates lastActivity,
        and updates the title if it's the first user message.
        Returns the saved message.
        """
        chat_ref = self._chats_coll.document(chat_id)
        chat_snapshot = chat_ref.get() # Get current chat state first

        if not chat_snapshot.exists:
            raise NotFound(f"Chat with ID {chat_id} not found when trying to add message")

        chat_data = chat_snapshot.to_dict()
        messages_coll = chat_ref.collection("messages")
        message_ref   = messages_coll.document()

        # ------- build the Firestore payload -------------
        message_data = {
            "text":      message.text,
            "sender":    message.sender,
            "timestamp": SERVER_TIMESTAMP, # Use server timestamp for message
        }
        if message.sources:
            # store each DocumentSource as plain dict
            message_data["sources"] = [
                s.model_dump(exclude_none=True) for s in message.sources
            ]

        # Add the message document
        message_ref.set(message_data)

        # ------- Prepare update for the main chat document -------
        update_payload = {"lastActivity": SERVER_TIMESTAMP} # Always update lastActivity

        # Check if title needs updating (first user message in a default-titled chat)
        if message.sender == "user" and chat_data.get("title") == _DEFAULT_CHAT_TITLE:
            # Generate title from first user message
            settings = get_settings() # Get settings instance
            max_len = settings.max_chat_title_length
            new_title = message.text[:max_len] + ("..." if len(message.text) > max_len else "")
            if new_title: # Ensure title is not empty
                update_payload["title"] = new_title
                logging.info(f"Updating title for chat {chat_id} to '{new_title}' based on first user message.")

        # Update the main chat document (lastActivity and potentially title)
        # This handles the title update persistence directly
        chat_ref.update(update_payload)


        # --- Fetch the saved message data to return ---
        # Fetch again after set/update to get the actual server timestamp.
        saved_snapshot = message_ref.get()
        saved_data     = saved_snapshot.to_dict()

        # Assemble ChatMessage to return
        sources_out = (
            [DocumentSource(**src) for src in saved_data.get("sources", [])]
            if saved_data.get("sources")
            else None
        )

        return ChatMessage(
            id=message_ref.id,
            text=saved_data.get("text", ""),
            sender=saved_data.get("sender", message.sender),
            timestamp=saved_data.get("timestamp"), # Use timestamp from saved data
            sources=sources_out,
        )

    def update_chat_title(self, chat_id: str, new_title: str) -> None:
        """Updates the title of a specific chat."""
        # Note: This method is now less likely to be called directly for the
        # 'first message' scenario, but kept for potential explicit title updates.
        chat_ref = self._chats_coll.document(chat_id)
        try:
            chat_ref.update({"title": new_title})
            logging.info(f"Updated title for chat {chat_id} to '{new_title}'")
        except NotFound:
            raise NotFound(f"Chat with ID {chat_id} not found when trying to update title")
        except Exception as e:
            logging.error(f"Failed to update title for chat {chat_id}: {e}")
            raise # Re-raise the exception to ensure it's not swallowed

    def delete_chat(self, chat_id: str) -> None:
        """Deletes a chat document and its messages subcollection."""
        chat_ref = self._chats_coll.document(chat_id)
        # Check existence first to provide a cleaner 404 if needed
        if not chat_ref.get().exists:
            raise NotFound(f"Chat with ID {chat_id} not found for deletion.")

        # Delete messages subcollection (batched delete is more efficient for large chats)
        # Simple iterative delete for now:
        messages_stream = chat_ref.collection("messages").stream()
        deleted_count = 0
        batch = self.db.batch()
        for msg in messages_stream:
            batch.delete(msg.reference)
            deleted_count += 1
            if deleted_count % 400 == 0: # Commit every 400 deletes
                 batch.commit()
                 batch = self.db.batch() # Start new batch
        if deleted_count % 400 != 0: # Commit remaining deletes
            batch.commit()

        # Delete the main chat document
        chat_ref.delete()
        logging.info(f"Deleted chat {chat_id} and {deleted_count} messages.")



