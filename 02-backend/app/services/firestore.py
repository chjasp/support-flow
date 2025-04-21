import datetime as _dt
import logging
import re
from typing import Any, Dict, List, Tuple, Optional

from google.cloud import firestore
from google.api_core.exceptions import NotFound

from app.config import get_settings
from app.models.domain import ChatMessage, ChatMetadata # Import chat models

_STOPWORDS = {"a","an","the","is","in","it","of","for","on","with"}
_DEFAULT_CHAT_TITLE = "New Chat"

class FirestoreRepository:
    def __init__(self) -> None:
        cfg = get_settings()
        logging.info("Initialising Firestore client …")
        self._db = firestore.Client(project=cfg.gcp_project)
        self._max_ctx = cfg.max_context_chunks
        self._chats_coll = self._db.collection("chats") # Chat collection reference
        self._docs_coll = self._db.collection("documents") # Document collection reference

    # --------------------------------------------------------------------- #
    # document & chunk persistence
    # --------------------------------------------------------------------- #
    def save_document(self,
                      doc_id: str,
                      source_name: str,
                      doc_type: str,
                      gcs_uri: str | None,
                      chunks: List[Dict[str, Any]],
                      status: str = "Processing") -> None:
        doc_data = {
            "source_name": source_name,
            "document_type": doc_type,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "chunk_count": len(chunks),
            "status": status
        }
        if gcs_uri:
            doc_data["gcs_uri"] = gcs_uri

        doc_ref = self._docs_coll.document(doc_id)
        doc_ref.set(doc_data, merge=True)

        if chunks:
            batch = self._db.batch()
            for c in chunks:
                chunk_ref = doc_ref.collection("chunks").document(f"chunk_{c['chunk_order']}")
                batch.set(chunk_ref, {
                    "chunk_text": c["chunk_text"],
                    "summary": c["summary"],
                    "chunk_order": c["chunk_order"]
                })
            batch.commit()
            doc_ref.update({"status": "Ready"})
        else:
            doc_ref.update({"status": "Ready", "chunk_count": 0})

    # --------------------------------------------------------------------- #
    # search helpers
    # --------------------------------------------------------------------- #
    def keyword_search(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        tokens = [w for w in re.findall(r"\b\w+\b", query.lower()) if w not in _STOPWORDS]
        if not tokens:
            return []

        results: List[Dict[str, Any]] = []
        for chunk in self._db.collection_group("chunks").stream():
            data = chunk.to_dict()
            txt = data.get("chunk_text", "").lower()
            score = sum(1 for t in tokens if t in txt)
            if score:
                doc_ref = chunk.reference.parent.parent
                if doc_ref and doc_ref.parent.id == "documents": # Ensure it's from the documents collection
                    doc_id = doc_ref.id
                    results.append({
                        "doc_id": doc_id,
                        "chunk_id": chunk.id,
                        "chunk_text": data.get("chunk_text", ""),
                        "summary": data.get("summary", ""),
                        "chunk_order": data.get("chunk_order", -1),
                        "keyword_score": score
                    })
        results.sort(key=lambda x: x["keyword_score"], reverse=True)
        return results[:max_results]

    # --------------------------------------------------------------------- #
    # listing / deletion
    # --------------------------------------------------------------------- #
    def list_documents(self) -> List[Dict[str, Any]]:
        docs_stream = self._docs_coll.order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
        items = []
        for doc in docs_stream:
            d = doc.to_dict()
            ts = d.get("timestamp")
            date_added = str(ts) # Default
            if isinstance(ts, _dt.datetime):
                # Ensure timezone awareness or convert to UTC if needed
                date_added = ts.isoformat() # Use ISO format for consistency

            file_type = None
            if d.get("document_type") == "PDF" and '.' in d.get("source_name", ""):
                file_type = d["source_name"].split('.')[-1].upper()
            items.append({
                "id": doc.id,
                "name": d.get("source_name", "Untitled"),
                "type": "Document" if d.get("document_type") == "PDF" else "Pasted Text",
                "fileType": file_type,
                "dateAdded": date_added,
                "status": d.get("status", "Unknown"),
                "gcsUri": d.get("gcs_uri")
            })
        return items

    def delete_document(self, doc_id: str) -> None:
        doc_ref = self._docs_coll.document(doc_id)
        if not doc_ref.get().exists:
            raise KeyError(f"Document {doc_id} not found")
        # delete chunks
        for chunk in doc_ref.collection("chunks").stream():
            chunk.reference.delete()
        doc_ref.delete()

    # --------------------------------------------------------------------- #
    # Chat Persistence
    # --------------------------------------------------------------------- #
    def create_chat(self, initial_message: Optional[ChatMessage] = None) -> ChatMetadata:
        """Creates a new chat session."""
        chat_ref = self._chats_coll.document() # Auto-generate ID
        now = _dt.datetime.now(_dt.timezone.utc)
        chat_data = {
            "title": _DEFAULT_CHAT_TITLE,
            "createdAt": now,
            "lastActivity": now
        }
        chat_ref.set(chat_data)
        logging.info(f"Created new chat with ID: {chat_ref.id}")

        # Add initial message if provided (e.g., a welcome message)
        if initial_message:
             self.add_message_to_chat(chat_ref.id, initial_message)
             # Note: add_message_to_chat already updates lastActivity

        return ChatMetadata(
            id=chat_ref.id,
            title=chat_data["title"],
            createdAt=chat_data["createdAt"],
            lastActivity=chat_data["lastActivity"]
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
            ts = data.get("timestamp")
            if not isinstance(ts, _dt.datetime):
                ts = None # Or handle conversion

            messages.append(ChatMessage(
                id=msg.id,
                text=data.get("text", ""),
                sender=data.get("sender", "bot"), # Default sender? Decide policy
                timestamp=ts
            ))
        return messages

    def add_message_to_chat(self, chat_id: str, message: ChatMessage) -> str:
        """Adds a message to a chat's subcollection and updates lastActivity."""
        chat_ref = self._chats_coll.document(chat_id)
        msg_coll_ref = chat_ref.collection("messages")

        now = _dt.datetime.now(_dt.timezone.utc)
        message_data = {
            "text": message.text,
            "sender": message.sender,
            "timestamp": now # Use server timestamp for consistency
        }
        # Add message
        update_time, msg_ref = msg_coll_ref.add(message_data) # Auto-generate message ID
        logging.info(f"Added message {msg_ref.id} to chat {chat_id}")

        # Update chat's lastActivity timestamp in a transaction
        @firestore.transactional
        def update_last_activity(transaction, chat_doc_ref):
            # Check if chat still exists within transaction
            snapshot = chat_doc_ref.get(transaction=transaction)
            if not snapshot.exists:
                 raise NotFound(f"Chat {chat_id} not found during message add transaction.")
            transaction.update(chat_doc_ref, {"lastActivity": now})

        transaction = self._db.transaction()
        update_last_activity(transaction, chat_ref)

        return msg_ref.id # Return the generated message ID

    def update_chat_title(self, chat_id: str, new_title: str) -> None:
        """Updates the title of a specific chat."""
        chat_ref = self._chats_coll.document(chat_id)
        try:
            chat_ref.update({"title": new_title})
            logging.info(f"Updated title for chat {chat_id} to '{new_title}'")
        except NotFound:
             logging.error(f"Failed to update title: Chat {chat_id} not found.")
             raise # Re-raise the exception to be handled by the caller

    def delete_chat(self, chat_id: str) -> None:
        """Deletes a chat document and all its messages."""
        chat_ref = self._chats_coll.document(chat_id)
        if not chat_ref.get().exists:
            raise NotFound(f"Chat with ID {chat_id} not found")

        # Delete all messages in the subcollection first (important!)
        # Use a batch delete for efficiency if many messages are expected
        messages_ref = chat_ref.collection("messages")
        docs = messages_ref.limit(500).stream() # Limit batch size if needed
        deleted = 0
        batch = self._db.batch()
        for doc in docs:
            logging.debug(f"Deleting message {doc.id} from chat {chat_id}")
            batch.delete(doc.reference)
            deleted += 1
        if deleted > 0:
            batch.commit()
            logging.info(f"Deleted {deleted} messages from chat {chat_id}")
        # Consider handling more than 500 messages if necessary (looping batches)

        # Delete the chat document itself
        chat_ref.delete()
        logging.info(f"Deleted chat document {chat_id}")
