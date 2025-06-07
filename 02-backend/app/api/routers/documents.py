import logging
from fastapi import APIRouter, Depends, HTTPException, status, Path
from typing import List

from app.api.deps import get_cloudsql_repo
from app.services.cloudsql import CloudSqlRepository
from app.models.domain import DocumentItem
from app.api.auth import verify_token

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(verify_token)]
)

@router.get("/", response_model=List[DocumentItem])
async def list_all_documents(
    sql_repo: CloudSqlRepository = Depends(get_cloudsql_repo),
):
    """Lists all documents in the knowledge base."""
    try:
        return sql_repo.list_documents()
    except Exception as e:
        logging.error(f"Error listing documents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve documents")

@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_single_document(
    doc_id: str = Path(..., description="The UUID of the document to delete"),
    sql_repo: CloudSqlRepository = Depends(get_cloudsql_repo),
):
    """Deletes a specific document by its ID."""
    try:
        # Call the delete method. It will raise KeyError if not found.
        sql_repo.delete_document(doc_id)
        # If no exception was raised, the deletion was successful.
        # The status_code=204 handles the success response automatically.
        return # Implicitly returns No Content

    except KeyError: # Catch the specific error for "not found"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    except ValueError: # Catch invalid UUID format from the repo
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid document ID format")
    except HTTPException as http_exc:
        raise http_exc # Re-raise other specific HTTP exceptions if needed
    except Exception as e:
        logging.error(f"Error deleting document {doc_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete document")