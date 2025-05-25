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

import fitz  # PyMuPDF
import tiktoken
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from google.cloud import storage
from google.cloud.sql.connector import Connector
from pydantic import BaseModel

import vertexai
import google.genai as genai
from google.genai import types as genai_types
from vertexai.language_models import TextEmbeddingModel
from vertexai.generative_models import ToolConfig
from dotenv import load_dotenv

# Import the new scraper
from scraper import WebDocumentProcessor

load_dotenv()

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

# initialise Vertex AI **for embeddings only**
vertexai.init(project=PROJECT_ID, location=LOCATION)

# single Google Generative AI client used everywhere else
genai_client = genai.Client(
    vertexai=True,              # keep routing through Vertex endpoint
    project=PROJECT_ID,
    location="global",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("handler")

storage_client = storage.Client(project=PROJECT_ID)
connector = Connector()

tokenizer = tiktoken.get_encoding("cl100k_base")
# extraction_model = GenerativeModel(GEMINI_MODEL) # Removed - no longer used
embedding_model = TextEmbeddingModel.from_pretrained(EMBED_MODEL)

# Define the schema as a dictionary for controlled generation
PAGE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "page":   {"type": "integer"},
            "header": {"type": "string"},
            "body":   {"type": "string"}
        },
        "required": ["page", "body"]
    }
}
GEN_CONFIG = genai_types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=PAGE_SCHEMA,
    # response_modalities=["TEXT"], # Optional: Specify modality if needed, often inferred
    temperature=0,
    top_p=0.1,
    max_output_tokens=65535, # Adjusted based on common limits, check model specifics if needed <= model limit
    automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(
        disable=True                     # ←‑‑‑ really disables AFC
    ),
)
# -----------------------------------------

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
    """Guarantee we have a PDF on disk; convert DOC/DOCX if necessary. Returns original path for non-convertible types."""
    suffix = local_path.suffix.lower()
    if suffix == ".pdf":
        return local_path # Already PDF

    # Check if the target PDF already exists (e.g., from a previous partial run)
    pdf_path = local_path.with_suffix(".pdf")
    if pdf_path.exists():
        logger.info(f"Using existing converted PDF: {pdf_path}")
        return pdf_path

    if suffix in {".doc", ".docx"}:
        logger.info(f"Converting {local_path} to PDF...")
        _docx_to_pdf(local_path, pdf_path)
        logger.info(f"Conversion complete: {pdf_path}")
        # Verify conversion success
        if not pdf_path.exists() or pdf_path.stat().st_size == 0:
             raise RuntimeError(f"PDF conversion failed or produced an empty file for {local_path}")
        return pdf_path

    # If it's not DOC/DOCX or PDF, return the original path.
    # TXT files will be handled directly in the main logic.
    logger.info(f"File type '{suffix}' does not require PDF conversion. Using original: {local_path}")
    return local_path


def _make_part(data: bytes | str, mime_type: str = "text/plain") -> genai_types.Part:
    """Helper that mirrors Part.from_data from vertexai."""
    if isinstance(data, bytes):
        return genai_types.Part(
            inline_data=genai_types.Blob(
                mime_type=mime_type,
                data=data
            )
        )
    else:  # str
        return genai_types.Part(text=data)


def _gemini_extract(pdf_part: genai_types.Part) -> list[dict]:
    """Extracts page data from a PDF part using Gemini with controlled generation."""
    try:
        # Simpler prompt, relying on the schema for structure
        prompt = "Extract each page's content. Include page number, header (if any), and body text."

        # Build a single user message that contains the PDF and the instruction
        contents = [
            genai_types.Content(
                role="user",
                parts=[pdf_part, _make_part(prompt)] # Use helper for the text part
            )
        ]

        resp = genai_client.models.generate_content(   # <- note ".models"
            model=GEMINI_MODEL,
            contents=contents,
            config=GEN_CONFIG
            # stream=False # Default is False, not needed explicitly
        )


        # Check for response text and parse JSON
        if not resp.text:
            # Handle cases where the model might fail schema validation or return unexpected structure
            finish_reason = getattr(resp.candidates[0].finish_reason, 'name', 'UNKNOWN') if resp.candidates else 'NO_CANDIDATES'
            safety_ratings = getattr(resp.candidates[0], 'safety_ratings', []) if resp.candidates else []
            prompt_feedback = getattr(resp, 'prompt_feedback', None)
            logger.error(f"Gemini response was empty. Finish Reason: {finish_reason}, Safety Ratings: {safety_ratings}, Prompt Feedback: {prompt_feedback}")
            logger.debug("Gemini raw response: %s", resp)
            # Consider checking safety ratings and finish reason more closely
            if finish_reason not in ('STOP', 'MAX_TOKENS'): # Check if finish reason indicates an issue
                 raise RuntimeError(f"Gemini returned an empty response with finish reason: {finish_reason}")
            elif not resp.candidates or not resp.candidates[0].content.parts: # Check if content is actually missing
                 raise RuntimeError(f"Gemini returned an empty response. Finish Reason: {finish_reason}")
            # If finish reason is STOP/MAX_TOKENS but text is empty, it might be a schema validation failure on the model side
            # or an issue with the response structure not matching expectations.
            # Adding more detailed logging here can help.
            logger.warning(f"Gemini response text is empty despite finish reason {finish_reason}. Raw response: {resp}")
            # Depending on requirements, you might return an empty list or raise an error. Raising for now.
            raise RuntimeError(f"Gemini returned empty text despite finish reason {finish_reason}. Check schema or model behavior.")


        try:
            # Parse the JSON string from the response text
            cleaned = resp.text.strip().removeprefix("```json").removesuffix("```")
            output_data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("Failed to decode JSON response from Gemini: %s", e)
            logger.debug("Gemini raw text response: %s", resp.text)
            # Log finish reason etc. again for context
            finish_reason = getattr(resp.candidates[0].finish_reason, 'name', 'UNKNOWN') if resp.candidates else 'NO_CANDIDATES'
            safety_ratings = getattr(resp.candidates[0], 'safety_ratings', []) if resp.candidates else []
            prompt_feedback = getattr(resp, 'prompt_feedback', None)
            logger.error(f"JSON Decode Error Context - Finish Reason: {finish_reason}, Safety Ratings: {safety_ratings}, Prompt Feedback: {prompt_feedback}")
            raise RuntimeError("Gemini failed to produce valid JSON output.") from e

        # Basic validation (ensure it's a list as expected by the schema)
        if not isinstance(output_data, list):
            logger.error(f"Expected list from Gemini JSON, got {type(output_data)}")
            logger.debug("Parsed JSON data: %s", output_data)
            raise TypeError(f"Gemini output did not match expected schema type (list), got {type(output_data)}")

        # Optional: Add more validation here if needed (e.g., check dict keys)

        return output_data

    except Exception as e:
        logger.error("Error during Gemini extraction: %s", e)
        logger.debug(traceback.format_exc())
        # Include raw response in debug logs if available and not already logged
        if 'resp' in locals():
             logger.debug("Gemini raw response during exception: %s", resp)
        raise # Re-raise the exception


def _extract_paginated(pdf_path: Path, batch_size: int = 5) -> list[dict]:
    """Opens a PDF, extracts content in batches using Gemini, and returns combined JSON."""
    logger.info(f"Starting paginated extraction for {pdf_path} with batch size {batch_size}")
    all_pages_json = []
    doc = None # Initialize doc to None
    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
        logger.info(f"PDF has {total_pages} pages.")

        for start_page in range(0, total_pages, batch_size):
            end_page = min(start_page + batch_size, total_pages)
            logger.info(f"Processing pages {start_page + 1} to {end_page}...")

            # Create a new PDF fragment in memory containing only the pages for this batch
            batch_doc = fitz.open() # Create empty doc
            batch_doc.insert_pdf(doc, from_page=start_page, to_page=end_page - 1)
            pdf_fragment_bytes = batch_doc.tobytes()
            batch_doc.close()

            if not pdf_fragment_bytes:
                 logger.warning(f"Generated empty PDF fragment for pages {start_page+1}-{end_page}. Skipping batch.")
                 continue

            pdf_part = _make_part(pdf_fragment_bytes, mime_type="application/pdf")

            try:
                # Call the updated _gemini_extract for the batch
                batch_json = _gemini_extract(pdf_part)
                for page_data in batch_json:
                    if isinstance(page_data, dict) and 'page' in page_data:
                         page_data['page'] = page_data['page'] + start_page # Adjust page number
                    else:
                         logger.warning(f"Unexpected item format in batch JSON: {page_data}")

                all_pages_json.extend(batch_json)
                logger.info(f"Successfully processed batch {start_page+1}-{end_page}, got {len(batch_json)} pages.")
            except Exception as batch_exc:
                logger.error(f"Failed to process batch {start_page+1}-{end_page}: {batch_exc}")
                # Decide on error handling: continue, retry, or fail fast?
                # For now, let's fail fast if a batch fails.
                raise RuntimeError(f"Extraction failed on batch {start_page+1}-{end_page}") from batch_exc

        logger.info(f"Finished paginated extraction. Total pages extracted: {len(all_pages_json)}")
        return all_pages_json

    except fitz.FileNotFoundError:
        logger.error(f"PyMuPDF could not find or open file: {pdf_path}")
        raise
    except Exception as e:
        logger.error(f"Error during paginated extraction setup or loop for {pdf_path}: {e}")
        logger.debug(traceback.format_exc())
        raise # Re-raise other exceptions
    finally:
        if doc:
            doc.close() # Ensure the main document is closed


_EMBED_TOKEN_LIMIT = 20_000
_SAFETY_MARGIN     = 3_000
_EFFECTIVE_LIMIT   = _EMBED_TOKEN_LIMIT - _SAFETY_MARGIN

def _yield_token_batched(texts: list[str], limit: int = _EFFECTIVE_LIMIT):
    """Yield sub-lists whose total token count ≤ limit."""
    batch, running = [], 0
    for t in texts:
        tok = len(tokenizer.encode(t))
        # split pathological long chunk on the fly
        if tok > limit:
            sub = _chunk_text(t, max_tokens=limit - 1, overlap=0)
            for s in sub:
                yield [s]                     # each sub-chunk alone
            continue
        if running + tok > limit and batch:
            yield batch
            batch, running = [], 0
        batch.append(t)
        running += tok
    if batch:
        yield batch


def _embed_chunks(chunks: List[str]) -> List[List[float]]:
    all_vectors: List[List[float]] = []
    for sublist in _yield_token_batched(chunks):
        embs = embedding_model.get_embeddings(sublist)
        all_vectors.extend(e.values for e in embs)
    return all_vectors

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
    processed_path: Optional[str], # Allow None
    chunks: List[str],
    vectors: List[List[float]],
) -> None:
    cur = conn.cursor()
    # Update documents table, setting processed_gcs potentially to NULL
    cur.execute(
        """
        UPDATE documents
        SET filename = %s, original_gcs = %s, processed_gcs = %s,
            status = 'Ready', error_message = NULL
        WHERE id = %s
        """,
        (filename, raw_path, processed_path, doc_id), # Pass processed_path directly (can be None)
    )

    # Delete existing chunks first
    cur.execute("DELETE FROM chunks WHERE doc_id = %s", (doc_id,))

    # Insert new chunks only if there are any
    if chunks and vectors:
        cur.executemany(
            """
            INSERT INTO chunks(doc_id, chunk_index, text, embedding)
            VALUES (%s, %s, %s, %s::vector) -- Ensure embedding is cast to vector type if needed
            """,
            [
                (doc_id, idx, txt, str(vec)) # Convert vector list to string for pg8000
                for idx, (txt, vec) in enumerate(zip(chunks, vectors))
            ],
        )
    else:
        logger.info(f"No chunks to insert for doc_id {doc_id}.")

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
    # gcs_object_filename = Path(object_name).name # Keep the GCS object name - No longer primary source for local name

    # Initialize variables that might not be set in all paths
    doc_id = None
    temp_dir = Path(tempfile.mkdtemp())
    # original_filename = gcs_object_filename # Default fallback - Replaced below
    processed_gcs_path: Optional[str] = None # Initialize as None

    try:
        # --- Fetch Blob Metadata First ---
        blob = storage_client.bucket(bucket_name).get_blob(object_name, generation=generation)
        if not blob:
            # Clean up temp dir before raising
            try:
                for p in temp_dir.iterdir(): p.unlink(missing_ok=True) # Use missing_ok
                temp_dir.rmdir()
            except OSError as e: logger.warning("Failed to clean temp dir %s on blob not found: %s", temp_dir, e)
            raise FileNotFoundError(f"Blob not found: {gcs_path} (gen {generation})")

        metadata = blob.metadata or {}
        # Get original filename from metadata, fallback to GCS object name's base name
        gcs_base_name = Path(object_name).name
        original_filename_from_meta = metadata.get("originalfilename") # Get from metadata

        # Determine the filename to store in the DB (prefer metadata if available and non-empty)
        db_filename = original_filename_from_meta if original_filename_from_meta else gcs_base_name
        logger.info(f"Processing blob: {gcs_path} (gen {generation}), DB Filename: {db_filename}")
        # ---------------------------------

        # --- Determine File Type from GCS Object Name ---
        # This is more reliable than metadata for routing logic
        object_suffix = Path(object_name).suffix.lower()
        if not object_suffix:
             logger.warning(f"GCS object name '{object_name}' has no suffix. Cannot determine file type.")
             # Decide how to handle this - fail or treat as specific type? Failing for now.
             raise ValueError(f"Cannot determine file type: GCS object '{object_name}' lacks a suffix.")
        logger.info(f"Detected file type based on GCS object suffix: '{object_suffix}'")
        # ------------------------------------------------

        # --- Idempotency Check & Initial DB Insert ---
        with _connect() as conn:
            existing = _fetch_existing(conn, gcs_path, generation)
            if existing:
                doc_id, status = existing
                if status in {"Ready", "Failed", "Processing"}:
                    logger.info("Skipping %s (gen %s); status=%s (checked after metadata fetch)", gcs_path, generation, status)
                    return {"status": "skipped", "doc_id": str(doc_id), "reason": status}
                logger.info(f"Found existing record for {gcs_path} (gen {generation}) with status '{status}'. Will re-process with doc_id {doc_id}.")
            else:
                doc_id = uuid.uuid4()
                try:
                    # Use db_filename for the initial insert
                    _insert_initial(conn, doc_id, db_filename, gcs_path, generation)
                    conn.commit()
                    logger.info(f"Inserted initial record for doc_id {doc_id} with filename {db_filename}")
                except Exception as e: # Catch specific DB exceptions if possible
                    conn.rollback()
                    logger.warning("Race inserting initial record: %s. Attempting fetch again.", e)
                    existing_retry = _fetch_existing(conn, gcs_path, generation)
                    if existing_retry:
                         doc_id, status = existing_retry
                         logger.info("Skipping %s (gen %s); status=%s (found after insert race)", gcs_path, generation, status)
                         return {"status": "skipped", "doc_id": str(doc_id), "reason": "race"}
                    else:
                        raise RuntimeError(f"Failed to insert or find record after insert race for {gcs_path}") from e
        # -------------------------------------------

        # --- Download and Process based on file type ---
        # Use a safe local filename based on doc_id + original suffix from GCS object name
        # This avoids issues with weird characters in metadata filename
        local_safe_filename = f"{doc_id}{object_suffix}" # Already checked object_suffix exists
        local_download_path = temp_dir / local_safe_filename
        logger.info(f"Downloading {gcs_path} to {local_download_path}...")
        blob.download_to_filename(str(local_download_path))
        logger.info(f"Download complete.")

        full_text = ""
        extracted_pages_json: Optional[List[dict]] = None # Store extracted JSON data
        # processed_gcs_path remains None unless explicitly set below

        # Use object_suffix for routing
        if object_suffix == ".txt":
            logger.info(f"Processing as TXT file: {local_download_path}")
            try:
                # Try reading as UTF-8 first, common for text
                full_text = local_download_path.read_text(encoding='utf-8')
                logger.info(f"Read {len(full_text)} characters from TXT file (UTF-8).")
            except UnicodeDecodeError:
                 logger.warning(f"UTF-8 decoding failed for {local_download_path}. Trying latin-1.")
                 # Fallback to latin-1 if UTF-8 fails
                 full_text = local_download_path.read_text(encoding='latin-1')
                 logger.info(f"Read {len(full_text)} characters from TXT file using latin-1.")
            except Exception as read_err:
                 logger.error(f"Failed to read text file {local_download_path}: {read_err}")
                 raise # Re-raise read errors
            # No PDF conversion or Gemini extraction needed for TXT
            # processed_gcs_path remains None
            # extracted_pages_json remains None

        elif object_suffix in {".pdf", ".doc", ".docx"}:
            logger.info(f"Processing as document (needs PDF): {local_download_path}")
            # Pass the actual downloaded path to _ensure_pdf
            pdf_path = _ensure_pdf(local_download_path) # Convert DOCX to PDF if needed

            if not pdf_path.exists():
                 raise FileNotFoundError(f"PDF file not found or created at {pdf_path} from {local_download_path}")

            # Use the new paginated extraction function
            logger.info(f"Extracting content from PDF: {pdf_path} using paginated Gemini...")
            extracted_pages_json = _extract_paginated(pdf_path) # Returns list[dict]
            logger.info(f"Extracted {len(extracted_pages_json)} page structures from {pdf_path}.")

            # Upload extracted JSON to processed bucket if extraction was successful
            if extracted_pages_json is not None: # Check if list is not None (could be empty list)
                processed_name = f"{doc_id}.json"
                processed_blob = storage_client.bucket(PROCESSED_BUCKET).blob(processed_name)
                logger.info(f"Uploading extracted JSON ({len(extracted_pages_json)} pages) to gs://{PROCESSED_BUCKET}/{processed_name}")
                # Ensure proper JSON serialization
                try:
                    json_string = json.dumps(extracted_pages_json, ensure_ascii=False, indent=2) # Use indent for readability
                except TypeError as json_err:
                    logger.error(f"Failed to serialize extracted data to JSON: {json_err}")
                    raise RuntimeError("Failed to serialize extracted page data") from json_err

                processed_blob.upload_from_string(json_string, content_type="application/json; charset=utf-8") # Specify charset
                processed_gcs_path = f"gs://{PROCESSED_BUCKET}/{processed_name}" # Set processed path
                logger.info(f"Upload complete: {processed_gcs_path}")

                # Combine text from extracted pages for chunking
                full_text = " ".join(
                    p.get("body", "") for p in extracted_pages_json if isinstance(p, dict) and p.get("body")
                )
                logger.info(f"Combined text from JSON has {len(full_text)} characters.")
            else:
                 # This case should ideally not happen if _extract_paginated raises errors,
                 # but handle defensively.
                 logger.warning(f"Extraction resulted in None for {pdf_path}. No JSON uploaded, no text combined.")
                 full_text = "" # Ensure full_text is empty

        else:
            # If file type is unsupported based on GCS object suffix
            # Use object_suffix in the error message
            raise ValueError(f"Unsupported file type based on GCS object suffix: '{object_suffix}'")
        # ---------------------------------------------

        # --- Chunking and Embedding ---
        if not full_text:
             # Use db_filename in the log message
             logger.warning(f"No text content extracted or read from {db_filename}. Skipping chunking/embedding. Marking as Ready (empty).")
             chunks = []
             vectors = []
             # Still proceed to upsert success, but with empty chunks/vectors
        else:
            logger.info(f"Chunking text for {doc_id}...")
            chunks = _chunk_text(full_text)
            logger.info(f"Embedding {len(chunks)} chunks for {doc_id}...")
            vectors = _embed_chunks(chunks)
            logger.info(f"Embedding complete for {doc_id}.")
        # ----------------------------

        # --- Final DB Update ---
        with _connect() as conn:
            # Use db_filename and potentially None processed_gcs_path
            _upsert_success(conn, doc_id, db_filename, gcs_path, processed_gcs_path, chunks, vectors)
            conn.commit()
            logger.info(f"Successfully processed and updated record for doc_id {doc_id} with filename {db_filename}")
        # -----------------------

        return {"status": "ok", "doc_id": str(doc_id)}

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("Processing failed for %s (gen %s): %s", gcs_path, generation, error_msg)
        logger.debug(traceback.format_exc())

        # Ensure doc_id is defined for error update if possible
        doc_id_for_error = doc_id # Use assigned doc_id if available
        if doc_id_for_error:
             logger.info(f"Attempting to update status to Failed for doc_id {doc_id_for_error}")
             with _connect() as conn:
                 try:
                     _update_status(conn, doc_id_for_error, "Failed", error_msg)
                     conn.commit()
                     logger.info(f"Successfully updated status to Failed for doc_id {doc_id_for_error}")
                 except Exception as db_exc:
                      conn.rollback()
                      logger.error(f"Failed to update status to Failed for doc_id {doc_id_for_error}: {db_exc}")
        else:
             # This case might happen if the blob fetch failed AND there was no existing record
             logger.warning("Could not determine doc_id to update status to Failed. No DB record was found or inserted.")

        # Re-raise as HTTPException for Cloud Functions/Run or other handlers
        raise HTTPException(status_code=500, detail=error_msg) from exc
    finally:
        # Cleanup temp directory
        try:
            logger.debug(f"Cleaning up temporary directory: {temp_dir}")
            for p in temp_dir.iterdir():
                p.unlink(missing_ok=True) # Don't error if file already gone
            temp_dir.rmdir()
            logger.debug(f"Successfully cleaned up {temp_dir}")
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


# Pydantic models for URL processing
class UrlProcessRequest(BaseModel):
    urls: List[str]
    description: str = ""

@app.post("/process-urls")
async def process_urls(request: UrlProcessRequest):
    """
    Process a list of URLs for both RAG and 3D visualization.
    This endpoint handles web scraping, embedding generation, and 3D coordinate calculation.
    """
    logger.info(f"Processing {len(request.urls)} URLs: {request.urls}")
    
    try:
        # Initialize the web document processor
        processor = WebDocumentProcessor()
        
        # Process all URLs
        result = processor.process_urls(request.urls)
        
        logger.info(f"URL processing completed. Processed: {len(result['processed'])}, Failed: {len(result['failed'])}")
        
        return {
            "status": "completed",
            "processed_count": len(result['processed']),
            "failed_count": len(result['failed']),
            "total_chunks": result['total_chunks'],
            "details": result
        }
        
    except Exception as e:
        logger.error(f"Error processing URLs: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process URLs: {str(e)}"
        )

if __name__ == "__main__":
    # Add PyMuPDF license check/acknowledgement if required by your usage context
    try:
        fitz.TOOLS.mupdf_display_errors(False) # Optionally suppress MuPDF errors/warnings to stdout
        # You might need to agree to AGPL or obtain a commercial license depending on use case.
        # fitz.TOOLS.set_small_glyph_heights(True) # Example configuration
        logger.info(f"PyMuPDF library version {fitz.__doc__}")
    except Exception as fitz_init_err:
        logger.warning(f"Could not configure PyMuPDF: {fitz_init_err}")

    uvicorn.run(app, host="0.0.0.0", port=8080)
