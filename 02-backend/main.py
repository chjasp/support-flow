# main.py

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from google.cloud import firestore
import os
import uuid
import re
from typing import List, Dict, Any

# --- Configuration ---
PROJECT_ID = os.environ.get("GCP_PROJECT") # Make sure this env var is set
LOCATION = "us-central1" # Or your preferred location
MODEL_NAME_EXTRACTION = "gemini-1.5-flash-001" # Use Flash for potentially faster/cheaper extraction/summarization
MODEL_NAME_SUMMARIZATION = "gemini-1.5-flash-001"
MODEL_NAME_GENERATION = "gemini-1.5-pro-preview-0409" # Use Pro for better final answers
MAX_SUMMARY_TOKENS = 100 # Limit summary length
MAX_CHUNKS_FOR_CONTEXT = 5 # Limit number of chunks sent to final LLM

# --- Initialization ---
try:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    db = firestore.Client()
    model_extraction = GenerativeModel(MODEL_NAME_EXTRACTION)
    model_summarization = GenerativeModel(MODEL_NAME_SUMMARIZATION,
                                        generation_config=GenerationConfig(max_output_tokens=MAX_SUMMARY_TOKENS))
    model_generation = GenerativeModel(MODEL_NAME_GENERATION)
    print("Vertex AI and Firestore initialized successfully.")
except Exception as e:
    print(f"Error initializing GCP services: {e}")
    # Handle initialization failure appropriately
    # You might want the app to fail startup if these don't initialize
    db = None
    model_extraction = None
    model_summarization = None
    model_generation = None


app = FastAPI(title="Chat with PDF API")

# --- Pydantic Models ---
class ProcessPdfRequest(BaseModel):
    gcs_uri: str = Field(..., description="GCS URI of the PDF file (gs://bucket_name/file_name)")
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
        print(f"Error extracting text from {gcs_uri} with Gemini: {e}")
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
             print(f"Warning: Summarization produced no content for chunk: {chunk_text[:100]}...")
             return "Summary could not be generated." # Placeholder for failed summaries
    except Exception as e:
        print(f"Error summarizing chunk with Gemini: {e}")
        # Decide how to handle summarization errors - return empty string, specific error message?
        return "Error during summarization." # Or return ""

def store_chunks_in_firestore(doc_id: str, original_filename: str, chunks_with_summaries: List[Dict[str, Any]]):
    """Stores document metadata and chunk data in Firestore."""
    if not db:
        raise HTTPException(status_code=500, detail="Firestore not initialized")
    try:
        # Store document metadata
        doc_ref = db.collection("documents").document(doc_id)
        doc_ref.set({
            "original_filename": original_filename,
            "processed_timestamp": firestore.SERVER_TIMESTAMP,
            "chunk_count": len(chunks_with_summaries)
        })

        # Store each chunk
        batch = db.batch()
        chunks_collection = db.collection("chunks")
        for item in chunks_with_summaries:
            chunk_doc_ref = chunks_collection.document(item["chunk_id"])
            batch.set(chunk_doc_ref, item)
        batch.commit()
        print(f"Stored {len(chunks_with_summaries)} chunks for doc_id: {doc_id}")
    except Exception as e:
        print(f"Error storing data in Firestore: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to store data in Firestore: {e}")

def search_summaries_keyword(query: str) -> List[Dict[str, Any]]:
    """
    Performs a basic keyword search across all chunk summaries in Firestore.
    WARNING: This is INEFFICIENT for large datasets as it fetches ALL chunks.
    """
    if not db:
        raise HTTPException(status_code=500, detail="Firestore not initialized")

    try:
        # Basic keyword extraction (split query into words, lowercase, remove common words)
        # Consider a more robust keyword extraction method
        stopwords = set(["a", "an", "the", "is", "in", "it", "of", "for", "on", "with"])
        keywords = [word for word in re.findall(r'\b\w+\b', query.lower()) if word not in stopwords]

        if not keywords:
            return [] # No keywords to search

        relevant_chunks = []
        chunks_ref = db.collection("chunks").stream() # Fetches ALL chunks!

        for chunk_doc in chunks_ref:
            chunk_data = chunk_doc.to_dict()
            summary_lower = chunk_data.get("summary", "").lower()
            chunk_text_lower = chunk_data.get("chunk_text", "").lower() # Also check original text? Maybe optional.

            # Score based on keyword presence in summary (or chunk text)
            score = 0
            matched_keywords = set()
            for keyword in keywords:
                 # Search in summary first
                if keyword in summary_lower:
                    score += 2 # Higher score for summary match
                    matched_keywords.add(keyword)
                 # Optional: Search in chunk text if not found in summary
                elif keyword in chunk_text_lower:
                     score += 1
                     matched_keywords.add(keyword)

            if score > 0:
                chunk_data_with_score = {**chunk_data, "score": score, "matched_keywords": list(matched_keywords)}
                # Ensure necessary fields are present for later use
                chunk_data_with_score['chunk_id'] = chunk_doc.id
                if 'doc_id' not in chunk_data_with_score: # Ensure doc_id is present
                   chunk_data_with_score['doc_id'] = chunk_data.get('doc_id', 'unknown') # Handle potential missing field
                relevant_chunks.append(chunk_data_with_score)


        # Sort by score (descending)
        relevant_chunks.sort(key=lambda x: x["score"], reverse=True)

        # Limit results (implement MAX_CHUNKS_FOR_CONTEXT)
        return relevant_chunks[:MAX_CHUNKS_FOR_CONTEXT]

    except Exception as e:
        print(f"Error searching summaries in Firestore: {e}")
        # Depending on the error, you might want to return [] or raise an exception
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
        print("Warning: No relevant chunks found. Attempting to answer query without context.")
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
             print(f"Warning: Answer generation produced no content for query: {query}")
             return "An error occurred while generating the answer, or the response was empty/blocked."

    except Exception as e:
        print(f"Error generating answer with Gemini: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate answer: {e}")


# --- API Endpoints ---

@app.post("/process-pdf", status_code=202) # 202 Accepted as processing is async
async def process_pdf_endpoint(request: ProcessPdfRequest):
    """
    Endpoint to trigger the processing of a PDF file stored in GCS.
    """
    if not db or not model_extraction or not model_summarization:
         raise HTTPException(status_code=500, detail="Backend services not fully initialized.")

    print(f"Received request to process GCS URI: {request.gcs_uri}")
    doc_id = str(uuid.uuid4()) # Generate a unique ID for this document

    try:
        # 1. Extract Text
        print(f"Extracting text from {request.gcs_uri}...")
        full_text = await extract_text_from_pdf_gemini(request.gcs_uri)
        if not full_text:
             raise HTTPException(status_code=400, detail="Could not extract text from PDF.")
        print(f"Extracted text length: {len(full_text)} characters.")


        # 2. Chunk Text
        print("Chunking text...")
        text_chunks = chunk_text(full_text) # Use your preferred chunking strategy
        print(f"Created {len(text_chunks)} chunks.")


        # 3. Summarize Chunks and Prepare for Firestore
        chunks_to_store = []
        print("Summarizing chunks...")
        for i, chunk in enumerate(text_chunks):
            chunk_id = f"{doc_id}_chunk_{i}"
            summary = await summarize_chunk(chunk)
            chunks_to_store.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "chunk_text": chunk,
                "summary": summary,
                "chunk_order": i
            })
            print(f"  Summarized chunk {i+1}/{len(text_chunks)}")


        # 4. Store in Firestore
        print(f"Storing {len(chunks_to_store)} chunks in Firestore for doc_id: {doc_id}...")
        store_chunks_in_firestore(doc_id, request.original_filename, chunks_to_store)


        return {"message": "PDF processing started successfully.", "doc_id": doc_id}

    except HTTPException as http_exc:
         # Re-raise HTTP exceptions directly
         raise http_exc
    except Exception as e:
        print(f"Unhandled error during PDF processing for {request.gcs_uri}: {e}")
        # Log the full error details here
        raise HTTPException(status_code=500, detail=f"Internal server error during PDF processing: {e}")


@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """
    Endpoint to handle user queries. Searches summaries and generates an answer.
    """
    if not db or not model_generation:
         raise HTTPException(status_code=500, detail="Backend services not fully initialized.")

    print(f"Received query: {request.query}")

    try:
        # 1. Search relevant summaries
        # This uses the basic keyword scan across all summaries.
        # Consider adding filtering by doc_id if needed based on request.
        print("Searching summaries...")
        retrieved_chunks_data = search_summaries_keyword(request.query)
        print(f"Found {len(retrieved_chunks_data)} potentially relevant chunks.")

        # Convert raw dicts to Pydantic models for the response
        retrieved_chunks_models = [ChunkData(**chunk_data) for chunk_data in retrieved_chunks_data]

        # 2. Generate Answer
        print("Generating answer...")
        answer = await generate_answer(request.query, retrieved_chunks_data) # Pass the raw dicts here

        return QueryResponse(answer=answer, retrieved_chunks=retrieved_chunks_models)

    except HTTPException as http_exc:
        # Re-raise HTTP exceptions directly
        raise http_exc
    except Exception as e:
        print(f"Unhandled error during query processing for query '{request.query}': {e}")
        # Log the full error details here
        raise HTTPException(status_code=500, detail=f"Internal server error during query processing: {e}")


# --- To run locally (for development) ---
if __name__ == "__main__":
    import uvicorn
    # Make sure GCP_PROJECT env var is set if running locally and need GCP access
    # You might need to run `gcloud auth application-default login`
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)