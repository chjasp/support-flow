"""
Cloud Run entry point that:
  1. Receives a Cloud Storage 'Object Finalize' event (via Eventarc POST).
  2. Downloads the file.
  3. Converts to PDF if needed.
  4. Calls Vertex AI Gemini 2.0-flash to extract structured JSON.
  5. Chunks, embeds, and stores vectors + meta in Cloud SQL (pgvector).
  6. Uploads the JSON artefact to the processed bucket.
"""

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import List

import tiktoken
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from google.cloud import storage
from google.cloud.sql.connector import Connector
import traceback

# Add new vertexai imports
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from vertexai.language_models import TextEmbeddingModel

# ---------------------------------------------------------------------------
# Environment                                                               |
# ---------------------------------------------------------------------------

PROJECT_ID        = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION          = os.environ.get("LOCATION", "europe-west3")
RAW_BUCKET        = os.environ["RAW_BUCKET"]
PROCESSED_BUCKET  = os.environ["PROCESSED_BUCKET"]
INSTANCE_CONNECTION_NAME = os.environ["CLOUD_SQL_INSTANCE"]  # project:region:instance
DB_USER           = os.environ["CLOUD_SQL_USER"]
DB_PASS           = os.environ["CLOUD_SQL_PASSWORD"]
DB_NAME           = os.environ["CLOUD_SQL_DB"]
EMBED_MODEL       = os.environ["EMBED_MODEL"]
GEMINI_MODEL      = os.environ["GEMINI_MODEL"]

# Initialize Vertex AI
vertexai.init(project=PROJECT_ID, location=LOCATION)

storage_client = storage.Client(project=PROJECT_ID)
tokenizer       = tiktoken.get_encoding("cl100k_base")

# Instantiate models globally
extraction_model = GenerativeModel(GEMINI_MODEL)
embedding_model = TextEmbeddingModel.from_pretrained(EMBED_MODEL)

app = FastAPI()
connector = Connector()

# ---------------------------------------------------------------------------
# Helpers                                                                    |
# ---------------------------------------------------------------------------


def _connect():
    return connector.connect(
        INSTANCE_CONNECTION_NAME,
        "pg8000",
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        ip_type="PRIVATE"
    )


def _chunk(text: str, max_tokens: int = 800, overlap: int = 200) -> List[str]:
    tokens = tokenizer.encode(text)
    out = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_txt = tokenizer.decode(tokens[start:end])
        out.append(chunk_txt)
        start = max(end - overlap, end) if overlap else end
    return out


def _docx_to_pdf(src: Path, dst: Path):
    """
    Uses LibreOffice in headless mode. Cloud Run base image must include libreoffice.
    """
    try:
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", dst.parent, src],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"LibreOffice failure: {exc.stderr.decode()}") from exc


def _ensure_pdf(local_path: Path) -> Path:
    if local_path.suffix.lower() == ".pdf":
        return local_path
    if local_path.suffix.lower() in {".docx", ".doc"}:
        pdf_path = local_path.with_suffix(".pdf")
        _docx_to_pdf(local_path, pdf_path)
        return pdf_path
    if local_path.suffix.lower() in {".txt"}:
        pdf_path = local_path.with_suffix(".pdf")
        pdf_path.write_text(local_path.read_text())
        return pdf_path
    raise ValueError(f"Unsupported file type: {local_path.suffix}")


def _gemini_extract(pdf_path: Path) -> dict:
    """Extracts structured JSON from a PDF using Gemini."""
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
    # Refined prompt for better JSON compliance
    prompt = (
        "You are an expert JSON extraction engine. Analyze the provided document page by page. "
        "Your task is to generate a **single, valid JSON array** as your output. Do not include any text before or after the JSON array. "
        "Each element in the array must be a JSON object representing a single page. "
        "Each page object must have the following structure: "
        "{ \"page\": <page_number_integer>, \"header\": \"<extracted_header_text_or_null>\", \"body\": \"<extracted_body_text>\" }. "
        "Infer page numbers starting from 1. Extract the main text content for the 'body'. If no header is present, use null for the 'header' value. "
        "**Crucially, ensure all string values within the JSON are correctly escaped (e.g., double quotes inside strings should be represented as \\\", backslashes as \\\\, newlines as \\n).** "
        "The final output MUST be parsable by a standard JSON parser."
    )


    # Use the globally instantiated model
    # Add generation_config to enforce JSON output
    response = extraction_model.generate_content(
        [pdf_part, prompt],
        generation_config={"response_mime_type": "application/json"}
    )

    try:
        # Clean potential markdown/code block formatting (might be less necessary with response_mime_type)
        cleaned_response = response.text.strip().lstrip("```json").rstrip("```")
        return json.loads(cleaned_response)
    except (json.JSONDecodeError, AttributeError, ValueError) as e:
        print(f"ERROR: Failed to parse Gemini JSON response: {e}")
        # Log the problematic string before raising
        print(f"Raw Gemini Response Text causing error: {getattr(response, 'text', 'N/A')}")
        # Consider adding a comment suggesting checking the GEMINI_MODEL env var
        # If issues persist, consider using a more powerful model like gemini-1.0-pro or gemini-1.5-pro
        # if the current GEMINI_MODEL is gemini-1.0-flash.
        raise ValueError(f"Failed to parse JSON from Gemini response: {e}") from e


def _embed_chunks(chunks: List[str]) -> List[List[float]]:
    """Embeds text chunks using the specified embedding model."""
    # Use the globally instantiated model
    # Note: get_embeddings typically handles batching internally, but check limits if chunks list is huge.
    embeddings = embedding_model.get_embeddings([c for c in chunks])
    return [e.values for e in embeddings]


def _upsert(
    conn,
    doc_id: uuid.UUID,
    filename: str,
    raw_path: str,
    processed_path: str,
    chunks: List[str],
    vectors: List[List[float]],
):
    cur = None # Initialize cursor variable
    try:
        cur = conn.cursor() # Create cursor manually
        cur.execute(
            """
            INSERT INTO documents(id, filename, original_gcs, processed_gcs)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (doc_id, filename, raw_path, processed_path),
        )
        # Convert each vector list to its string representation '[f1, f2, ...]'
        # which is the format expected by pgvector's vector type input function.
        cur.executemany(
            """
            INSERT INTO chunks(doc_id, chunk_index, text, embedding)
            VALUES (%s, %s, %s, %s)
            """,
            [(doc_id, idx, text, str(vector)) for idx, (text, vector) in enumerate(zip(chunks, vectors))],
        )
        conn.commit() # Commit the transaction
    finally:
        if cur:
            cur.close() # Ensure cursor is closed


# ---------------------------------------------------------------------------
# HTTP handler                                                               |
# ---------------------------------------------------------------------------

@app.post("/")
async def ingest(request: Request):
    event = await request.json()  # CloudEvent JSON or direct GCS notification
    # Add logging to see the received event structure
    print(f"DEBUG: Received Event: {json.dumps(event, indent=2)}")

    # Access 'bucket' and 'name' directly from the event object
    # This handles both direct GCS notifications and CloudEvents wrapped payloads (if 'data' exists)
    payload = event.get("data") if "data" in event else event

    if not isinstance(payload, dict):
         print(f"ERROR: Event payload is not a dictionary. Event: {event}")
         raise HTTPException(status_code=400, detail="Invalid event payload: not a dictionary.")

    bucket = payload.get("bucket")
    name = payload.get("name")

    # Check if 'bucket' or 'name' are missing
    if not bucket or not name:
        print(f"ERROR: 'bucket' or 'name' missing in event payload. Payload: {payload}")
        raise HTTPException(status_code=400, detail="Invalid event payload: 'bucket' or 'name' missing.")

    # Check if the event is for the correct bucket
    if bucket != RAW_BUCKET:
         print(f"ERROR: Received event for unexpected bucket '{bucket}'. Expected '{RAW_BUCKET}'.")
         # Consider returning 2xx to ACK but not process, or keep 400 for invalid request.
         raise HTTPException(status_code=400, detail=f"Event received for unexpected bucket: {bucket}")

    doc_id = uuid.uuid4()
    temp_dir = Path(tempfile.mkdtemp())
    local_path = temp_dir / Path(name).name

    # Download
    blob = storage_client.bucket(bucket).blob(name)
    blob.download_to_filename(str(local_path))

    try:
        pdf_path = _ensure_pdf(local_path)
        struct_json = _gemini_extract(pdf_path)

        # Basic validation of the extracted structure
        if not isinstance(struct_json, list) or not all(isinstance(item, dict) and 'body' in item for item in struct_json):
             print(f"ERROR: Extracted JSON is not in the expected format. Got: {struct_json}")
             raise HTTPException(status_code=500, detail="Failed to extract valid structured data from PDF.")

        json_name = f"{doc_id}.json"
        json_blob = storage_client.bucket(PROCESSED_BUCKET).blob(json_name)
        json_blob.upload_from_string(json.dumps(struct_json), content_type="application/json")

        all_text = " ".join([p.get("body", "") for p in struct_json if p.get("body")])
        chunks = _chunk(all_text)
        vectors = _embed_chunks(chunks)

        with _connect() as conn:
            _upsert(
                conn,
                doc_id,
                name,
                f"gs://{RAW_BUCKET}/{name}",
                f"gs://{PROCESSED_BUCKET}/{json_name}",
                chunks,
                vectors,
            )
    except Exception as exc:
        # Log the full traceback for detailed debugging
        print(f"ERROR: Exception during processing file '{name}' from bucket '{bucket}': {exc}")
        print("--- Traceback ---")
        print(traceback.format_exc()) # Log the detailed traceback
        print("--- End Traceback ---")
        # Re-raise as HTTPException for FastAPI to handle
        raise HTTPException(status_code=500, detail=f"Internal server error processing file: {name}. Check logs for details.") from exc
    finally:
        # Clean up temporary files
        try:
            for f in temp_dir.iterdir():
                f.unlink()
            temp_dir.rmdir()
        except OSError as e:
            # Log cleanup error but don't let it mask the original exception
            print(f"WARNING: Error cleaning up temp directory {temp_dir}: {e}")

    return {"status": "ok", "doc_id": str(doc_id)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
