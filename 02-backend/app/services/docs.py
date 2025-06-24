"""CRUD service for user documents (Firestore)."""

import logging
import uuid
from datetime import datetime, timezone
from typing import List

from google.cloud import firestore
from fastapi import HTTPException

from ..models import DocumentItem

logger = logging.getLogger(__name__)


class DocumentService:
    """Simple wrapper around the `documents` collection."""

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
        docs = (
            self.db.collection("documents")
            .where("user_id", "==", user_id)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(50)
            .stream()
        )
        return [DocumentItem(**doc.to_dict()) for doc in docs]

    def delete_document(self, doc_id: str, user_id: str):
        doc_ref = self.db.collection("documents").document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc.to_dict().get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete")
        doc_ref.delete() 