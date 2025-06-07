"""
Utility functions for PocketFlow integration.
These functions provide the external interfaces needed by the PocketFlow nodes.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple
import requests
from google.cloud import storage
import google.genai as genai
from vertexai.language_models import TextEmbeddingModel
import vertexai

from app.config import get_settings

settings = get_settings()

# Initialize services
vertexai.init(project=settings.gcp_project, location=settings.gcp_location)
genai_client = genai.Client(
    vertexai=True,
    project=settings.gcp_project,
    location="global",
)
embedding_model = TextEmbeddingModel.from_pretrained(settings.model_embedding)
storage_client = storage.Client(project=settings.gcp_project)

# ================================================================
# LLM Utilities
# ================================================================

def call_gemini(prompt: str, temperature: float = 0.1) -> str:
    """
    Call Google Gemini LLM for text generation.
    
    Args:
        prompt: The input prompt
        temperature: Response randomness (0.0 to 1.0)
    
    Returns:
        Generated text response
    """
    try:
        config = genai.types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=8192,
        )
        
        response = genai_client.models.generate_content(
            model=settings.model_generation,
            contents=prompt,
            config=config
        )
        
        if response.candidates and response.candidates[0].content.parts:
            return response.candidates[0].content.parts[0].text
        else:
            logging.warning(f"Empty response from Gemini for prompt: {prompt[:100]}...")
            return "I apologize, but I couldn't generate a response. Please try again."
            
    except Exception as e:
        logging.error(f"Gemini API error: {e}")
        return f"Error generating response: {str(e)}"

def classify_query_type(query: str) -> str:
    """
    Classify user query into categories for specialized handling.
    
    Args:
        query: User's question/request
    
    Returns:
        Query type classification
    """
    classification_prompt = f"""
    Classify this user query into one of these categories:
    - "terraform": Terraform/Infrastructure-as-Code questions
    - "code_generation": Code creation/programming requests  
    - "documentation": Documentation lookup/explanation requests
    - "general_qa": General knowledge questions

    Query: "{query}"

    Respond with only the category name.
    """
    
    result = call_gemini(classification_prompt, temperature=0.0)
    # Clean up result and validate
    result = result.strip().lower()
    valid_types = ["terraform", "code_generation", "documentation", "general_qa"]
    
    if result in valid_types:
        return result
    else:
        # Default fallback
        return "general_qa"

def generate_enhanced_answer(query: str, context_chunks: List[Dict[str, Any]], query_type: str) -> str:
    """
    Generate an enhanced answer based on query type and context.
    
    Args:
        query: User's question
        context_chunks: Retrieved context chunks
        query_type: Classified query type
    
    Returns:
        Generated answer
    """
    # Build context from chunks
    context_texts = []
    for chunk in context_chunks:
        text = chunk.get("chunk_text", "")
        filename = chunk.get("doc_filename", "Unknown")
        context_texts.append(f"[{filename}]: {text}")
    
    context = "\n\n".join(context_texts)
    
    # Query-specific prompts
    if query_type == "terraform":
        prompt = f"""
        You are a Terraform expert. Answer this question using the provided documentation.
        Always include complete, working code examples when relevant.

        Question: {query}

        Documentation:
        {context}

        Provide a comprehensive answer with:
        1. Complete Terraform configuration if applicable
        2. Clear explanation of each component
        3. Best practices and considerations
        4. Any prerequisites or dependencies
        """
    
    elif query_type == "code_generation":
        prompt = f"""
        You are a software development expert. Generate code based on this request.

        Request: {query}

        Reference Documentation:
        {context}

        Provide:
        1. Complete, working code example
        2. Step-by-step explanation
        3. Setup/installation instructions if needed
        4. Error handling considerations
        """
    
    else:
        prompt = f"""
        Answer this question using the provided context. Be comprehensive and accurate.

        Question: {query}

        Context:
        {context}

        Provide a clear, well-structured answer.
        """
    
    return call_gemini(prompt)

# ================================================================
# Embedding Utilities
# ================================================================

def get_embedding(text: str) -> List[float]:
    """
    Generate embedding vector for text using Vertex AI.
    
    Args:
        text: Input text to embed
    
    Returns:
        Embedding vector as list of floats
    """
    try:
        embeddings = embedding_model.get_embeddings([text])
        if embeddings and len(embeddings) > 0:
            return embeddings[0].values
        else:
            logging.warning(f"No embedding returned for text: {text[:100]}...")
            return []
    except Exception as e:
        logging.error(f"Embedding generation error: {e}")
        return []

def batch_get_embeddings(texts: List[str], batch_size: int = 50) -> List[List[float]]:
    """
    Generate embeddings for multiple texts in batches.
    
    Args:
        texts: List of text strings to embed
        batch_size: Number of texts to process per batch
    
    Returns:
        List of embedding vectors
    """
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            embeddings = embedding_model.get_embeddings(batch)
            for emb in embeddings:
                all_embeddings.append(emb.values if emb else [])
        except Exception as e:
            logging.error(f"Batch embedding error for batch {i//batch_size}: {e}")
            # Add empty embeddings for failed batch
            all_embeddings.extend([[] for _ in batch])
    
    return all_embeddings

# ================================================================
# Document Processing Utilities
# ================================================================

def download_file_from_gcs(gcs_uri: str, local_path: str) -> bool:
    """
    Download file from Google Cloud Storage.
    
    Args:
        gcs_uri: GCS URI (gs://bucket/path)
        local_path: Local file path to save to
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Parse GCS URI
        if not gcs_uri.startswith("gs://"):
            return False
        
        path_parts = gcs_uri[5:].split("/", 1)
        bucket_name = path_parts[0]
        object_name = path_parts[1] if len(path_parts) > 1 else ""
        
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.download_to_filename(local_path)
        
        return True
    except Exception as e:
        logging.error(f"GCS download error: {e}")
        return False

def scrape_web_page(url: str) -> Optional[Dict[str, Any]]:
    """
    Scrape content from a web page.
    
    Args:
        url: URL to scrape
    
    Returns:
        Dictionary with page content and metadata
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract title
        title = soup.find('title')
        title_text = title.get_text().strip() if title else "Untitled"
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()
        
        # Extract text content
        text_content = soup.get_text()
        
        # Clean up text
        lines = (line.strip() for line in text_content.splitlines())
        text_content = '\n'.join(line for line in lines if line)
        
        return {
            "title": title_text,
            "content": text_content,
            "url": url,
            "content_type": "text/html"
        }
        
    except Exception as e:
        logging.error(f"Web scraping error for {url}: {e}")
        return None

# ================================================================
# Database Utilities
# ================================================================

def store_document_chunks(
    conn,
    doc_id: uuid.UUID,
    filename: str,
    chunks: List[str],
    embeddings: List[List[float]],
    metadata: Dict[str, Any]
) -> bool:
    """
    Store document chunks and embeddings to database.
    
    Args:
        conn: Database connection
        doc_id: Document UUID
        filename: Document filename
        chunks: Text chunks
        embeddings: Embedding vectors
        metadata: Document metadata
    
    Returns:
        True if successful, False otherwise
    """
    try:
        cursor = conn.cursor()
        
        # Insert chunks
        for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = uuid.uuid4()
            
            cursor.execute("""
                INSERT INTO document_chunks (
                    chunk_id, doc_id, chunk_index, chunk_text, 
                    embedding, token_count, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (
                chunk_id, doc_id, i, chunk_text,
                embedding, len(chunk_text.split()), 
            ))
        
        conn.commit()
        return True
        
    except Exception as e:
        logging.error(f"Database storage error: {e}")
        conn.rollback()
        return False

def vector_search_chunks(
    conn,
    query_embedding: List[float],
    limit: int = 10,
    similarity_threshold: float = 0.5
) -> List[Dict[str, Any]]:
    """
    Perform vector similarity search on document chunks.
    
    Args:
        conn: Database connection
        query_embedding: Query embedding vector
        limit: Maximum number of results
        similarity_threshold: Minimum similarity score
    
    Returns:
        List of matching chunks with metadata
    """
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                dc.chunk_id,
                dc.chunk_text,
                dc.chunk_index,
                d.doc_id,
                d.filename as doc_filename,
                d.gcs_uri,
                1 - (dc.embedding <=> %s::vector) as similarity
            FROM document_chunks dc
            JOIN documents d ON dc.doc_id = d.doc_id
            WHERE 1 - (dc.embedding <=> %s::vector) > %s
            ORDER BY dc.embedding <=> %s::vector
            LIMIT %s
        """, (query_embedding, query_embedding, similarity_threshold, query_embedding, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "chunk_id": str(row[0]),
                "chunk_text": row[1],
                "chunk_index": row[2],
                "doc_id": str(row[3]),
                "doc_filename": row[4],
                "gcs_uri": row[5],
                "similarity": float(row[6])
            })
        
        return results
        
    except Exception as e:
        logging.error(f"Vector search error: {e}")
        return []

def get_document_metadata(conn, doc_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """
    Retrieve document metadata from database.
    
    Args:
        conn: Database connection
        doc_id: Document UUID
    
    Returns:
        Document metadata dictionary
    """
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                doc_id, filename, gcs_uri, status, 
                created_at, updated_at, error_message
            FROM documents 
            WHERE doc_id = %s
        """, (doc_id,))
        
        row = cursor.fetchone()
        if row:
            return {
                "doc_id": str(row[0]),
                "filename": row[1],
                "gcs_uri": row[2],
                "status": row[3],
                "created_at": row[4],
                "updated_at": row[5],
                "error_message": row[6]
            }
        
        return None
        
    except Exception as e:
        logging.error(f"Database metadata error: {e}")
        return None

# ================================================================
# Test Functions (for development)
# ================================================================

if __name__ == "__main__":
    # Test LLM utility
    print("Testing Gemini API...")
    response = call_gemini("What is the meaning of life?")
    print(f"Gemini response: {response[:100]}...")
    
    # Test embedding
    print("\nTesting embedding...")
    embedding = get_embedding("Hello world")
    print(f"Embedding dimension: {len(embedding)}")
    
    # Test query classification
    print("\nTesting query classification...")
    query_type = classify_query_type("How do I create an AWS S3 bucket with Terraform?")
    print(f"Query type: {query_type}") 