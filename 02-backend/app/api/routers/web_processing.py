import logging
import requests
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from typing import List, Dict, Any
from pydantic import BaseModel, HttpUrl, ValidationError

from app.api.deps import get_cloudsql_repo
from app.services.cloudsql import CloudSqlRepository
from app.api.auth import verify_token
from app.config import get_settings

router = APIRouter(
    prefix="/web",
    tags=["web-processing"],
    dependencies=[Depends(verify_token)]
)

settings = get_settings()

# Pydantic models
class UrlProcessRequest(BaseModel):
    urls: List[HttpUrl]
    description: str = ""

class ProcessingResponse(BaseModel):
    task_id: str
    status: str
    message: str

class Document3DResponse(BaseModel):
    id: str
    name: str
    type: str
    chunks: List[Dict[str, Any]]

# In-memory task tracking (in production, use Redis or database)
processing_tasks = {}

def call_processing_service(urls: List[str]) -> Dict[str, Any]:
    """Call the processing service to handle URL processing."""
    processing_url = settings.processing_service_url
    
    try:
        response = requests.post(
            f"{processing_url}/process-urls",
            json={"urls": urls},
            timeout=300  # 5 minute timeout
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Error calling processing service: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Processing service unavailable"
        )

@router.post("/process-urls", response_model=ProcessingResponse)
async def process_urls(
    request_obj: Request,
    background_tasks: BackgroundTasks,
    sql_repo: CloudSqlRepository = Depends(get_cloudsql_repo)
):
    """
    Process a list of URLs for both RAG and 3D visualization.
    This endpoint triggers background processing and returns immediately.
    """
    # ===== LOGGING POINT 1: Raw Request Details =====
    logging.info("===== BACKEND URL PROCESSING DEBUG =====")
    logging.info(f"Request method: {request_obj.method}")
    logging.info(f"Request URL: {request_obj.url}")
    logging.info(f"Request headers: {dict(request_obj.headers)}")
    
    # Get the raw body for debugging
    body = await request_obj.body()
    logging.info(f"Raw request body: {body}")
    
    try:
        # Parse the body as JSON
        import json
        body_json = json.loads(body) if body else {}
        logging.info(f"Parsed JSON body: {body_json}")
        
        # ===== LOGGING POINT 2: Pydantic Validation =====
        logging.info("Attempting Pydantic validation...")
        request = UrlProcessRequest(**body_json)
        logging.info(f"Pydantic validation successful. URLs: {[str(url) for url in request.urls]}")
        
    except json.JSONDecodeError as e:
        logging.error(f"JSON parsing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {str(e)}"
        )
    except ValidationError as e:
        # ===== LOGGING POINT 3: Validation Error Details =====
        logging.error("===== PYDANTIC VALIDATION ERROR =====")
        logging.error(f"Validation error: {e}")
        logging.error(f"Error details: {e.errors()}")
        for error in e.errors():
            logging.error(f"Field: {error.get('loc')}, Type: {error.get('type')}, Message: {error.get('msg')}, Input: {error.get('input')}")
        logging.error("=====================================")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"URL validation failed: {e.errors()}"
        )
    except Exception as e:
        logging.error(f"Unexpected error during request processing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
    
    logging.info("================================")
    
    import uuid
    task_id = str(uuid.uuid4())
    
    # Convert HttpUrl objects to strings
    url_strings = [str(url) for url in request.urls]
    
    processing_tasks[task_id] = {
        'status': 'processing',
        'urls': url_strings,
        'description': request.description,
        'created_at': str(datetime.utcnow())
    }
    
    # Add background task
    background_tasks.add_task(process_urls_background, task_id, url_strings)
    
    return ProcessingResponse(
        task_id=task_id,
        status="processing",
        message=f"Started processing {len(url_strings)} URLs"
    )

async def process_urls_background(task_id: str, urls: List[str]):
    """Background task to process URLs."""
    try:
        result = call_processing_service(urls)
        processing_tasks[task_id].update({
            'status': 'completed',
            'result': result,
            'completed_at': str(datetime.utcnow())
        })
        logging.info(f"Task {task_id} completed successfully")
    except Exception as e:
        processing_tasks[task_id].update({
            'status': 'failed',
            'error': str(e),
            'completed_at': str(datetime.utcnow())
        })
        logging.error(f"Task {task_id} failed: {e}")

@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Get the status of a processing task."""
    if task_id not in processing_tasks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    return processing_tasks[task_id]

@router.get("/documents-3d", response_model=List[Document3DResponse])
async def get_documents_3d(
    sql_repo: CloudSqlRepository = Depends(get_cloudsql_repo)
):
    """
    Get all documents with their 3D coordinates for visualization.
    """
    try:
        return sql_repo.get_documents_with_3d_coords()
    except Exception as e:
        logging.error(f"Error retrieving 3D documents: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve 3D document data"
        )

@router.get("/google-cloud-urls")
async def get_google_cloud_urls():
    """Get predefined Google Cloud documentation URLs for easy processing."""
    urls = [
        "https://cloud.google.com/docs/overview",
        "https://cloud.google.com/compute/docs/instances/create-start-instance",
        "https://cloud.google.com/storage/docs/creating-buckets",
        "https://cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-service",
        "https://cloud.google.com/vertex-ai/docs/tutorials/text-classification-automl",
        "https://cloud.google.com/bigquery/docs/quickstarts/load-data-console",
        "https://cloud.google.com/kubernetes-engine/docs/quickstart",
        "https://cloud.google.com/functions/docs/quickstart-python",
        "https://cloud.google.com/sql/docs/mysql/quickstart",
        "https://cloud.google.com/firestore/docs/quickstart-servers",
        "https://cloud.google.com/pubsub/docs/quickstart-console",
        "https://cloud.google.com/iam/docs/understanding-roles",
        "https://cloud.google.com/security/security-design",
        "https://cloud.google.com/architecture/framework",
        "https://cloud.google.com/docs/security/best-practices"
    ]
    
    return {
        "urls": urls,
        "count": len(urls),
        "description": "Curated Google Cloud documentation URLs for processing"
    }

@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a completed or failed task from memory."""
    if task_id not in processing_tasks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    
    del processing_tasks[task_id]
    return {"message": "Task deleted successfully"}

# Import datetime here to avoid circular imports
from datetime import datetime 