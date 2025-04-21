import base64, json, uuid, os, logging
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.deps import get_pipeline
from app.services.pipeline import DocumentPipeline

router = APIRouter(prefix="/event", tags=["events"])

class PubSubMessage(Dict):
    data: str

@router.post("/gcs")
async def gcs_event(msg: Dict,
                    tasks: BackgroundTasks,
                    pipeline: DocumentPipeline = Depends(get_pipeline)):
    payload = msg.get("message", {})
    data_b64 = payload.get("data", "")
    if not data_b64:
        return {"status": "error", "message": "empty data"}

    data_json = json.loads(base64.b64decode(data_b64).decode())
    bucket = data_json["bucket"]
    name = data_json["name"]
    gcs_uri = f"gs://{bucket}/{name}"

    original_name = os.path.basename(name).split('-', 1)[-1]
    if name.lower().endswith('.pdf'):
        tasks.add_task(pipeline.process_pdf, gcs_uri, original_name=original_name)
    elif name.lower().endswith('.txt'):
        tasks.add_task(pipeline.process_text, gcs_uri, original_name=original_name)
    else:
        return {"status": "ignored", "reason": "unsupported file"}
    return {"status": "accepted"}
