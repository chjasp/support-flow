import os, uuid, logging
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_cloudsql_repo
from app.services.cloudsql import CloudSqlRepository
from app.models.domain import DocumentItem

router = APIRouter(prefix="", tags=["documents"])

@router.get("/documents", response_model=list[DocumentItem])
async def list_documents(repo: CloudSqlRepository = Depends(get_cloudsql_repo)):
    """Lists documents and their status from Cloud SQL."""
    try:
        return repo.list_documents()
    except Exception as e:
        logging.error(f"Failed to list documents from Cloud SQL: {e}", exc_info=True)
        # Consider more specific error handling based on repo exceptions
        raise HTTPException(status_code=500, detail="Failed to retrieve document list.")

@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: str,
                          repo: CloudSqlRepository = Depends(get_cloudsql_repo)):
    """Deletes a document record from Cloud SQL."""
    try:
        repo.delete_document(doc_id)
    except KeyError: # Raised by repo if not found
        raise HTTPException(status_code=404, detail="Document not found")
    except ValueError: # Raised by repo if UUID format is invalid
        raise HTTPException(status_code=400, detail="Invalid document ID format.")
    except Exception as e:
        logging.error(f"Failed to delete document {doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete document.")
    # No return needed on 204
