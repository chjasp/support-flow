# flows/ingestion_nodes.py
"""
PocketFlow nodes for document ingestion pipeline.
Handles processing of documents (PDFs, web pages, etc.) into searchable chunks.
"""

import logging
import uuid
import tempfile
import os
from typing import List, Dict, Any
from pathlib import Path

from pocketflow import Node, BatchNode
from app.utils.pocketflow_utils import (
    download_file_from_gcs, scrape_web_page, batch_get_embeddings, 
    store_document_chunks
)

class ValidateInputNode(Node):
    """
    Validates and prepares input URLs/files for processing.
    Downloads files if needed and validates content.
    """
    
    def prep(self, shared):
        """Read input URLs and files from shared store."""
        return {
            "urls": shared["input"].get("urls", []),
            "files": shared["input"].get("files", [])
        }
    
    def exec(self, inputs):
        """Validate and download content."""
        urls = inputs["urls"]
        files = inputs["files"]
        
        validated_documents = []
        
        # Process URLs
        for url in urls:
            if isinstance(url, str) and (url.startswith("http://") or url.startswith("https://")):
                validated_documents.append({
                    "source": url,
                    "type": "url",
                    "status": "ready"
                })
            else:
                logging.warning(f"Invalid URL: {url}")
        
        # Process local files
        for file_path in files:
            if os.path.exists(file_path):
                validated_documents.append({
                    "source": file_path,
                    "type": "file",
                    "status": "ready"
                })
            else:
                logging.warning(f"File not found: {file_path}")
        
        return validated_documents
    
    def post(self, shared, prep_res, exec_res):
        """Store validated documents for processing."""
        shared["processing"]["documents"] = exec_res
        logging.info(f"Validated {len(exec_res)} documents for processing")

class ExtractContentNode(BatchNode):
    """
    Extracts text content from documents (URLs, PDFs, etc.).
    Handles different content types and formats.
    """
    
    def prep(self, shared):
        """Get documents to process."""
        return shared["processing"]["documents"]
    
    def exec(self, document):
        """Extract content from a single document."""
        doc_type = document["type"]
        source = document["source"]
        
        try:
            if doc_type == "url":
                # Scrape web content
                content_data = scrape_web_page(source)
                if content_data:
                    return {
                        "source": source,
                        "filename": f"{content_data['title']}.html",
                        "content": content_data["content"],
                        "content_type": "text/html",
                        "metadata": {
                            "url": source,
                            "title": content_data["title"]
                        }
                    }
                
            elif doc_type == "file":
                # Process local file
                file_path = Path(source)
                
                if file_path.suffix.lower() == ".txt":
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    return {
                        "source": source,
                        "filename": file_path.name,
                        "content": content,
                        "content_type": "text/plain",
                        "metadata": {
                            "file_path": str(file_path)
                        }
                    }
                
                elif file_path.suffix.lower() == ".pdf":
                    # Would integrate with existing PDF processing
                    # For now, return placeholder
                    return {
                        "source": source,
                        "filename": file_path.name,
                        "content": "[PDF content would be extracted here]",
                        "content_type": "application/pdf",
                        "metadata": {
                            "file_path": str(file_path)
                        }
                    }
            
            # Return None for failed extraction
            return None
            
        except Exception as e:
            logging.error(f"Content extraction failed for {source}: {e}")
            return None
    
    def post(self, shared, prep_res, exec_res_list):
        """Store extracted content."""
        # Filter out None results
        successful_extractions = [result for result in exec_res_list if result is not None]
        
        shared["processing"]["extracted_content"] = successful_extractions
        logging.info(f"Successfully extracted content from {len(successful_extractions)} documents")

class ChunkDocumentNode(BatchNode):
    """
    Chunks documents into smaller pieces for embedding.
    Uses intelligent chunking that preserves context.
    """
    
    def __init__(self, chunk_size: int = 800, overlap: int = 200, **kwargs):
        super().__init__(**kwargs)
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def prep(self, shared):
        """Get extracted content for chunking."""
        return shared["processing"]["extracted_content"]
    
    def exec(self, document):
        """Chunk a single document."""
        content = document["content"]
        filename = document["filename"]
        
        # Simple token-based chunking (can be enhanced with Terraform-aware chunking)
        chunks = self._chunk_text(content, self.chunk_size, self.overlap)
        
        return {
            "filename": filename,
            "source": document["source"],
            "content_type": document["content_type"],
            "metadata": document["metadata"],
            "chunks": chunks
        }
    
    def _chunk_text(self, text: str, max_tokens: int, overlap: int) -> List[str]:
        """Simple text chunking by tokens."""
        # This is a simplified version - in production you'd use tiktoken
        words = text.split()
        chunks = []
        
        start = 0
        while start < len(words):
            end = min(start + max_tokens, len(words))
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            
            if end == len(words):
                break
            start = end - overlap if overlap else end
        
        return chunks
    
    def post(self, shared, prep_res, exec_res_list):
        """Store chunked documents."""
        all_chunks_with_metadata = []
        
        for doc_chunks in exec_res_list:
            for i, chunk_text in enumerate(doc_chunks["chunks"]):
                all_chunks_with_metadata.append({
                    "chunk_text": chunk_text,
                    "chunk_index": i,
                    "filename": doc_chunks["filename"],
                    "source": doc_chunks["source"],
                    "content_type": doc_chunks["content_type"],
                    "metadata": doc_chunks["metadata"]
                })
        
        shared["processing"]["chunks"] = all_chunks_with_metadata
        logging.info(f"Created {len(all_chunks_with_metadata)} chunks from {len(exec_res_list)} documents")

class GenerateEmbeddingsNode(BatchNode):
    """
    Generates embeddings for text chunks using Vertex AI.
    Processes chunks in batches for efficiency.
    """
    
    def __init__(self, batch_size: int = 50, **kwargs):
        super().__init__(**kwargs)
        self.batch_size = batch_size
    
    def prep(self, shared):
        """Get chunks for embedding generation."""
        return shared["processing"]["chunks"]
    
    def exec(self, chunk):
        """Generate embedding for a single chunk."""
        # Note: For efficiency, this should actually be done in batches
        # This is simplified for the node structure
        from app.utils.pocketflow_utils import get_embedding
        
        chunk_text = chunk["chunk_text"]
        embedding = get_embedding(chunk_text)
        
        return {
            **chunk,  # Include all original metadata
            "embedding": embedding
        }
    
    def post(self, shared, prep_res, exec_res_list):
        """Store chunks with embeddings."""
        shared["processing"]["chunks_with_embeddings"] = exec_res_list
        
        # Count successful embeddings
        successful_embeddings = len([chunk for chunk in exec_res_list if chunk.get("embedding")])
        logging.info(f"Generated {successful_embeddings} embeddings from {len(exec_res_list)} chunks")

class StoreDatabaseNode(Node):
    """
    Stores processed chunks and embeddings to the database.
    Creates document records and chunk records.
    """
    
    def prep(self, shared):
        """Get processed chunks with embeddings."""
        return {
            "chunks_with_embeddings": shared["processing"]["chunks_with_embeddings"],
            "database_connection": shared.get("database_connection")
        }
    
    def exec(self, inputs):
        """Store chunks to database."""
        chunks_with_embeddings = inputs["chunks_with_embeddings"]
        conn = inputs["database_connection"]
        
        if not conn:
            raise ValueError("Database connection not available")
        
        stored_documents = {}
        
        # Group chunks by document
        documents = {}
        for chunk in chunks_with_embeddings:
            source = chunk["source"]
            if source not in documents:
                documents[source] = {
                    "filename": chunk["filename"],
                    "source": source,
                    "content_type": chunk["content_type"],
                    "metadata": chunk["metadata"],
                    "chunks": []
                }
            documents[source]["chunks"].append(chunk)
        
        # Store each document
        for source, doc_data in documents.items():
            try:
                # Create document ID
                doc_id = uuid.uuid4()
                
                # Store document metadata
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO documents (
                        doc_id, filename, gcs_uri, status, created_at
                    ) VALUES (%s, %s, %s, %s, NOW())
                """, (doc_id, doc_data["filename"], source, "completed"))
                
                # Prepare chunks and embeddings for bulk insert
                chunks = [chunk["chunk_text"] for chunk in doc_data["chunks"]]
                embeddings = [chunk["embedding"] for chunk in doc_data["chunks"]]
                
                # Store chunks
                success = store_document_chunks(
                    conn, doc_id, doc_data["filename"], 
                    chunks, embeddings, doc_data["metadata"]
                )
                
                if success:
                    stored_documents[source] = {
                        "doc_id": str(doc_id),
                        "filename": doc_data["filename"],
                        "chunk_count": len(chunks)
                    }
                
                conn.commit()
                
            except Exception as e:
                logging.error(f"Failed to store document {source}: {e}")
                conn.rollback()
        
        return stored_documents
    
    def post(self, shared, prep_res, exec_res):
        """Store results in shared."""
        shared["output"]["stored_documents"] = exec_res
        shared["output"]["doc_ids"] = [doc["doc_id"] for doc in exec_res.values()]
        
        total_stored = len(exec_res)
        logging.info(f"Successfully stored {total_stored} documents to database")

# Node with retry capability for unreliable operations
class RobustWebScrapingNode(Node):
    """
    Web scraping node with built-in retries and error handling.
    Example of using PocketFlow's retry functionality.
    """
    
    def __init__(self, **kwargs):
        # Configure retries for unreliable web operations
        super().__init__(max_retries=3, wait=5, **kwargs)
    
    def prep(self, shared):
        """Get URLs to scrape."""
        return shared["input"]["urls"]
    
    def exec(self, urls):
        """Scrape web content with retries."""
        scraped_content = []
        
        for url in urls:
            try:
                content_data = scrape_web_page(url)
                if content_data:
                    scraped_content.append(content_data)
                else:
                    # Raise exception to trigger retry
                    raise Exception(f"Failed to scrape content from {url}")
            except Exception as e:
                logging.error(f"Scraping failed for {url} (attempt {self.cur_retry + 1}): {e}")
                raise  # Re-raise to trigger retry mechanism
        
        return scraped_content
    
    def exec_fallback(self, urls, exc):
        """Fallback when all retries are exhausted."""
        logging.warning(f"Web scraping failed after {self.max_retries} attempts: {exc}")
        # Return empty list instead of failing completely
        return []
    
    def post(self, shared, prep_res, exec_res):
        """Store scraped content."""
        shared["processing"]["scraped_content"] = exec_res
        logging.info(f"Successfully scraped {len(exec_res)} web pages") 