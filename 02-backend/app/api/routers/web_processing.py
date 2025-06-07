import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, ValidationError
import datetime
import uuid

from app.api.deps import get_cloudsql_repo
from app.services.cloudsql import CloudSqlRepository
from app.services.pubsub_service import get_pubsub_service, PubSubService
from app.api.auth import verify_token
from app.config import get_settings
from app.models.domain import (
    UrlProcessingRequest, ProcessingTaskResponse, ProcessingTaskStatus,
    TextProcessingRequest
)

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

# Pydantic models for 3D visualization
class Document3DResponse(BaseModel):
    """Representation of a document with 3D coordinates for the frontend."""

    id: str
    name: str
    type: str
    fileType: Optional[str] = None
    position: List[float]
    dateAdded: str
    status: str
    chunkCount: int
    url: Optional[str] = None

@router.post("/process-urls", response_model=ProcessingTaskResponse)
async def process_urls(
    request_obj: Request,
    sql_repo: CloudSqlRepository = Depends(get_cloudsql_repo),
    pubsub_service: PubSubService = Depends(get_pubsub_service)
):
    """
    Process a list of URLs using unified event-driven architecture.
    This endpoint publishes URL processing tasks to Pub/Sub for consistent processing.
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
        request = UrlProcessingRequest(**body_json)
        logging.info(f"Pydantic validation successful. URLs: {request.urls}")
        
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
    
    task_id = str(uuid.uuid4())
    
    try:
        # Create task record in database
        task_input_data = {
            "urls": request.urls,
            "description": request.description
        }
        
        sql_repo.create_processing_task(
            task_id=task_id,
            task_type="url_processing",
            input_data=task_input_data
        )
        
        # Publish to Pub/Sub for processing
        message_id = pubsub_service.publish_url_processing_task(
            task_id=task_id,
            urls=request.urls,
            description=request.description
        )
        
        logging.info(f"Created URL processing task {task_id} with {len(request.urls)} URLs. Message ID: {message_id}")
        
        return ProcessingTaskResponse(
            task_id=task_id,
            status="queued",
            message=f"Queued {len(request.urls)} URLs for processing",
            created_at=datetime.datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logging.error(f"Failed to create URL processing task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue URL processing task: {str(e)}"
        )

@router.get("/tasks/{task_id}", response_model=ProcessingTaskStatus)
async def get_task_status(
    task_id: str,
    sql_repo: CloudSqlRepository = Depends(get_cloudsql_repo)
):
    """Get the status of a processing task from the database."""
    try:
        task_data = sql_repo.get_processing_task(task_id)
        
        return ProcessingTaskStatus(
            task_id=task_data["task_id"],
            task_type=task_data["task_type"],
            status=task_data["status"],
            input_data=task_data["input_data"],
            result_data=task_data["result_data"],
            error_message=task_data["error_message"],
            created_at=task_data["created_at"].isoformat() if task_data["created_at"] else "",
            updated_at=task_data["updated_at"].isoformat() if task_data["updated_at"] else "",
            completed_at=task_data["completed_at"].isoformat() if task_data["completed_at"] else None
        )
        
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )
    except Exception as e:
        logging.error(f"Error retrieving task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve task status"
        )

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
        "https://cloud.google.com/sql/docs/mysql/quickstart",
        "https://cloud.google.com/functions/docs/quickstart-console",
        "https://cloud.google.com/firestore/docs/quickstart-servers"
    ]
    
    return {
        "urls": urls,
        "description": "Google Cloud documentation URLs for testing"
    }

@router.post("/process-text", response_model=ProcessingTaskResponse)
async def process_text(
    request: TextProcessingRequest,
    sql_repo: CloudSqlRepository = Depends(get_cloudsql_repo),
    pubsub_service: PubSubService = Depends(get_pubsub_service)
):
    """
    Process text content using unified event-driven architecture.
    This endpoint publishes text processing tasks to Pub/Sub.
    """
    task_id = str(uuid.uuid4())
    
    try:
        # Create task record in database
        task_input_data = {
            "content": request.content,
            "title": request.title,
            "content_type": request.content_type
        }
        
        sql_repo.create_processing_task(
            task_id=task_id,
            task_type="text_processing",
            input_data=task_input_data
        )
        
        # Publish to Pub/Sub for processing
        message_id = pubsub_service.publish_text_processing_task(
            task_id=task_id,
            content=request.content,
            title=request.title,
            content_type=request.content_type
        )
        
        logging.info(f"Created text processing task {task_id} for '{request.title}'. Message ID: {message_id}")
        
        return ProcessingTaskResponse(
            task_id=task_id,
            status="queued",
            message=f"Queued text content '{request.title}' for processing",
            created_at=datetime.datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logging.error(f"Failed to create text processing task: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue text processing task: {str(e)}"
        ) 