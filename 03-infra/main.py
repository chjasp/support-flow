# main.py

from fastapi import FastAPI, HTTPException, Body, BackgroundTasks, status, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from google.cloud import firestore, storage
import os
import uuid
import re
from typing import List, Dict, Any
import datetime
from dotenv import load_dotenv # Import load_dotenv
import base64 # Added for decoding Pub/Sub message
import json   # Added for parsing decoded message
import uvicorn
from google.cloud.firestore_v1.base_document import DocumentSnapshot
from google.api_core.exceptions import NotFound
from google.cloud.firestore_v1.collection import CollectionReference
import logging # Add this import

# Load environment variables from .env file
load_dotenv()

# --- Basic Logging Configuration ---
# Add this block to configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:     %(message)s')
# --- End Logging Configuration ---

# --- Configuration ---
# Now os.environ.get will first look for variables loaded from .env
PROJECT_ID = os.environ.get("GCP_PROJECT")
LOCATION = os.environ.get("GCP_LOCATION") # Add default if not in .env
MODEL_NAME_EXTRACTION = os.environ.get("MODEL_NAME_EXTRACTION")
MODEL_NAME_SUMMARIZATION = os.environ.get("MODEL_NAME_SUMMARIZATION")
MODEL_NAME_GENERATION = os.environ.get("MODEL_NAME_GENERATION")
MAX_SUMMARY_TOKENS = int(os.environ.get("MAX_SUMMARY_TOKENS", 100)) # Convert to int
MAX_CHUNKS_FOR_CONTEXT = int(os.environ.get("MAX_CHUNKS_FOR_CONTEXT", 5)) # Convert to int

# --- Initialization ---
try:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    db = firestore.Client(project=PROJECT_ID)
    model_extraction = GenerativeModel(MODEL_NAME_EXTRACTION)
    model_summarization = GenerativeModel(MODEL_NAME_SUMMARIZATION,
                                        generation_config=GenerationConfig(max_output_tokens=MAX_SUMMARY_TOKENS))
    model_generation = GenerativeModel(MODEL_NAME_GENERATION)
    logging.info("Vertex AI and Firestore initialized successfully.")
except Exception as e:
    logging.info(f"Error initializing GCP services: {e}")
    # Handle initialization failure appropriately
    # You might want the app to fail startup if these don't initialize
    db = None
    model_extraction = None
    model_summarization = None
    model_generation = None


app = FastAPI(
    title="Knowledge Base API",
    description="API for managing and querying knowledge base documents.",
    version="0.1.0"
)

# --- CORS Configuration ---
# Define allowed origins (replace with your frontend URL in production)
origins = [
    "http://localhost:3000", # Your Next.js frontend development URL
    # Add your deployed frontend URL here if applicable
    # e.g., "https://your-frontend-app-url.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # List of allowed origins
    allow_credentials=True, # Allow cookies/authorization headers
    allow_methods=["*"],    # Allow all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],    # Allow all headers
)
# --- End CORS Configuration ---


# --- Pydantic Models ---
class ProcessFileRequest(BaseModel):
    gcs_uri: str = Field(..., description="GCS URI of the file (gs://bucket_name/file_name)")
    original_filename: str = Field(..., description="Original name of the uploaded file")

class ChunkData(BaseModel):
    chunk_id: str
    doc_id: str
    chunk_text: str
    summary: str
    chunk_order: int

class QueryRequest(BaseModel):
    query: str = Field(..., description="User's question")
    # Optional: Add doc_id if user should query specific docs
    # doc_id: Optional[str] = Field(None, description="Optional document ID to search within")

class QueryResponse(BaseModel):
    answer: str
    retrieved_chunks: List[ChunkData] # Return the chunks used for context

class DocumentListItem(BaseModel):
    id: str
    name: str # Use 'name' for consistency (will be title for text)
    type: str # Will be 'Document' or 'Pasted Text'
    fileType: str | None = None # Extract from name if possible for 'Document'
    dateAdded: str # Format as YYYY-MM-DD string
    status: str # e.g., 'Processing', 'Ready', 'Error'
    gcsUri: str | None = None # Optional

# --- Models for Pub/Sub Eventarc Trigger ---
class PubSubMessage(BaseModel):
    data: str # Base64-encoded data
    messageId: str | None = None
    publishTime: str | None = None
    attributes: Dict[str, str] | None = None # Include attributes if needed

class PubSubRequest(BaseModel):
    message: PubSubMessage
    subscription: str | None = None # Subscription name

class GcsEventData(BaseModel):
    """Structure within the decoded Pub/Sub message data for GCS events"""
    bucket: str
    name: str # File path within the bucket
    # Add other fields if needed, e.g., contentType, timeCreated, updated


# --- Helper Functions ---

def chunk_text(text: str, chunk_size: int = 10000, overlap: int = 500) -> List[str]:
    """
    Chunks text, attempting to split on whitespace near the chunk_size limit
    to avoid cutting words.
    """
    chunks = []
    start = 0
    text_len = len(text)

    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")

    while start < text_len:
        # Calculate the ideal end point
        ideal_end = start + chunk_size

        # If the ideal end is past the text length, take the rest
        if ideal_end >= text_len:
            actual_end = text_len
        else:
            # Find the last whitespace before the ideal end point
            # Search back from ideal_end up to a reasonable limit (e.g., start + overlap)
            # to avoid searching too far back if there's no whitespace.
            search_start = max(start, ideal_end - chunk_size // 2) # Don't search back too far
            last_space = text.rfind(' ', search_start, ideal_end)
            last_newline = text.rfind('\n', search_start, ideal_end)
            split_pos = max(last_space, last_newline)

            # If we found a whitespace, split there. Otherwise, split at ideal_end.
            if split_pos > start: # Ensure we found a space *after* the current start
                actual_end = split_pos + 1 # Split *after* the whitespace
            else:
                # Fallback: No suitable whitespace found, split at the ideal point
                actual_end = ideal_end

        # Extract the chunk
        chunk = text[start:actual_end]
        # Only add non-empty chunks
        if chunk.strip(): # Check if chunk is not just whitespace
             chunks.append(chunk)

        # Calculate the next start position based on the *ideal* chunk size and overlap
        # This ensures overlap is consistent even if the actual chunk was shorter.
        next_start = start + chunk_size - overlap

        # If we split at whitespace and the actual chunk was much shorter,
        # ensure the next start doesn't skip too much. It should be at least
        # after the current actual_end, but ideally respects the overlap.
        # However, the standard overlap calculation usually works well enough.
        # If the fallback split occurred (actual_end == ideal_end), next_start is correct.
        # If a whitespace split occurred (actual_end < ideal_end), next_start
        # might be slightly further than 'overlap' chars from actual_end, which is fine.
        start = next_start

        # Safety break for potential infinite loops (e.g., if overlap calculation is wrong)
        if start >= text_len or actual_end == start:
             break # Exit if start doesn't advance or goes past the end

    return chunks

async def extract_text_from_pdf_gemini(gcs_uri: str) -> str:
    """Extracts text content from a PDF using Gemini."""
    if not model_extraction:
        raise HTTPException(status_code=500, detail="Extraction model not initialized")
    try:
        pdf_part = Part.from_uri(uri=gcs_uri, mime_type="application/pdf")
        prompt = "Extract all text content from this PDF document, preserving paragraphs and structure as much as possible. Output only the raw text content."
        contents = [pdf_part, prompt]
        response = await model_extraction.generate_content_async(contents)
        return response.text
    except Exception as e:
        logging.info(f"Error extracting text from {gcs_uri} with Gemini: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to extract text from PDF: {e}")

async def summarize_chunk(chunk_text: str) -> str:
    """Summarizes a text chunk using Gemini."""
    if not model_summarization:
        raise HTTPException(status_code=500, detail="Summarization model not initialized")
    try:
        prompt = f"Summarize the key information in the following text chunk in about 10 sentences. Focus on the main topics and entities:\n\n{chunk_text}"
        response = await model_summarization.generate_content_async(prompt)
        # Add basic error handling/checking for blocked content if needed
        if response.candidates and response.candidates[0].content.parts:
             return response.text.strip()
        else:
             logging.info(f"Warning: Summarization produced no content for chunk: {chunk_text[:100]}...")
             return "Summary could not be generated." # Placeholder for failed summaries
    except Exception as e:
        logging.info(f"Error summarizing chunk with Gemini: {e}")
        # Decide how to handle summarization errors - return empty string, specific error message?
        return "Error during summarization." # Or return ""

def store_chunks_in_firestore(doc_id: str, source_name: str, document_type: str, chunks_with_summaries: List[Dict[str, Any]], gcs_uri: str | None = None, initial_status: str = "Processing"):
    """
    Stores document metadata in 'documents' collection and chunk data
    in a 'chunks' subcollection under the corresponding document.
    Handles both PDF uploads (with gcs_uri) and pasted text (without gcs_uri).
    """
    if not db:
        raise HTTPException(status_code=500, detail="Firestore not initialized")
    try:
        # Prepare document metadata
        doc_data = {
            "source_name": source_name, # Use a generic name field
            "document_type": document_type, # Store 'PDF' or 'TEXT'
            "timestamp": firestore.SERVER_TIMESTAMP,
            "chunk_count": len(chunks_with_summaries),
            "status": initial_status
        }
        if gcs_uri: # Only add gcs_uri if it exists
            doc_data["gcs_uri"] = gcs_uri

        # Store document metadata (or update if exists)
        doc_ref = db.collection("documents").document(doc_id)
        doc_ref.set(doc_data, merge=True) # Use merge=True

        # Store each chunk in the 'chunks' subcollection if summaries are provided
        if chunks_with_summaries:
            batch = db.batch()
            chunks_subcollection_ref = doc_ref.collection("chunks")
            for item in chunks_with_summaries:
                chunk_doc_ref = chunks_subcollection_ref.document(f"chunk_{item['chunk_order']}")
                chunk_data_to_store = {
                    "chunk_text": item["chunk_text"],
                    "summary": item["summary"],
                    "chunk_order": item["chunk_order"]
                }
                batch.set(chunk_doc_ref, chunk_data_to_store)

            batch.commit()
            logging.info(f"Stored {len(chunks_with_summaries)} chunks in subcollection for doc_id: {doc_id}")

            # Update status to 'Ready' after successful chunk storage
            doc_ref.update({"status": "Ready"})
            logging.info(f"Updated status to 'Ready' for doc_id: {doc_id}")
        # If there were no chunks (e.g., empty text), mark as Ready immediately
        elif not chunks_with_summaries:
             doc_ref.update({"status": "Ready", "chunk_count": 0})
             logging.info(f"Marked doc_id {doc_id} as 'Ready' (no chunks).")


    except Exception as e:
        logging.info(f"Error storing data in Firestore for doc_id {doc_id}: {e}")
        # Attempt to update status to 'Error' if storing fails
        try:
            doc_ref = db.collection("documents").document(doc_id) # Ensure doc_ref is defined
            doc_ref.update({"status": "Error"})
        except Exception as update_e:
             logging.info(f"Failed to update status to 'Error' for doc_id {doc_id}: {update_e}")
        raise HTTPException(status_code=500, detail=f"Failed to store data in Firestore: {e}")

def search_summaries_keyword(query: str) -> List[Dict[str, Any]]:
    """
    Performs a basic keyword search across all chunk summaries in Firestore
    using a Collection Group query on the 'chunks' subcollections.
    WARNING: This is INEFFICIENT for large datasets as it fetches ALL chunks
             from ALL documents. Consider a dedicated search solution for production.
    """
    if not db:
        raise HTTPException(status_code=500, detail="Firestore not initialized")

    try:
        # Basic keyword extraction (same as before)
        stopwords = set(["a", "an", "the", "is", "in", "it", "of", "for", "on", "with"])
        keywords = [word for word in re.findall(r'\b\w+\b', query.lower()) if word not in stopwords]

        if not keywords:
            return [] # No keywords to search

        relevant_chunks = []
        # Use collection_group to query across all 'chunks' subcollections
        # NOTE: This might require creating a Collection Group index in Firestore.
        # Check your backend logs for a link if you get permission errors on first run.
        chunks_stream = db.collection_group("chunks").stream()

        for chunk_doc in chunks_stream:
            chunk_data = chunk_doc.to_dict()
            summary_lower = chunk_data.get("summary", "").lower()
            chunk_text_lower = chunk_data.get("chunk_text", "").lower()

            # Score based on keyword presence (same as before)
            score = 0
            matched_keywords = set()
            for keyword in keywords:
                if keyword in summary_lower:
                    score += 2
                    matched_keywords.add(keyword)
                elif keyword in chunk_text_lower:
                     score += 1
                     matched_keywords.add(keyword)

            if score > 0:
                # --- Get the parent document ID (doc_id) ---
                # The parent of a chunk document in the subcollection is the document reference
                parent_doc_ref = chunk_doc.reference.parent.parent
                if not parent_doc_ref:
                     logging.info(f"Warning: Could not get parent document for chunk {chunk_doc.id}")
                     continue # Skip this chunk if we can't identify its parent document
                doc_id = parent_doc_ref.id
                # ---

                chunk_data_with_score = {
                    **chunk_data,
                    "score": score,
                    "matched_keywords": list(matched_keywords),
                    # Add doc_id and a unique chunk_id for the response model
                    "doc_id": doc_id,
                    "chunk_id": f"{doc_id}_{chunk_doc.id}" # Reconstruct a unique ID for response if needed
                }
                relevant_chunks.append(chunk_data_with_score)


        # Sort by score (descending)
        relevant_chunks.sort(key=lambda x: x["score"], reverse=True)

        # Limit results (implement MAX_CHUNKS_FOR_CONTEXT)
        return relevant_chunks[:MAX_CHUNKS_FOR_CONTEXT]

    except Exception as e:
        logging.info(f"Error searching summaries in Firestore: {e}")
        # Check if the error is related to needing an index
        if "requires an index" in str(e):
             logging.info(">>> Firestore Index Required <<<")
             logging.info("Please check the backend logs for a URL to create the necessary Firestore index for the collection group query.")
             raise HTTPException(status_code=500, detail=f"Firestore index required for collection group query. Check backend logs. Original error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search summaries: {e}")


async def generate_answer(query: str, context_chunks: List[Dict[str, Any]]) -> str:
    """Generates an answer using Gemini based on the query and context."""
    if not model_generation:
        raise HTTPException(status_code=500, detail="Generation model not initialized")

    context_str = "No relevant context found."
    prompt_template = "" # Initialize prompt template variable

    if not context_chunks:
        logging.info("Warning: No relevant chunks found. Attempting to answer query without context.")
        # If no context, directly ask the model using its general knowledge
        prompt_template = f"""Answer the following user question using your general knowledge.

    Format your answer using Markdown.
    - Use headings (#, ##), bullet points (- or *), or numbered lists (1., 2.) where appropriate to structure the information clearly (e.g., for steps, key points, or lists).
    - Use bold text (**text**) for emphasis where needed.
    - Ensure distinct paragraphs are separated by double newlines (\n\n).
    - If the answer involves steps or a list like in the user's example, please use appropriate Markdown list formatting.

    User Question: {query}

    Answer (in Markdown):
    """
    else:
        # Format context if chunks were found
        context_str = "\n---\n".join([chunk.get("chunk_text", "") for chunk in context_chunks])
        # --- Revised Prompt with Formatting Instructions ---
        prompt_template = f"""Answer the user's question based *primarily* on the provided context below.
    If the context does not provide a sufficient answer, use your general knowledge to supplement, but clearly indicate if the answer goes beyond the provided context.
    Do not mention the context source explicitly (e.g., "Based on the context...") unless it's crucial for clarification.

    Format your answer using Markdown.
    - Use headings (#, ##), bullet points (- or *), or numbered lists (1., 2.) where appropriate to structure the information clearly (e.g., for steps, key points, or lists).
    - Use bold text (**text**) for emphasis where needed (like the bolded list items in the user's example image).
    - Ensure distinct paragraphs are separated by double newlines (\n\n).
    - Structure the response logically, potentially with an introduction, main points (possibly as a list), and a conclusion if appropriate for the query.

    Context:
    ---
    {context_str}
    ---

    User Question: {query}

    Answer (in Markdown):
    """
        # --- End Revised Prompt ---

    try:
        # Use the selected prompt template
        response = await model_generation.generate_content_async(prompt_template)
        # Add basic error handling/checking for blocked content if needed
        if response.candidates and response.candidates[0].content.parts:
            # The response text should now contain Markdown
            return response.text
        else:
            logging.info(f"Warning: Answer generation produced no content for query: {query}")
            return "An error occurred while generating the answer, or the response was empty/blocked."

    except Exception as e:
        logging.info(f"Error generating answer with Gemini: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate answer: {e}")


# --- Core Processing Logic ---

async def process_uploaded_pdf(doc_id: str, gcs_uri: str, original_filename: str):
    """
    Core logic to process a PDF from GCS: extract, chunk, summarize, store.
    Chunks are stored in a subcollection under the document.
    Updates document status in Firestore.
    """
    if not db or not model_extraction or not model_summarization:
        logging.info("Error: Backend services not fully initialized.")
        try:
            doc_ref = db.collection("documents").document(doc_id)
            # Use source_name consistently
            doc_ref.set({"status": "Error", "source_name": original_filename, "gcs_uri": gcs_uri, "document_type": "PDF"}, merge=True)
        except Exception as e:
            logging.info(f"Failed to mark doc {doc_id} as Error during service init failure: {e}")
        raise RuntimeError("Backend services not fully initialized.")

    logging.info(f"Starting processing for doc_id: {doc_id}, GCS URI: {gcs_uri}")
    doc_ref = db.collection("documents").document(doc_id)

    try:
        # 0. Set initial status in Firestore
        logging.info(f"Setting initial status 'Processing' for doc_id: {doc_id}")
        doc_ref.set({
            "source_name": original_filename, # Use source_name
            "document_type": "PDF", # Specify type
            "gcs_uri": gcs_uri,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "status": "Processing"
        }, merge=True)

        # 1. Extract Text
        logging.info(f"Extracting text from {gcs_uri}...")
        full_text = await extract_text_from_pdf_gemini(gcs_uri)
        if not full_text:
            raise ValueError("Could not extract text from PDF.") # Use ValueError or custom exception
        logging.info(f"Extracted text length: {len(full_text)} characters for doc_id: {doc_id}.")

        # 2. Chunk Text
        logging.info(f"Chunking text for doc_id: {doc_id}...")
        text_chunks = chunk_text(full_text) # Use your preferred chunking strategy
        logging.info(f"Created {len(text_chunks)} chunks for doc_id: {doc_id}.")

        # 3. Summarize Chunks and Prepare for Firestore
        chunks_to_store = []
        logging.info(f"Summarizing chunks for doc_id: {doc_id}...")
        for i, chunk in enumerate(text_chunks):
            summary = await summarize_chunk(chunk)
            chunks_to_store.append({
                "chunk_text": chunk,
                "summary": summary,
                "chunk_order": i
            })
            if (i + 1) % 10 == 0: # Log progress periodically
                 logging.info(f"  Summarized chunk {i+1}/{len(text_chunks)} for doc_id: {doc_id}")

        # 4. Store in Firestore (uses the updated store_chunks_in_firestore)
        logging.info(f"Storing {len(chunks_to_store)} chunks in Firestore subcollection for doc_id: {doc_id}...")
        # Pass 'PDF' as document_type, original_filename as source_name, and the gcs_uri
        store_chunks_in_firestore(doc_id, original_filename, "PDF", chunks_to_store, gcs_uri=gcs_uri, initial_status="Processing")

        logging.info(f"Successfully processed and stored document: {doc_id}")

    except Exception as e:
        logging.info(f"Error during PDF processing for doc_id {doc_id} ({gcs_uri}): {e}")
        # Update status to 'Error' in Firestore
        try:
            doc_ref.update({"status": "Error"})
            logging.info(f"Updated status to 'Error' for doc_id: {doc_id}")
        except Exception as update_e:
            logging.info(f"Failed to update status to 'Error' for doc_id {doc_id} after processing error: {update_e}")
        # Re-raise the exception so the caller (HTTP endpoint or GCS handler) knows it failed
        raise e


# --- API Endpoints ---

@app.post("/process-file", status_code=status.HTTP_202_ACCEPTED)
async def process_file_endpoint(request: ProcessFileRequest, background_tasks: BackgroundTasks):
    """
    HTTP Endpoint to manually trigger the processing of a file stored in GCS.
    Determines file type from GCS URI and adds the appropriate processing task
    to the background. Generates a doc_id.
    """
    logging.info(f"Received HTTP request to process GCS URI: {request.gcs_uri}")
    doc_id = str(uuid.uuid4()) # Generate a unique ID for this document

    try:
        # Determine file type from GCS URI
        file_name = request.gcs_uri.lower() # Use lowercase for extension check
        original_filename = request.original_filename # Keep original case for storage

        if file_name.endswith('.pdf'):
            logging.info(f"Detected PDF. Adding PDF processing task to background for doc_id: {doc_id}")
            background_tasks.add_task(process_uploaded_pdf, doc_id, request.gcs_uri, original_filename)
        elif file_name.endswith('.txt'):
            logging.info(f"Detected TXT. Adding Text processing task to background for doc_id: {doc_id}")
            background_tasks.add_task(process_uploaded_text, doc_id, request.gcs_uri, original_filename)
        # Add elif for other supported types here if needed
        # elif file_name.endswith('.docx'):
        #     background_tasks.add_task(process_uploaded_docx, doc_id, request.gcs_uri, original_filename)
        else:
            # Handle unsupported file types for manual trigger
            logging.info(f"Unsupported file type for manual processing: {request.gcs_uri}")
            # Optionally create an 'Error' document entry immediately
            if db:
                try:
                    db.collection("documents").document(doc_id).set({
                        "status": "Error",
                        "source_name": original_filename,
                        "gcs_uri": request.gcs_uri,
                        "timestamp": firestore.SERVER_TIMESTAMP,
                        "error_message": f"Unsupported file type for manual trigger: {os.path.splitext(original_filename)[1]}",
                        "document_type": "UNSUPPORTED"
                    }, merge=True)
                except Exception as db_e:
                    logging.info(f"Failed to mark unsupported file {doc_id} as Error in Firestore: {db_e}")
            # Raise HTTPException to inform the client
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type for manual processing: {os.path.splitext(original_filename)[1] or 'Unknown'}. Supported types: .pdf, .txt"
            )

        # Immediately return 202 if a task was added
        return {"message": "File processing accepted.", "doc_id": doc_id}

    except HTTPException as http_exc:
         # Re-raise HTTP exceptions (like the 400 for unsupported type)
         raise http_exc
    except Exception as e:
        # This catch block handles errors during task *submission* or initial checks
        logging.info(f"Error initiating file processing for {request.gcs_uri} via HTTP: {e}")
        # Attempt to mark as error if we know the doc_id (though task might not have started)
        if doc_id and db:
             try:
                 db.collection("documents").document(doc_id).set({
                     "status": "Error",
                     "source_name": request.original_filename,
                     "gcs_uri": request.gcs_uri,
                     "timestamp": firestore.SERVER_TIMESTAMP,
                     "error_message": f"Failed to initiate processing: {e}"
                 }, merge=True)
             except Exception as update_e:
                 logging.info(f"Failed to mark doc {doc_id} as Error during HTTP initiation failure: {update_e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to initiate file processing: {e}")


# --- New Helper Function for Parsing LLM Ranking ---
def parse_llm_ranking(response_text: str, index_to_chunk_map: Dict[int, Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Parses the LLM response to extract ranked chunk IDs and scores.

    Args:
        response_text: The raw text output from the LLM.
        index_to_chunk_map: A dictionary mapping the prompt index (1-based) to chunk info ({'doc_id': ..., 'chunk_id': ...}).

    Returns:
        A list of dictionaries, each containing 'doc_id', 'chunk_id', and 'score',
        sorted by score descending. Returns empty list if parsing fails.
    """
    ranked_chunks = []
    # Regex to find lines like "Doc: 9, Relevance: 7" or "Chunk: 9, Relevance: 7"
    # Allows for variations in spacing and capitalization. Handles scores 1-10.
    pattern = re.compile(r"^\s*(?:Doc|Chunk):\s*(\d+)\s*,\s*Relevance:\s*([1-9]|10)\s*$", re.IGNORECASE | re.MULTILINE)

    try:
        matches = pattern.findall(response_text)
        logging.info(f"LLM Ranking - Found matches: {matches}")

        for match in matches:
            prompt_index = int(match[0])
            score = int(match[1])

            if prompt_index in index_to_chunk_map:
                chunk_info = index_to_chunk_map[prompt_index]
                ranked_chunks.append({
                    "doc_id": chunk_info["doc_id"],
                    "chunk_id": chunk_info["chunk_id"],
                    "score": score
                })
            else:
                logging.warning(f"LLM Ranking - Parsed index {prompt_index} not found in map.")

        # Sort by score descending
        ranked_chunks.sort(key=lambda x: x["score"], reverse=True)
        logging.info(f"LLM Ranking - Successfully parsed and sorted {len(ranked_chunks)} chunks.")

    except Exception as e:
        logging.error(f"LLM Ranking - Error parsing response: {e}\nResponse was:\n{response_text}")
        return [] # Return empty on error

    return ranked_chunks


# --- Modified Keyword Search Function ---
def search_chunks_keyword(query: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """
    Performs a basic keyword search across all chunk_text in Firestore
    using a Collection Group query on the 'chunks' subcollections.
    Returns a list of chunks with keyword scores.
    """
    if not db:
        logging.error("Firestore not initialized for keyword search.")
        # Return empty list instead of raising HTTPException here,
        # as the calling function might handle it.
        return []

    logging.info(f"Starting keyword search on chunk_text for query: '{query}'")
    try:
        # Basic keyword extraction
        stopwords = set(["a", "an", "the", "is", "in", "it", "of", "for", "on", "with"])
        keywords = [word for word in re.findall(r'\b\w+\b', query.lower()) if word not in stopwords]

        if not keywords:
            logging.info("No keywords extracted from query for keyword search.")
            return []

        relevant_chunks = []
        # Use collection_group to query across all 'chunks' subcollections
        # Ensure the necessary Firestore index exists!
        chunks_stream = db.collection_group("chunks").stream() # Consider adding .where("status", "==", "Ready") on parent? No, query parent docs first.

        # --- Optimization: Query only chunks from 'Ready' documents ---
        ready_doc_ids = set()
        docs_ref = db.collection("documents").where("status", "==", "Ready").select([]) # Select no fields, just get IDs
        ready_docs_stream = docs_ref.stream()
        for doc in ready_docs_stream:
            ready_doc_ids.add(doc.id)

        if not ready_doc_ids:
            logging.info("No 'Ready' documents found for keyword search.")
            return []
        logging.info(f"Keyword search will target chunks from {len(ready_doc_ids)} 'Ready' documents.")
        # --- End Optimization ---


        chunk_count = 0
        for chunk_doc in chunks_stream:
            # --- Get parent doc_id and check if it's 'Ready' ---
            parent_doc_ref = chunk_doc.reference.parent.parent
            if not parent_doc_ref:
                 logging.warning(f"Keyword Search: Could not get parent document for chunk {chunk_doc.id}")
                 continue
            doc_id = parent_doc_ref.id
            if doc_id not in ready_doc_ids:
                continue # Skip chunks from documents not in 'Ready' state
            # --- End Parent Check ---

            chunk_count += 1
            chunk_data = chunk_doc.to_dict()
            chunk_text_lower = chunk_data.get("chunk_text", "").lower()
            chunk_id = chunk_doc.id # Get the chunk ID

            # Score based on keyword presence in chunk_text
            score = 0
            matched_keywords = set()
            for keyword in keywords:
                # Simple presence check, could be enhanced with frequency (TF-IDF) later
                if keyword in chunk_text_lower:
                     score += 1 # Increment score for each keyword found
                     matched_keywords.add(keyword)

            if score > 0:
                relevant_chunks.append({
                    "doc_id": doc_id,
                    "chunk_id": chunk_id,
                    "keyword_score": score,
                    "matched_keywords": list(matched_keywords) # Optional: for debugging/info
                })

        logging.info(f"Keyword search scanned {chunk_count} chunks from ready documents, found {len(relevant_chunks)} potential matches.")

        # Sort by score (descending)
        relevant_chunks.sort(key=lambda x: x["keyword_score"], reverse=True)

        # Limit results
        return relevant_chunks[:max_results]

    except Exception as e:
        logging.exception(f"Error during keyword search on chunk_text: {e}")
        # Check if the error is related to needing an index
        if "requires an index" in str(e):
             logging.error(">>> Firestore Index Required <<<")
             logging.error("Please check the backend logs for a URL to create the necessary Firestore index for the collection group query.")
        # Return empty list on error to allow fusion logic to proceed if possible
        return []


# --- New Reciprocal Rank Fusion (RRF) Function ---
def combine_rankings_rrf(list1: List[Dict[str, Any]], list2: List[Dict[str, Any]], k: int = 60, score_key1: str = 'keyword_score', score_key2: str = 'llm_score') -> List[Dict[str, Any]]:
    """
    Combines two ranked lists using Reciprocal Rank Fusion (RRF).

    Args:
        list1: First ranked list of dicts, each with 'doc_id', 'chunk_id'.
        list2: Second ranked list of dicts, each with 'doc_id', 'chunk_id'.
        k: RRF constant (default 60).
        score_key1: Key for score in list1 (used for sorting if ranks aren't explicit).
        score_key2: Key for score in list2 (used for sorting if ranks aren't explicit).

    Returns:
        A single list of dicts, sorted by RRF score (descending),
        each containing 'doc_id', 'chunk_id', and 'rrf_score'.
    """
    logging.info(f"Combining {len(list1)} keyword results and {len(list2)} LLM results using RRF (k={k}).")
    # Ensure lists are sorted (higher score = better rank)
    list1.sort(key=lambda x: x.get(score_key1, 0), reverse=True)
    list2.sort(key=lambda x: x.get(score_key2, 0), reverse=True)

    # Create rank maps (chunk_tuple -> rank)
    rank_map1 = {(item['doc_id'], item['chunk_id']): i + 1 for i, item in enumerate(list1)}
    rank_map2 = {(item['doc_id'], item['chunk_id']): i + 1 for i, item in enumerate(list2)}

    # Get all unique chunks
    all_chunks = set(rank_map1.keys()) | set(rank_map2.keys())

    # Calculate RRF scores
    fused_results = []
    for chunk_tuple in all_chunks:
        doc_id, chunk_id = chunk_tuple
        rank1 = rank_map1.get(chunk_tuple)
        rank2 = rank_map2.get(chunk_tuple)

        rrf_score = 0.0
        if rank1:
            rrf_score += 1.0 / (k + rank1)
        if rank2:
            rrf_score += 1.0 / (k + rank2)

        if rrf_score > 0: # Only include chunks that appeared in at least one list
            fused_results.append({
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "rrf_score": rrf_score
            })

    # Sort by RRF score (descending)
    fused_results.sort(key=lambda x: x["rrf_score"], reverse=True)

    logging.info(f"RRF resulted in {len(fused_results)} unique ranked chunks.")
    return fused_results


# --- Modify LLM Ranking Function to return scores ---
async def find_relevant_chunks_llm_ranked(query: str, max_chunks_to_rank: int = 50) -> List[Dict[str, Any]]: # Limit how many summaries we rank
    """
    Finds relevant chunks using LLM ranking based on summaries.
    1. Fetches chunk summaries from 'Ready' documents.
    2. Asks LLM to rank summaries based on the query.
    3. Parses LLM response and returns ranked list with scores.
    """
    if not db or not model_generation:
        logging.error("Firestore or Generation model not initialized for LLM ranking.")
        return []

    logging.info(f"Starting LLM-ranked chunk retrieval for query: '{query}'")
    all_summaries_data = []
    index_to_chunk_map: Dict[int, Dict[str, str]] = {}
    prompt_index_counter = 1

    try:
        # 1. Fetch summaries from ready documents (Limit the number fetched initially if needed)
        docs_ref = db.collection("documents").where("status", "==", "Ready")
        docs_stream = docs_ref.stream()

        logging.info("Fetching summaries from 'Ready' documents for LLM ranking...")
        doc_count = 0
        chunk_summary_count = 0
        summaries_for_prompt = []

        # --- Fetch summaries efficiently ---
        # We might hit limits if we try to rank *all* summaries.
        # Let's fetch documents and then their chunks.
        ready_docs = list(docs_stream) # Get all ready docs first
        doc_count = len(ready_docs)
        logging.info(f"Found {doc_count} 'Ready' documents.")

        for doc in ready_docs:
            doc_id = doc.id
            # Fetch only summary and order? Firestore doesn't make selecting subcollection fields easy.
            # Fetch chunk docs, limit if necessary?
            chunks_ref = doc.reference.collection("chunks").order_by("chunk_order") # Keep order
            chunks_stream = chunks_ref.stream()

            for chunk_doc in chunks_stream:
                if chunk_summary_count >= max_chunks_to_rank: # Stop collecting summaries if we hit the limit
                    break

                chunk_data = chunk_doc.to_dict()
                if chunk_data and "summary" in chunk_data:
                    summary_text = chunk_data["summary"]
                    chunk_id = chunk_doc.id

                    # Add to list for prompt generation and create mapping
                    summary_info = {
                        "prompt_index": prompt_index_counter,
                        "doc_id": doc_id,
                        "chunk_id": chunk_id,
                        "summary": summary_text
                    }
                    summaries_for_prompt.append(summary_info)
                    index_to_chunk_map[prompt_index_counter] = {"doc_id": doc_id, "chunk_id": chunk_id}
                    prompt_index_counter += 1
                    chunk_summary_count += 1
            if chunk_summary_count >= max_chunks_to_rank:
                 logging.info(f"Reached summary limit ({max_chunks_to_rank}) for LLM ranking prompt.")
                 break # Stop processing more documents if limit reached

        logging.info(f"Collected {chunk_summary_count} summaries from {doc_count} documents for LLM ranking.")

        if not summaries_for_prompt:
            logging.info("No summaries found in 'Ready' documents. Cannot perform LLM ranking.")
            return []

        # 2. Prepare prompt for LLM Ranking
        context_parts = []
        for summary_info in summaries_for_prompt:
            context_parts.append(f"Chunk {summary_info['prompt_index']}:\n{summary_info['summary']}")

        context_str = "\n\n".join(context_parts)

        # --- Updated Ranking Prompt ---
        # Ask for a score (1-10) and ensure it lists relevant ones.
        ranking_prompt = f"""A list of document chunk summaries is shown below. Each chunk has a number. A question is also provided.

Evaluate the relevance of each chunk summary to the user's question on a scale of 1 to 10 (1 = not relevant, 10 = highly relevant).
Respond ONLY with the numbers of the chunks that are relevant (score > 3) to answering the question.
For each relevant chunk, list its number and relevance score. Use the format "Chunk: <number>, Relevance: <score>" for each relevant chunk, with each on a new line. Order them from most relevant to least relevant.

Example format:
Chunk: 9, Relevance: 8
Chunk: 3, Relevance: 6
Chunk: 7, Relevance: 4

Document Chunk Summaries:
{context_str}

User Question: {query}

Relevant Chunks (Format: Chunk: <number>, Relevance: <score>):
"""
        # --- End Updated Ranking Prompt ---

        logging.info(f"Sending ranking prompt to LLM ({len(summaries_for_prompt)} summaries)...")

        # 3. Call LLM for Ranking
        try:
            response = await model_generation.generate_content_async(ranking_prompt)
            llm_response_text = response.text
            logging.info(f"LLM Ranking Response received:\n{llm_response_text}")
        except Exception as gen_e:
            logging.error(f"Error calling LLM for ranking: {gen_e}")
            return []

        # 4. Parse LLM Response (using existing helper, it extracts score)
        # The parse_llm_ranking function already extracts 'score'
        ranked_chunks = parse_llm_ranking(llm_response_text, index_to_chunk_map)
        # Rename 'score' to 'llm_score' for clarity in fusion
        for chunk in ranked_chunks:
            chunk['llm_score'] = chunk.pop('score')


        if not ranked_chunks:
            logging.warning("LLM ranking parsing returned no chunks.")
            return []

        logging.info(f"LLM Ranking identified {len(ranked_chunks)} relevant chunks.")
        # Return the ranked list with scores, no need to fetch full text here yet.
        return ranked_chunks

    except Exception as e:
        logging.exception(f"Error during LLM-ranked chunk retrieval for query '{query}': {e}")
        return []


# --- New Helper Function: Hybrid Search Logic ---
async def search_summaries_hybrid(query: str, top_n: int = 5) -> List[Dict[str, Any]]:
    """
    Performs hybrid search (keyword + LLM ranking + RRF) and fetches
    full chunk data for the top N results.

    Args:
        query: The user's search query.
        top_n: The maximum number of final chunks to retrieve.

    Returns:
        A list of dictionaries, each containing the full data for a relevant chunk.
        Returns empty list if no relevant chunks are found or an error occurs.
    """
    logging.info(f"Starting hybrid search for query: '{query}' (top_n={top_n})")
    if not db or not model_generation: # Check necessary services
        logging.error("Hybrid search cannot proceed: Firestore or Generation model not initialized.")
        return []

    try:
        # 1. Perform Keyword Search on full text
        logging.info("Hybrid Search Step 1: Performing keyword search...")
        # Limit keyword results more broadly initially, RRF will refine
        keyword_results = search_chunks_keyword(query, max_results=20) # Use existing helper

        # 2. Perform LLM Ranking on summaries
        logging.info("Hybrid Search Step 2: Performing LLM ranking...")
        # Limit summaries sent to LLM
        llm_ranked_results = await find_relevant_chunks_llm_ranked(query, max_chunks_to_rank=50) # Use existing helper

        # 3. Combine rankings using RRF
        logging.info("Hybrid Search Step 3: Combining results using RRF...")
        final_ranked_list = combine_rankings_rrf(keyword_results, llm_ranked_results, k=60) # Use existing helper

        # 4. Select Top N chunk references
        top_chunks_refs = final_ranked_list[:top_n]
        logging.info(f"Hybrid Search Step 4: Selected top {len(top_chunks_refs)} chunk references after RRF.")

        if not top_chunks_refs:
             logging.info("Hybrid Search: No relevant chunks found after RRF.")
             return []

        # 5. Fetch Full Chunk Text for the final selected chunks
        logging.info("Hybrid Search Step 5: Fetching full text for top-ranked chunks...")
        relevant_chunks_data = []
        fetched_chunk_ids = set() # Avoid duplicates

        # Use Firestore batching for potentially better performance if fetching many chunks
        # Note: Firestore batching has limits (e.g., 500 operations per batch)
        # For small top_n (like 5), individual gets are fine.
        # If top_n could be large, consider implementing batching.

        for chunk_ref in top_chunks_refs:
            doc_id = chunk_ref["doc_id"]
            chunk_id = chunk_ref["chunk_id"]
            chunk_key = (doc_id, chunk_id)

            if chunk_key in fetched_chunk_ids:
                continue # Skip if already fetched

            try:
                chunk_doc_ref = db.collection("documents").document(doc_id).collection("chunks").document(chunk_id)
                chunk_snapshot = chunk_doc_ref.get()
                if chunk_snapshot.exists:
                    chunk_data = chunk_snapshot.to_dict()
                    # Add necessary fields for context generation and response model
                    chunk_data["doc_id"] = doc_id
                    chunk_data["chunk_id"] = chunk_id
                    # Optionally add the final score for debugging/display?
                    # chunk_data["final_score"] = chunk_ref["rrf_score"]
                    relevant_chunks_data.append(chunk_data)
                    fetched_chunk_ids.add(chunk_key)
                else:
                    logging.warning(f"Hybrid Search: Could not fetch chunk {chunk_id} from doc {doc_id} (snapshot missing).")
            except Exception as fetch_e:
                logging.error(f"Hybrid Search: Error fetching chunk {chunk_id} from doc {doc_id}: {fetch_e}")

        logging.info(f"Hybrid Search: Successfully fetched {len(relevant_chunks_data)} full chunks.")
        return relevant_chunks_data

    except Exception as e:
        logging.exception(f"Hybrid Search: Unexpected error during hybrid search for query '{query}': {e}")
        return [] # Return empty list on error


# --- Update Query Endpoint ---
@app.post("/chat", response_model=QueryResponse)
async def handle_query(request: QueryRequest):
    """
    Handles user queries using hybrid retrieval (keyword + LLM ranking)
    with Reciprocal Rank Fusion (RRF) and generates an answer.
    """
    logging.info(f"Received chat query: '{request.query}'")
    if not model_generation or not db:
        logging.error("Cannot handle chat query: Backend services (Generation Model/Firestore) not initialized.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backend services are not ready. Please try again later."
        )

    try:
        # --- Hybrid Retrieval Steps ---
        # 1. Perform Hybrid Search
        logging.info("Step 1: Performing hybrid search...")
        relevant_chunks_data = await search_summaries_hybrid(request.query, top_n=MAX_CHUNKS_FOR_CONTEXT)
        logging.info(f"Found {len(relevant_chunks_data)} relevant chunks for query '{request.query}'.")

        # 2. Generate Answer
        logging.info(f"Step 2: Generating answer using {len(relevant_chunks_data)} context chunks...")
        answer = await generate_answer(request.query, relevant_chunks_data)

        # 3. Format response chunks to match the Pydantic model
        response_chunks = []
        for chunk_dict in relevant_chunks_data:
             try:
                 response_chunks.append(ChunkData(
                     chunk_id=chunk_dict.get("chunk_id", "unknown-chunk-id"),
                     doc_id=chunk_dict.get("doc_id", "unknown-doc-id"),
                     chunk_text=chunk_dict.get("chunk_text", ""),
                     summary=chunk_dict.get("summary", ""),
                     chunk_order=chunk_dict.get("chunk_order", -1)
                 ))
             except Exception as pydantic_error:
                 logging.warning(f"Could not format chunk {chunk_dict.get('chunk_id')} for response model: {pydantic_error}")


        logging.info(f"Sending answer for chat query '{request.query}'. Chunks used: {len(response_chunks)}")
        return QueryResponse(answer=answer, retrieved_chunks=response_chunks)

    except HTTPException as http_exc:
         logging.warning(f"HTTPException while handling chat query '{request.query}': {http_exc.status_code} - {http_exc.detail}")
         raise http_exc
    except Exception as e:
        logging.exception(f"Unexpected error handling chat query '{request.query}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred while processing the query."
        )


@app.get("/documents", response_model=list[DocumentListItem])
async def get_documents():
    """
    Retrieves a list of processed documents (PDFs and Text) from Firestore.
    Includes document status.
    """
    
    logging.info("GET /documents endpoint called.") # Add log at entry
    if not db:
        raise HTTPException(status_code=500, detail="Firestore not initialized")

    try:
        docs_ref = db.collection('documents').order_by('timestamp', direction=firestore.Query.DESCENDING).stream()

        documents_list = []
        for doc in docs_ref:
            doc_data = doc.to_dict()
            doc_id = doc.id

            doc_type = doc_data.get('document_type', 'Unknown') # Get the type
            source_name = doc_data.get('source_name', 'Untitled') # Get the source name

            file_type_display = None
            item_type_display = "Unknown"

            if doc_type == "PDF":
                item_type_display = "Document"
                if '.' in source_name:
                    file_type_display = source_name.split('.')[-1].upper()
            elif doc_type == "TEXT":
                item_type_display = "Pasted Text"
                # file_type_display remains None

            # Format timestamp
            timestamp = doc_data.get('timestamp')
            date_added_str = "Unknown"
            if isinstance(timestamp, datetime.datetime):
                 date_added_str = timestamp.strftime('%Y-%m-%d')
            elif isinstance(timestamp, str):
                 try:
                     date_added_str = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                 except ValueError:
                     date_added_str = timestamp

            item = DocumentListItem(
                id=doc_id,
                name=source_name, # Use source_name for display
                type=item_type_display, # Use the determined display type
                fileType=file_type_display, # Use determined file type (or None)
                dateAdded=date_added_str,
                status=doc_data.get('status', 'Unknown'),
                gcsUri=doc_data.get('gcs_uri') # Get GCS URI (will be None for text)
            )
            documents_list.append(item)

        return documents_list
    except Exception as e:
        logging.info(f"Error fetching documents from Firestore: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch documents: {e}")


@app.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_endpoint(doc_id: str):
    """
    Deletes a document and all its associated chunks from Firestore.
    """
    logging.info(f"DELETE /documents/{doc_id} endpoint called.") # Add log at entry

    if not db:
        logging.error("Firestore not initialized during delete request.") # Log errors too
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Firestore not initialized")

    doc_ref = db.collection("documents").document(doc_id)
    chunks_ref = doc_ref.collection("chunks") # Reference to the subcollection

    try:
        # Replace logging.info with logging.info
        logging.info(f"Attempting to get document with ID: '{doc_id}' for deletion.")
        # 1. Check if the document exists
        doc_snapshot: DocumentSnapshot = doc_ref.get()
        if not doc_snapshot.exists:
            # If not found...
            logging.warning(f"Document {doc_id} not found for deletion.") # Use warning level
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document with ID {doc_id} not found")

        # 2. Delete all chunks in the subcollection first
        logging.info(f"Deleting chunks for document: {doc_id}...")
        delete_collection(chunks_ref, batch_size=100) # Adjust batch size as needed
        logging.info(f"Finished deleting chunks for document: {doc_id}")


        # 3. Now delete the main document itself
        logging.info(f"Deleting main document: {doc_id}")
        doc_ref.delete()
        logging.info(f"Successfully deleted document and chunks for ID: {doc_id}")

        # Return 204 No Content (FastAPI handles this based on status_code)
        return

    except NotFound:
         logging.warning(f"Document {doc_id} was not found during deletion process (possibly already deleted).")
         # Return 204 as the desired state (deleted) is achieved
         return
    except HTTPException as http_exc:
        # Re-raise HTTP exceptions (like the 404 above)
        logging.error(f"HTTPException during delete for {doc_id}: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logging.exception(f"Error deleting document {doc_id}: {e}") # Use logging.exception to include traceback
        # Log the error appropriately (consider more detailed logging)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred while deleting document {doc_id}.")

# --- Add this helper function ---
def delete_collection(coll_ref: CollectionReference, batch_size: int):
    """Recursively deletes the documents in a collection or subcollection in batches."""
    docs = coll_ref.limit(batch_size).stream()
    deleted = 0

    for doc in docs:
        # Use logging instead of logging.info for consistency, and fix the path attribute
        logging.info(f"Deleting doc {doc.id} from {coll_ref._path}") # Use _path
        doc.reference.delete()
        deleted = deleted + 1

    # If we deleted a full batch, there might be more documents, so recurse
    if deleted >= batch_size:
        # Use logging and fix the path attribute
        logging.info(f"Deleted batch of {deleted} from {coll_ref._path}, checking for more...") # Use _path
        return delete_collection(coll_ref, batch_size)
    else:
        # Use logging and fix the path attribute
        logging.info(f"Finished deleting all documents from {coll_ref._path}") # Use _path
        return

# --- Eventarc GCS Trigger Endpoint ---

@app.post("/event/gcs", status_code=status.HTTP_200_OK)
async def handle_gcs_event_pubsub(request: PubSubRequest, background_tasks: BackgroundTasks):
    """
    Endpoint to receive GCS change notifications via Pub/Sub messages from Eventarc.
    Decodes the message, extracts file details, determines file type,
    and triggers the appropriate processing task (PDF or Text).
    """
    logging.info(f"Received Pub/Sub message: {request.message.messageId}")

    if not request.message or not request.message.data:
        logging.info("Error: Received empty message or message data.")
        # Return 2xx so Pub/Sub doesn't retry, but log the error.
        # Consider returning 400 if the format is definitively wrong.
        return {"status": "error", "message": "Empty message data received"}

    try:
        # Decode the base64-encoded message data
        decoded_data = base64.b64decode(request.message.data).decode('utf-8')
        logging.info(f"Decoded message data: {decoded_data}")
        event_data_dict = json.loads(decoded_data)
        event_data = GcsEventData(**event_data_dict)

        bucket_name = event_data.bucket
        file_name = event_data.name # This is the object name (e.g., uploads/uuid-filename.pdf)
        gcs_uri = f"gs://{bucket_name}/{file_name}"

        # --- Get original filename (Attempt from metadata first, then fallback) ---
        original_filename = "Unknown Filename" # Default
        try:
            # Initialize storage client if not already done globally or passed in
            storage_client = storage.Client()
            blob = storage_client.bucket(bucket_name).get_blob(file_name)
            if blob and blob.metadata and 'originalfilename' in blob.metadata:
               original_filename = blob.metadata['originalfilename']
               logging.info(f"Retrieved original filename from metadata: {original_filename}")
            else:
               # Fallback extraction from object name
               logging.info(f"Warning: Could not retrieve 'originalfilename' metadata for {file_name}. Falling back to object name parsing.")
               base_name = os.path.basename(file_name)
               parts = base_name.split('-', 1) # Assumes 'uuid-original_filename.ext'
               if len(parts) > 1:
                   original_filename = parts[1]
               else: # If no UUID prefix, use the whole name
                   original_filename = base_name
               logging.info(f"Using fallback original filename: {original_filename}")

        except Exception as meta_e:
             logging.info(f"Error retrieving metadata for {file_name}, using fallback: {meta_e}")
             # Fallback extraction from object name (repeat in case of error)
             base_name = os.path.basename(file_name)
             parts = base_name.split('-', 1)
             if len(parts) > 1:
                 original_filename = parts[1]
             else:
                 original_filename = base_name
             logging.info(f"Using fallback original filename after error: {original_filename}")
        # --- End Original Filename Retrieval ---


        # Generate a unique ID for the document
        doc_id = str(uuid.uuid4())

        logging.info(f"GCS event triggered processing for: {gcs_uri}")
        logging.info(f"Generated document ID: {doc_id}")
        logging.info(f"Using original filename: {original_filename}")

        # --- Determine file type and choose processing function ---
        lower_filename = file_name.lower()
        if lower_filename.endswith('.pdf'):
            logging.info(f"Detected PDF file. Adding PDF processing task for doc_id: {doc_id}")
            background_tasks.add_task(process_uploaded_pdf, doc_id, gcs_uri, original_filename)
        elif lower_filename.endswith('.txt'): # Assuming pasted text is saved as .txt
            logging.info(f"Detected TXT file. Adding Text processing task for doc_id: {doc_id}")
            background_tasks.add_task(process_uploaded_text, doc_id, gcs_uri, original_filename)
        # Add elif for .docx, etc. if you implement extraction for them
        # elif lower_filename.endswith('.docx'):
        #     logging.info(f"Detected DOCX file. Adding DOCX processing task for doc_id: {doc_id}")
        #     background_tasks.add_task(process_uploaded_docx, doc_id, gcs_uri, original_filename) # Example
        else:
            logging.info(f"Ignoring unsupported file type: {file_name}")
            # Mark as error in Firestore immediately? Or just ignore.
            # Let's mark it as an error for visibility.
            try:
                if db:
                    db.collection("documents").document(doc_id).set({
                        "source_name": original_filename,
                        "document_type": "UNSUPPORTED",
                        "gcs_uri": gcs_uri,
                        "timestamp": firestore.SERVER_TIMESTAMP,
                        "status": "Error",
                        "error_message": f"Unsupported file type: {os.path.splitext(original_filename)[1]}"
                    }, merge=True)
            except Exception as db_e:
                 logging.info(f"Failed to mark unsupported file {doc_id} as Error in Firestore: {db_e}")
            # Return success to Pub/Sub so it doesn't retry
            return {"status": "ignored", "message": "Unsupported file type"}
        # --- End File Type Determination ---

        # Acknowledge the Pub/Sub message
        return {"status": "success", "message": "Processing initiated", "doc_id": doc_id}

    except json.JSONDecodeError as e:
        logging.info(f"Error decoding Pub/Sub message data JSON: {e}")
        # Don't retry bad format
        return {"status": "error", "message": f"Invalid JSON in message data: {e}"}, 400
    except Exception as e:
        logging.info(f"Error processing GCS event message {request.message.messageId}: {e}")
        # Let background task handle retries if applicable, but acknowledge message receipt
        # Or return 500 to potentially trigger Pub/Sub retries if the error is transient
        # For now, return 500 to indicate failure to *initiate* processing
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process GCS event: {e}")


# --- Add Helper Function ---
async def read_text_from_gcs(gcs_uri: str) -> str:
    """Downloads and reads text content from a GCS file."""
    try:
        # Parse GCS URI
        if not gcs_uri.startswith("gs://"):
            raise ValueError("Invalid GCS URI format. Must start with gs://")
        parts = gcs_uri[5:].split("/", 1)
        if len(parts) != 2:
            raise ValueError("Invalid GCS URI format. Must be gs://bucket_name/object_name")
        bucket_name, object_name = parts

        # Download the blob as bytes and decode
        storage_client = storage.Client() # Reuse client if possible, or initialize
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_name)

        logging.info(f"Attempting to download text from: {gcs_uri}")
        content_bytes = blob.download_as_bytes()
        logging.info(f"Downloaded {len(content_bytes)} bytes from {gcs_uri}")

        # Decode assuming UTF-8, handle potential errors
        try:
            content_text = content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            logging.info(f"Warning: Could not decode {gcs_uri} as UTF-8. Trying latin-1.")
            content_text = content_bytes.decode('latin-1') # Fallback encoding

        return content_text

    except Exception as e:
        logging.info(f"Error reading text from GCS URI {gcs_uri}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read text content from GCS: {e}")


# --- Create Text Processing Function ---
async def process_uploaded_text(doc_id: str, gcs_uri: str, original_filename: str):
    """
    Core logic to process a text file from GCS: read, chunk, summarize, store.
    Chunks are stored in a subcollection under the document.
    Updates document status in Firestore.
    """
    if not db or not model_summarization: # Only summarization model needed here
        logging.info("Error: Backend services (Firestore/Summarization) not fully initialized.")
        try:
            doc_ref = db.collection("documents").document(doc_id)
            doc_ref.set({"status": "Error", "source_name": original_filename, "gcs_uri": gcs_uri, "document_type": "TEXT"}, merge=True)
        except Exception as e:
            logging.info(f"Failed to mark doc {doc_id} as Error during service init failure: {e}")
        raise RuntimeError("Backend services not fully initialized.")

    logging.info(f"Starting TEXT processing for doc_id: {doc_id}, GCS URI: {gcs_uri}")
    doc_ref = db.collection("documents").document(doc_id)

    try:
        # 0. Set initial status in Firestore
        logging.info(f"Setting initial status 'Processing' for doc_id: {doc_id}")
        doc_ref.set({
            "source_name": original_filename,
            "document_type": "TEXT", # Specify type
            "gcs_uri": gcs_uri,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "status": "Processing"
        }, merge=True)

        # 1. Read Text from GCS
        logging.info(f"Reading text content from {gcs_uri} for doc_id: {doc_id}...")
        full_text = await read_text_from_gcs(gcs_uri)
        logging.info(f"Read {len(full_text)} characters from {gcs_uri}.")

        # 2. Chunk Text (Use the existing helper)
        logging.info(f"Chunking text for doc_id: {doc_id}...")
        text_chunks = chunk_text(full_text) # Use your preferred chunking strategy
        logging.info(f"Created {len(text_chunks)} chunks for doc_id: {doc_id}.")

        # 3. Summarize Chunks and Prepare for Firestore
        chunks_to_store = []
        if text_chunks: # Only summarize if there are chunks
            logging.info(f"Summarizing chunks for doc_id: {doc_id}...")
            for i, chunk in enumerate(text_chunks):
                summary = await summarize_chunk(chunk)
                chunks_to_store.append({
                    "chunk_text": chunk,
                    "summary": summary,
                    "chunk_order": i
                })
                if (i + 1) % 10 == 0: # Log progress
                    logging.info(f"  Summarized chunk {i+1}/{len(text_chunks)} for doc_id: {doc_id}")
        else:
             logging.info(f"No text content found to chunk for doc_id: {doc_id}. Skipping summarization.")


        # 4. Store in Firestore (uses the updated store_chunks_in_firestore)
        logging.info(f"Storing {len(chunks_to_store)} chunks in Firestore subcollection for doc_id: {doc_id}...")
        # Pass 'TEXT' as document_type, original_filename as source_name, and the gcs_uri
        store_chunks_in_firestore(doc_id, original_filename, "TEXT", chunks_to_store, gcs_uri=gcs_uri, initial_status="Processing")

        logging.info(f"Successfully processed and stored TEXT document: {doc_id}")

    except Exception as e:
        logging.info(f"Error during TEXT processing for doc_id {doc_id} ({gcs_uri}): {e}")
        # Update status to 'Error' in Firestore
        try:
            doc_ref.update({"status": "Error"})
            logging.info(f"Updated status to 'Error' for doc_id: {doc_id}")
        except Exception as update_e:
            logging.info(f"Failed to update status to 'Error' for doc_id {doc_id} after processing error: {update_e}")
        raise e # Re-raise the exception so background task runner knows it failed


# Add near other Pydantic models (e.g., after line 84)
class ChatMessage(BaseModel):
    id: str | None = None # Firestore document ID, optional on creation
    text: str
    sender: str = Field(..., pattern="^(user|bot)$") # Ensure sender is 'user' or 'bot'
    timestamp: datetime.datetime | None = None # Firestore will set this

class ChatMetadata(BaseModel):
    id: str | None = None # Firestore document ID
    title: str
    createdAt: datetime.datetime | None = None
    lastActivity: datetime.datetime | None = None

class NewChatResponse(BaseModel):
    id: str
    title: str
    messages: List[ChatMessage] # Include initial messages if any

# Add near other endpoint definitions (e.g., after line 1040)

# --- Chat Management Endpoints ---

@app.post("/chats", response_model=NewChatResponse, status_code=status.HTTP_201_CREATED)
async def create_new_chat():
    """
    Creates a new chat session in Firestore.
    Initializes with a default title and potentially a greeting message.
    """
    logging.info("POST /chats endpoint called: Creating new chat.")
    if not db:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Firestore not initialized")

    try:
        new_chat_id = str(uuid.uuid4())
        chat_ref = db.collection("chats").document(new_chat_id)
        initial_title = "New Chat"
        current_time = firestore.SERVER_TIMESTAMP # Use server timestamp

        # 1. Create the main chat document
        chat_data = {
            "title": initial_title,
            "createdAt": current_time,
            "lastActivity": current_time
        }
        chat_ref.set(chat_data)
        logging.info(f"Created chat document with ID: {new_chat_id}")

        # 2. (Optional) Add an initial bot message
        messages_ref = chat_ref.collection("messages")
        initial_message_id = str(uuid.uuid4())
        initial_message_data = {
            "text": "Hello! How can I help you today?",
            "sender": "bot",
            "timestamp": current_time
        }
        messages_ref.document(initial_message_id).set(initial_message_data)
        logging.info(f"Added initial bot message {initial_message_id} to chat {new_chat_id}")

        # Prepare the response message (without server-generated timestamp initially)
        response_message = ChatMessage(
            id=initial_message_id,
            text=initial_message_data["text"],
            sender=initial_message_data["sender"],
            timestamp=None # Timestamp will be set by server, client can approximate if needed
        )

        return NewChatResponse(
            id=new_chat_id,
            title=initial_title,
            messages=[response_message]
        )

    except Exception as e:
        logging.exception(f"Error creating new chat: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create new chat: {e}")


@app.get("/chats", response_model=List[ChatMetadata])
async def get_chat_list():
    """
    Retrieves metadata for all chat sessions, ordered by last activity.
    """
    logging.info("GET /chats endpoint called: Fetching chat list.")
    if not db:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Firestore not initialized")

    try:
        chats_ref = db.collection("chats").order_by("lastActivity", direction=firestore.Query.DESCENDING)
        chats_stream = chats_ref.stream()

        chat_list = []
        for chat_doc in chats_stream:
            chat_data = chat_doc.to_dict()
            # Ensure timestamps are timezone-aware if needed, Firestore usually handles this
            chat_list.append(ChatMetadata(
                id=chat_doc.id,
                title=chat_data.get("title", "Untitled Chat"),
                createdAt=chat_data.get("createdAt"),
                lastActivity=chat_data.get("lastActivity")
            ))
        logging.info(f"Retrieved {len(chat_list)} chats from Firestore.")
        return chat_list

    except Exception as e:
        logging.exception(f"Error retrieving chat list: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve chat list: {e}")


@app.get("/chats/{chat_id}/messages", response_model=List[ChatMessage])
async def get_chat_messages(chat_id: str):
    """
    Retrieves all messages for a specific chat session, ordered by timestamp.
    """
    logging.info(f"GET /chats/{chat_id}/messages endpoint called.")
    if not db:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Firestore not initialized")

    try:
        # Verify chat exists (optional but good practice)
        chat_ref = db.collection("chats").document(chat_id)
        if not chat_ref.get().exists:
             logging.warning(f"Chat not found: {chat_id}")
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chat with ID {chat_id} not found")

        messages_ref = chat_ref.collection("messages").order_by("timestamp", direction=firestore.Query.ASCENDING)
        messages_stream = messages_ref.stream()

        message_list = []
        for msg_doc in messages_stream:
            msg_data = msg_doc.to_dict()
            message_list.append(ChatMessage(
                id=msg_doc.id,
                text=msg_data.get("text", ""),
                sender=msg_data.get("sender", "unknown"),
                timestamp=msg_data.get("timestamp")
            ))
        logging.info(f"Retrieved {len(message_list)} messages for chat {chat_id}.")
        return message_list

    except HTTPException as http_exc:
        raise http_exc # Re-raise specific HTTP exceptions
    except Exception as e:
        logging.exception(f"Error retrieving messages for chat {chat_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve messages for chat {chat_id}: {e}")


# --- Modify Existing Query Endpoint ---

# Change the route decorator and function signature
@app.post("/chat/{chat_id}", response_model=QueryResponse)
async def handle_chat_query(chat_id: str, request: QueryRequest):
    """
    Handles user queries within a specific chat session.
    1. Saves the user message to Firestore.
    2. Performs hybrid retrieval (keyword + LLM ranking) with RRF.
    3. Generates an answer using the retrieved context.
    4. Saves the bot's answer to Firestore.
    5. Updates the chat's lastActivity timestamp and potentially the title.
    6. Returns the generated answer and retrieved chunk info.
    """
    logging.info(f"Received chat query for chat_id '{chat_id}': '{request.query}'")
    if not model_generation or not db:
        logging.error("Cannot handle chat query: Backend services (Generation Model/Firestore) not initialized.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backend services are not ready. Please try again later."
        )

    try:
        chat_ref = db.collection("chats").document(chat_id)
        messages_ref = chat_ref.collection("messages")
        current_time = firestore.SERVER_TIMESTAMP

        # --- Verify Chat Exists ---
        chat_snapshot = chat_ref.get()
        if not chat_snapshot.exists:
            logging.warning(f"Chat not found during query handling: {chat_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chat with ID {chat_id} not found")
        chat_data = chat_snapshot.to_dict()
        original_title = chat_data.get("title", "New Chat")
        # --- End Verification ---


        # --- Save User Message ---
        user_message_id = str(uuid.uuid4())
        user_message_data = {
            "text": request.query,
            "sender": "user",
            "timestamp": current_time
        }
        messages_ref.document(user_message_id).set(user_message_data)
        logging.info(f"Saved user message {user_message_id} to chat {chat_id}")
        # --- End Save User Message ---


        # --- Hybrid Retrieval Steps (Existing Logic) ---
        logging.info("Step 1: Performing hybrid search...")
        relevant_chunks_data = await search_summaries_hybrid(request.query, top_n=MAX_CHUNKS_FOR_CONTEXT)
        logging.info(f"Found {len(relevant_chunks_data)} relevant chunks for query '{request.query}'.")
        # --- End Hybrid Retrieval ---


        # --- Generate Answer (Existing Logic) ---
        logging.info(f"Step 2: Generating answer using {len(relevant_chunks_data)} context chunks...")
        answer_text = await generate_answer(request.query, relevant_chunks_data)
        # --- End Generate Answer ---


        # --- Save Bot Message ---
        bot_message_id = str(uuid.uuid4())
        bot_message_data = {
            "text": answer_text,
            "sender": "bot",
            "timestamp": current_time # Use same timestamp marker for ordering relative to user msg
        }
        messages_ref.document(bot_message_id).set(bot_message_data)
        logging.info(f"Saved bot message {bot_message_id} to chat {chat_id}")
        # --- End Save Bot Message ---


        # --- Update Chat Metadata ---
        update_data = {"lastActivity": current_time}
        # Update title if it's still the default "New Chat"
        if original_title == "New Chat" and request.query:
            # Simple title generation: first ~30 chars of user query
            MAX_TITLE_LEN = 30
            new_title = request.query[:MAX_TITLE_LEN]
            if len(request.query) > MAX_TITLE_LEN:
                new_title += "..."
            update_data["title"] = new_title
            logging.info(f"Updating chat {chat_id} title to '{new_title}'")

        chat_ref.update(update_data)
        logging.info(f"Updated lastActivity for chat {chat_id}")
        # --- End Update Chat Metadata ---


        # --- Format response chunks (Existing Logic) ---
        response_chunks = []
        for chunk_dict in relevant_chunks_data:
             try:
                 response_chunks.append(ChunkData(
                     chunk_id=chunk_dict.get("chunk_id", "unknown-chunk-id"),
                     doc_id=chunk_dict.get("doc_id", "unknown-doc-id"),
                     chunk_text=chunk_dict.get("chunk_text", ""),
                     summary=chunk_dict.get("summary", ""),
                     chunk_order=chunk_dict.get("chunk_order", -1)
                 ))
             except Exception as pydantic_error:
                 logging.warning(f"Could not format chunk {chunk_dict.get('chunk_id')} for response model: {pydantic_error}")
        # --- End Format Response Chunks ---


        logging.info(f"Sending answer for chat query '{request.query}'. Chunks used: {len(response_chunks)}")
        # Return the answer and chunks; frontend will fetch the updated message list separately
        return QueryResponse(answer=answer_text, retrieved_chunks=response_chunks)

    except HTTPException as http_exc:
         logging.warning(f"HTTPException while handling chat query '{request.query}' for chat {chat_id}: {http_exc.status_code} - {http_exc.detail}")
         raise http_exc
    except Exception as e:
        logging.exception(f"Unexpected error handling chat query '{request.query}' for chat {chat_id}: {e}")
        # Attempt to save an error message to the chat? Maybe too complex for now.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred while processing the query for chat {chat_id}."
        )
        
        

# --- To run FastAPI locally (for development) ---
if __name__ == "__main__":
    # Make sure GCP_PROJECT env var is set if running locally and need GCP access
    # You might need to run `gcloud auth application-default login`
    port = int(os.environ.get("PORT", 8080)) # Use 8080 as default if not set
    logging.info(f"Starting Uvicorn on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)