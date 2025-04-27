import datetime as _dt
import logging
import re
from typing import Any, Dict, List, Tuple, Optional

from google.cloud import firestore
from google.api_core.exceptions import NotFound

from app.config import get_settings
from app.models.domain import ChatMessage, ChatMetadata # Import chat models

_DEFAULT_CHAT_TITLE = "New Chat"

# Define a simple structure for the interaction data (can be formalized in domain.py if preferred)
class EmailInteractionData:
    def __init__(self, id: str, replyDraft: Optional[str] = None, refinementHistory: Optional[List[ChatMessage]] = None, lastUpdated: Optional[_dt.datetime] = None):
        self.id = id
        self.replyDraft = replyDraft if replyDraft is not None else "" # Default to empty string
        self.refinementHistory = refinementHistory if refinementHistory is not None else [] # Default to empty list
        self.lastUpdated = lastUpdated


class FirestoreRepository:
    """Repository for interacting with Chat and Email Interaction data in Firestore."""
    def __init__(self) -> None:
        cfg = get_settings()
        logging.info("Initialising Firestore client …")
        self._db = firestore.Client(project=cfg.gcp_project)
        self._chats_coll = self._db.collection("chats") # Chat collection reference
        self._email_interactions_coll = self._db.collection("email_interactions") # New collection reference

    # --------------------------------------------------------------------- #
    # document persistence methods removed
    # (save_document_metadata, list_documents, delete_document)
    # --------------------------------------------------------------------- #


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

    # --- Email Interaction Persistence ---

    def get_email_interaction(self, email_id: str) -> Optional[EmailInteractionData]:
        """Retrieves the interaction data (draft, history) for a given email ID."""
        doc_ref = self._email_interactions_coll.document(email_id)
        doc = doc_ref.get()
        if not doc.exists:
            logging.info(f"No interaction data found for email {email_id}.")
            # Return default structure instead of None for easier frontend handling
            return EmailInteractionData(id=email_id)
        try:
            data = doc.to_dict()
            # Convert Firestore array to list of ChatMessage objects if needed
            # Assuming stored history matches ChatMessage structure {sender: str, text: str}
            history_raw = data.get("refinementHistory", [])
            history = [ChatMessage(**msg) for msg in history_raw]

            return EmailInteractionData(
                id=doc.id,
                replyDraft=data.get("replyDraft"),
                refinementHistory=history,
                lastUpdated=data.get("lastUpdated") # Ensure this is datetime if needed, else ignore
            )
        except Exception as e:
            logging.error(f"Error parsing interaction data for email {email_id}: {e}", exc_info=True)
            # Return default on error? Or raise? Let's return default for now.
            return EmailInteractionData(id=email_id)


    def update_reply_draft(self, email_id: str, draft: str) -> None:
        """Updates or creates the reply draft for an email interaction."""
        doc_ref = self._email_interactions_coll.document(email_id)
        now = firestore.SERVER_TIMESTAMP
        try:
            # Use set with merge=True to create or update
            doc_ref.set({"replyDraft": draft, "lastUpdated": now}, merge=True)
            logging.info(f"Updated reply draft for email {email_id}.")
        except Exception as e:
            logging.error(f"Failed to update reply draft for email {email_id}: {e}", exc_info=True)
            raise # Re-raise to be handled by API layer

    def add_refinement_message(self, email_id: str, message: ChatMessage) -> None:
        """Adds a message to the refinement history for an email interaction."""
        doc_ref = self._email_interactions_coll.document(email_id)
        now = firestore.SERVER_TIMESTAMP
        # Convert Pydantic model to dict, ensuring only expected fields are included
        # Assuming ChatMessage has 'sender' and 'text'
        message_dict = {"sender": message.sender, "text": message.text}

        try:
             # Use firestore.ArrayUnion
             # Use set with merge=True to ensure document exists if adding first message
            doc_ref.set({
                "refinementHistory": firestore.ArrayUnion([message_dict]),
                "lastUpdated": now
            }, merge=True)
            logging.info(f"Added refinement message from {message.sender} for email {email_id}.")
        except Exception as e:
            logging.error(f"Failed to add refinement message for email {email_id}: {e}", exc_info=True)
            raise # Re-raise

    def clear_refinement_history(self, email_id: str) -> None:
        """Clears the refinement history for a specific email interaction."""
        doc_ref = self._email_interactions_coll.document(email_id)
        now = firestore.SERVER_TIMESTAMP
        try:
            # Update the history field to an empty array
            # Use update, assuming the document might exist (if not, it won't fail)
            doc_ref.update({
                "refinementHistory": [],
                "lastUpdated": now
            })
            logging.info(f"Cleared refinement history for email {email_id}.")
        except NotFound:
            logging.warning(f"No interaction document found for email {email_id} when trying to clear history. No action taken.")
            # No need to raise, clearing non-existent history is not an error
        except Exception as e:
            logging.error(f"Failed to clear refinement history for email {email_id}: {e}", exc_info=True)
            raise # Re-raise other errors

    # Optional: Clear interaction data if needed (delete whole document)
    def delete_email_interaction(self, email_id: str) -> None:
        """Deletes the interaction data for a given email ID."""
        doc_ref = self._email_interactions_coll.document(email_id)
        try:
            doc_ref.delete()
            logging.info(f"Deleted interaction data for email {email_id}.")
        except NotFound:
             logging.warning(f"No interaction data found to delete for email {email_id}.")
        except Exception as e:
            logging.error(f"Failed to delete interaction data for email {email_id}: {e}", exc_info=True)
            raise
