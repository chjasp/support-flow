from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal, Dict
import datetime
import logging

class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    chunk_text: str
    summary: str
    chunk_order: int
    keyword_score: Optional[float] = None

class DocumentSource(BaseModel):
    id: str
    name: str
    uri: Optional[str] = None   # gcs uri, presigned url, etc.

class DocumentItem(BaseModel):
    id: str
    name: str
    type: str
    fileType: Optional[str] = None
    dateAdded: str
    status: str
    gcsUri: Optional[str] = None
    errorMessage: Optional[str] = None

    @validator('dateAdded', pre=True, always=True)
    def ensure_datetime_or_iso(cls, v):
        if isinstance(v, datetime.datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=datetime.timezone.utc)
            return v.isoformat()
        if isinstance(v, str):
            try:
                datetime.datetime.fromisoformat(v.replace('Z', '+00:00'))
                return v
            except ValueError:
                logging.warning(f"Could not parse dateAdded string: {v}")
                return str(v)
        return str(v)

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    answer: str
    retrieved_chunks: List[Chunk]

class ChatMessage(BaseModel):
    id: Optional[str] = None
    text: str
    sender: Literal["user", "ai", "bot"]
    timestamp: Optional[datetime.datetime] = None
    sources: Optional[List[DocumentSource]] = None

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime.datetime: lambda dt: dt.isoformat() if dt else None
        }

class ChatMetadata(BaseModel):
    id: str
    title: str
    createdAt: Optional[datetime.datetime] = None
    lastActivity: Optional[datetime.datetime] = None

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime.datetime: lambda dt: dt.isoformat() if dt else None
        }

class NewChatResponse(BaseModel):
    id: str
    title: str
    messages: List[ChatMessage] = []
    createdAt: Optional[datetime.datetime] = None
    lastActivity: Optional[datetime.datetime] = None

# --- Mail Generation Models ---
class GenerateReplyRequest(BaseModel):
    email_content: str

class GenerateReplyResponse(BaseModel):
    reply: str

# --- Mail Refinement Models ---
class RefineReplyRequest(BaseModel):
    email_content: str
    current_draft: str
    instruction: str

class RefineReplyResponse(BaseModel):
    refined_reply: str

# --- NEW: Model specifically for adding a refinement message ---
class AddRefinementMessageRequest(BaseModel):
    sender: Literal["user", "ai"]
    text: str

# --- Email Interaction Models (Used for GET response) ---
class EmailInteractionResponse(BaseModel):
    id: str
    replyDraft: Optional[str] = ""
    refinementHistory: List[ChatMessage] = []

class UpdateDraftRequest(BaseModel):
    draft: str

# --- Gmail API Models ---
class EmailHeader(BaseModel):
    name: str
    value: str

class EmailMetadata(BaseModel):
    id: str
    threadId: str
    labelIds: List[str] = []
    snippet: str
    subject: Optional[str] = None
    from_address: Optional[str] = Field(None, alias="from")
    date: Optional[str] = None

    class Config:
        allow_population_by_field_name = True

class EmailBodyResponse(BaseModel):
    body: str

# --- Document Processing Models ---
class ProcessRequest(BaseModel):
    gcs_uri: str
    original_filename: Optional[str] = None

class ProcessResponse(BaseModel):
    document_id: str
    message: str
    chunks_processed: int

# --- NEW: Response model for posting a message ---
class PostMessageResponse(BaseModel):
    user_message: ChatMessage
    bot_message: ChatMessage

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime.datetime: lambda dt: dt.isoformat() if dt else None
        }

# --- Unified Content Processing Models ---
class ContentProcessingTask(BaseModel):
    task_id: str
    task_type: Literal["url_processing", "text_processing", "file_processing"]
    status: Literal["queued", "processing", "completed", "failed"]
    input_data: Dict
    result_data: Optional[Dict] = None
    error_message: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    completed_at: Optional[datetime.datetime] = None

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime.datetime: lambda dt: dt.isoformat() if dt else None
        }

class UrlProcessingRequest(BaseModel):
    urls: List[str]
    description: str = ""

class TextProcessingRequest(BaseModel):
    content: str
    title: str
    content_type: str = "text/plain"

class ProcessingTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str
    created_at: str

class ProcessingTaskStatus(BaseModel):
    task_id: str
    task_type: str
    status: str
    input_data: Dict
    result_data: Optional[Dict] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None

# --- Pub/Sub Message Models ---
class ContentProcessingMessage(BaseModel):
    task_id: str
    task_type: Literal["url_processing", "text_processing", "file_processing"]
    input_data: Dict
    metadata: Optional[Dict] = None