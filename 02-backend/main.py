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

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
    """Simple chunking function based on character count."""
    # This is a very basic chunking method. Consider using token-based chunking
    # or paragraph/sentence splitting from libraries like LangChain or NLTK
    # for more semantic chunking.
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += chunk_size - overlap
        if start < 0: # Avoid infinite loop if overlap >= chunk_size
            start = end
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
        prompt = f"Summarize the key information in the following text chunk in about {MAX_SUMMARY_TOKENS // 5} words. Focus on the main topics and entities:\n\n{chunk_text}"
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
    if not context_chunks:
        # Handle case where no relevant chunks were found
        # Option 1: Tell the user no context was found
        # return "I couldn't find relevant information in the provided documents to answer your question."
        # Option 2: Try answering without context (might hallucinate)
        logging.info("Warning: No relevant chunks found. Attempting to answer query without context.")
        context_str = "No relevant context found."
    else:
         # Format context
        context_str = "\n---\n".join([chunk.get("chunk_text", "") for chunk in context_chunks])

    prompt = f"""Based ONLY on the following context, answer the user's question. If the context doesn't contain the answer, say "I cannot answer this question based on the provided documents."

Context:
{context_str}

User Question: {query}

Answer:
"""
    try:
        response = await model_generation.generate_content_async(prompt)
         # Add basic error handling/checking for blocked content if needed
        if response.candidates and response.candidates[0].content.parts:
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


@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """
    Endpoint to handle user queries. Searches summaries and generates an answer.
    """
    if not db or not model_generation:
         raise HTTPException(status_code=500, detail="Backend services not fully initialized.")

    logging.info(f"Received query: {request.query}")

    try:
        # 1. Search relevant summaries
        # This uses the basic keyword scan across all summaries.
        # Consider adding filtering by doc_id if needed based on request.
        logging.info("Searching summaries...")
        retrieved_chunks_data = search_summaries_keyword(request.query)
        logging.info(f"Found {len(retrieved_chunks_data)} potentially relevant chunks.")

        # Convert raw dicts to Pydantic models for the response
        retrieved_chunks_models = [ChunkData(**chunk_data) for chunk_data in retrieved_chunks_data]

        # 2. Generate Answer
        logging.info("Generating answer...")
        answer = await generate_answer(request.query, retrieved_chunks_data) # Pass the raw dicts here

        return QueryResponse(answer=answer, retrieved_chunks=retrieved_chunks_models)

    except HTTPException as http_exc:
        # Re-raise HTTP exceptions directly
        raise http_exc
    except Exception as e:
        logging.info(f"Unhandled error during query processing for query '{request.query}': {e}")
        # Log the full error details here
        raise HTTPException(status_code=500, detail=f"Internal server error during query processing: {e}")


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


# --- To run FastAPI locally (for development) ---
if __name__ == "__main__":
    # Make sure GCP_PROJECT env var is set if running locally and need GCP access
    # You might need to run `gcloud auth application-default login`
    port = int(os.environ.get("PORT", 8080)) # Use 8080 as default if not set
    logging.info(f"Starting Uvicorn on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)