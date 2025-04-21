from pydantic import BaseModel, Field
from typing import Dict, Optional

class ProcessFileRequest(BaseModel):
    gcs_uri: str = Field(..., description="gs://bucket/file")
    original_filename: str
