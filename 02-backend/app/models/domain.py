from pydantic import BaseModel, Field, validator
from typing import List, Optional
import datetime
import logging

class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    chunk_text: str
    summary: str
    chunk_order: int
    keyword_score: Optional[float] = None

class DocumentItem(BaseModel):
    id: str
    name: str
    type: str
    fileType: Optional[str] = None
    dateAdded: datetime.datetime | str
    status: str
    gcsUri: Optional[str] = None

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
    sender: str = Field(..., pattern="^(user|bot)$")
    timestamp: Optional[datetime.datetime] = None

    class Config:
        arbitrary_types_allowed = True

class ChatMetadata(BaseModel):
    id: str
    title: str
    createdAt: Optional[datetime.datetime] = None
    lastActivity: Optional[datetime.datetime] = None

    class Config:
        arbitrary_types_allowed = True

class NewChatResponse(BaseModel):
    id: str
    title: str
    messages: List[ChatMessage] = []
    createdAt: Optional[datetime.datetime] = None
    lastActivity: Optional[datetime.datetime] = None
