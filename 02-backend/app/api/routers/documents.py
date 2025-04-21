import os, uuid, logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.api.deps import get_pipeline, get_repo
from app.services.pipeline import DocumentPipeline
from app.services.firestore import FirestoreRepository
from app.models.domain import DocumentItem
from app.models.api_io import ProcessFileRequest

router = APIRouter(prefix="", tags=["documents"])

@router.post("/process-file", status_code=status.HTTP_202_ACCEPTED)
async def process_file(req: ProcessFileRequest,
                       tasks: BackgroundTasks,
                       pipeline: DocumentPipeline = Depends(get_pipeline)):
    file_lower = req.gcs_uri.lower()
    if file_lower.endswith('.pdf'):
        tasks.add_task(pipeline.process_pdf, req.gcs_uri, original_name=req.original_filename)
    elif file_lower.endswith('.txt'):
        tasks.add_task(pipeline.process_text, req.gcs_uri, original_name=req.original_filename)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    return {"message": "accepted"}

@router.get("/documents", response_model=list[DocumentItem])
async def list_documents(repo: FirestoreRepository = Depends(get_repo)):
    return repo.list_documents()

@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: str,
                          repo: FirestoreRepository = Depends(get_repo)):
    try:
        repo.delete_document(doc_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Document not found")
    return
