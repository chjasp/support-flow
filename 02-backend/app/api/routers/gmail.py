import logging
from typing import List, Dict, Optional
from fastapi import APIRouter, HTTPException, Query, Depends, status

from app.api.deps import get_gmail_service # <-- Use dependency injection
from app.services.gmail import GmailService

# Define response models (optional but good practice)
from pydantic import BaseModel, Field

class MessageMetadata(BaseModel):
    id: str
    threadId: Optional[str] = None
    subject: str
    from_email: Optional[str] = Field(None, alias="from") # Handle 'from' keyword
    date: Optional[str] = None # Keep as string ms epoch for now
    snippet: Optional[str] = None

    class Config:
        allow_population_by_field_name = True # Allow using 'from' in data

class MessageListResponse(BaseModel):
    messages: List[MessageMetadata]

class MessageBodyResponse(BaseModel):
    id: str
    body: str


# Use /api prefix consistent with mail.py
router = APIRouter(prefix="/api", tags=["gmail"])

@router.get("/messages", response_model=MessageListResponse)
async def list_messages_api(
    max_results: int = Query(20, le=100, description="Max messages to return"),
    gmail_svc: GmailService = Depends(get_gmail_service) # Inject service
):
    """Lists recent messages with basic metadata."""
    try:
        messages_data = gmail_svc.list_messages(max_results=max_results)
        # Pydantic will automatically handle the alias for 'from'
        return MessageListResponse(messages=messages_data)
    except ConnectionError as e:
         logging.error(f"Gmail connection error in list_messages: {e}")
         raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Could not connect to Gmail API: {e}")
    except Exception as e:
        logging.error(f"Error listing Gmail messages: {e}", exc_info=True)
        # Use a generic error message for the client
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list Gmail messages.")

@router.get("/messages/{msg_id}", response_model=MessageBodyResponse)
async def get_message_api(
    msg_id: str,
    gmail_svc: GmailService = Depends(get_gmail_service) # Inject service
):
    """Gets the plain text body of a specific message."""
    try:
        body_text = gmail_svc.get_message_body(msg_id)
        return MessageBodyResponse(id=msg_id, body=body_text)
    except ConnectionError as e:
         logging.error(f"Gmail connection error in get_message: {e}")
         raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Could not connect to Gmail API: {e}")
    except Exception as e:
        logging.error(f"Error getting Gmail message {msg_id}: {e}", exc_info=True)
        # Use a generic error message for the client
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve Gmail message.")
