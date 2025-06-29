"""Pydantic data models shared across the application."""

import datetime as _dt
from typing import Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    id: Optional[str] = None
    text: str
    sender: str  # "user" | "bot"
    timestamp: Optional[_dt.datetime] = None


class ChatSession(BaseModel):
    id: str
    title: str
    created_at: _dt.datetime
    updated_at: _dt.datetime


class QueryRequest(BaseModel):
    query: str
    model_name: str
