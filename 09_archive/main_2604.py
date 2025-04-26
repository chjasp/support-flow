import json
import logging
import os
import subprocess
import tempfile
import traceback
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

import tiktoken
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from google.cloud import storage
from google.cloud.sql.connector import Connector

import vertexai
from vertexai.generative_models import GenerativeModel, Part
from vertexai.language_models import TextEmbeddingModel

###############################################################################
# Configuration + Globals
###############################################################################

PROJECT_ID: str = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION: str = os.environ.get("LOCATION", "europe-west3")
RAW_BUCKET: str = os.environ["RAW_BUCKET"]
PROCESSED_BUCKET: str = os.environ["PROCESSED_BUCKET"]
INSTANCE_CONNECTION_NAME: str = os.environ["CLOUD_SQL_INSTANCE"]
DB_USER: str = os.environ["CLOUD_SQL_USER"]
DB_PASS: str = os.environ["CLOUD_SQL_PASSWORD"]
DB_NAME: str = os.environ["CLOUD_SQL_DB"]
EMBED_MODEL: str = os.environ["EMBED_MODEL"]
GEMINI_MODEL: str = os.environ["GEMINI_MODEL"]

vertexai.init(project=PROJECT_ID, location=LOCATION)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("handler")

storage_client = storage.Client(project=PROJECT_ID)
connector = Connector()

tokenizer = tiktoken.get_encoding("cl100k_base")
extraction_model = GenerativeModel(GEMINI_MODEL)
embedding_model = TextEmbeddingModel.from_pretrained(EMBED_MODEL)

app = FastAPI()

###############################################################################
# Utility context‑managers / helpers
###############################################################################


@contextmanager
def _connect() -> Iterator["pg8000.Connection"]:
    """Yield a pg8000 connection; always close it afterwards."""
    conn = connector.connect(
        INSTANCE_CONNECTION_NAME,
        "pg8000",
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        ip_type="PRIVATE",
    )
    try:
        yield conn
    finally:
        conn.close()


def _chunk_text(text: str, /, *, max_tokens: int = 800, overlap: int = 200) -> List[str]:
    tokens = tokenizer.encode(text)
    segments: List[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        segments.append(tokenizer.decode(tokens[start:end]))
        if end == len(tokens):          # last chunk → quit
            break
        start = end - overlap if overlap else end
    return segments


def _docx_to_pdf(src: Path, dst: Path) -> None:
    """Convert DOC/DOCX file to PDF using LibreOffice."""
    try:
        subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(dst.parent),
                str(src),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"LibreOffice failure: {exc.stderr.decode()}") from exc


def _ensure_pdf(local_path: Path) -> Path:
    """Guarantee we have a PDF on disk; convert if necessary."""
    suffix = local_path.suffix.lower()
    if suffix == ".pdf":
        return local_path

    pdf_path = local_path.with_suffix(".pdf")

    if suffix in {".doc", ".docx"}:
        _docx_to_pdf(local_path, pdf_path)
        return pdf_path

    if suffix == ".txt":
        pdf_path.write_text(local_path.read_text())
        return pdf_path

    raise ValueError(f"Unsupported file type: {suffix}")


def _gemini_extract(pdf_path: Path) -> List[dict]:
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
    prompt = (
        "You are an expert JSON extraction engine. Produce a single JSON array where each element "
        "represents one page with keys: page (int), header (string|null), body (string). "
        "Escape all strings properly. Do not wrap with markdown fences."
    )

    response = extraction_model.generate_content(
        [pdf_part, prompt],
        generation_config={"response_mime_type": "application/json"},
    )

    cleaned = response.text.strip().lstrip("```json").rstrip("```")
    try:
        data: List[dict] = json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError) as e:
        logger.error("Failed to parse Gemini output: %s", e)
        logger.debug("Gemini raw response: %s", getattr(response, "text", "<none>"))
        raise
    return data


def _embed_chunks(chunks: List[str]) -> List[List[float]]:
    embeddings = embedding_model.get_embeddings(chunks)
    return [e.values for e in embeddings]

###############################################################################
# Database helpers
###############################################################################


def _fetch_existing(conn, gcs_path: str, generation: int) -> Optional[Tuple[uuid.UUID, str]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, status FROM documents WHERE original_gcs = %s AND gcs_generation = %s
        """,
        (gcs_path, generation),
    )
    result = cur.fetchone()
    cur.close()
    return result


def _insert_initial(conn, doc_id: uuid.UUID, filename: str, gcs_path: str, generation: int) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO documents(id, filename, original_gcs, gcs_generation, status)
        VALUES (%s, %s, %s, %s, 'Processing')
        """,
        (doc_id, filename, gcs_path, generation),
    )
    cur.close()


def _update_status(conn, doc_id: uuid.UUID, status: str, error: Optional[str] = None) -> None:
    cur = conn.cursor()
    cur.execute(
        "UPDATE documents SET status = %s, error_message = %s WHERE id = %s",
        (status, error, doc_id),
    )
    cur.close()


def _upsert_success(
    conn,
    doc_id: uuid.UUID,
    filename: str,
    raw_path: str,
    processed_path: str,
    chunks: List[str],
    vectors: List[List[float]],
) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE documents
        SET filename = %s, original_gcs = %s, processed_gcs = %s,
            status = 'Ready', error_message = NULL
        WHERE id = %s
        """,
        (filename, raw_path, processed_path, doc_id),
    )

    cur.execute("DELETE FROM chunks WHERE doc_id = %s", (doc_id,))
    cur.executemany(
        """
        INSERT INTO chunks(doc_id, chunk_index, text, embedding)
        VALUES (%s, %s, %s, %s)
        """,
        [
            (doc_id, idx, txt, str(vec))
            for idx, (txt, vec) in enumerate(zip(chunks, vectors))
        ],
    )
    cur.close()

###############################################################################
# Core processing logic
###############################################################################


def _process_blob(
    *,
    bucket_name: str,
    object_name: str,
    generation: int,
) -> dict:
    """Main orchestration for a single GCS object generation."""
    gcs_path = f"gs://{bucket_name}/{object_name}"
    filename = Path(object_name).name

    with _connect() as conn:
        # Idempotency / race‑condition handling
        existing = _fetch_existing(conn, gcs_path, generation)
        if existing:
            doc_id, status = existing
            if status in {"Ready", "Failed", "Processing"}:
                logger.info("Skipping %s (gen %s); status=%s", gcs_path, generation, status)
                return {"status": "skipped", "doc_id": str(doc_id), "reason": status}
        else:
            doc_id = uuid.uuid4()
            try:
                _insert_initial(conn, doc_id, filename, gcs_path, generation)
                conn.commit()
            except Exception as e:
                conn.rollback()
                # Assume unique constraint == race condition
                logger.warning("Race inserting initial record: %s", e)
                return {"status": "skipped", "reason": "race"}

    # At this point we own processing for this doc_id
    temp_dir = Path(tempfile.mkdtemp())
    try:
        blob = storage_client.bucket(bucket_name).get_blob(object_name, generation=generation)
        if not blob:
            raise FileNotFoundError("Blob (generation) not found")

        local_raw = temp_dir / filename
        blob.download_to_filename(str(local_raw))
        pdf_path = _ensure_pdf(local_raw)
        pages = _gemini_extract(pdf_path)

        processed_name = f"{doc_id}.json"
        processed_blob = storage_client.bucket(PROCESSED_BUCKET).blob(processed_name)
        processed_blob.upload_from_string(json.dumps(pages), content_type="application/json")
        processed_gcs_path = f"gs://{PROCESSED_BUCKET}/{processed_name}"

        full_text = " ".join(p.get("body", "") for p in pages if p.get("body"))
        chunks = _chunk_text(full_text)
        vectors = _embed_chunks(chunks)
        logger.info("%s produced %d chunks", doc_id, len(chunks))

        with _connect() as conn:
            _upsert_success(conn, doc_id, filename, gcs_path, processed_gcs_path, chunks, vectors)
            conn.commit()

        return {"status": "ok", "doc_id": str(doc_id)}

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("Processing failed: %s", error_msg)
        logger.debug(traceback.format_exc())
        with _connect() as conn:
            _update_status(conn, doc_id, "Failed", error_msg)
            conn.commit()
        raise HTTPException(status_code=500, detail=error_msg) from exc
    finally:
        # cleanup
        try:
            for p in temp_dir.iterdir():
                p.unlink()
            temp_dir.rmdir()
        except OSError as e:
            logger.warning("Failed to clean temp dir %s: %s", temp_dir, e)


###############################################################################
# HTTP entry‑point
###############################################################################


@app.post("/")
async def ingest(request: Request):
    event = await request.json()
    logger.debug("Received event: %s", event)

    payload = event.get("data") if "data" in event else event
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object")

    bucket = payload.get("bucket")
    name = payload.get("name")
    generation_str = payload.get("generation")

    if not bucket or not name or not generation_str:
        raise HTTPException(status_code=400, detail="bucket, name, generation required")

    try:
        generation = int(generation_str)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="generation must be int")

    if bucket != RAW_BUCKET:
        return {"status": "ignored", "reason": "wrong bucket"}

    return _process_blob(bucket_name=bucket, object_name=name, generation=generation)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
