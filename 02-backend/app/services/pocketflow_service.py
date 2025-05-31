# services/pocketflow_service.py
"""
PocketFlow integration service.
Provides high-level interface for using PocketFlow workflows in the application.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

from app.flows.pocketflow_flows import (
    get_ingestion_flow, get_rag_flow, create_shared_store_template,
    run_document_ingestion, run_rag_query
)
from app.services.cloudsql import CloudSqlRepository
from app.config import get_settings

settings = get_settings()

class PocketFlowService:
    """
    Service class for integrating PocketFlow workflows.
    Provides async wrappers and error handling for the flows.
    """
    
    def __init__(self, sql_repo: CloudSqlRepository):
        self.sql_repo = sql_repo
        self.settings = settings
    
    @contextmanager
    def _get_db_connection(self):
        """Get database connection for PocketFlow operations."""
        try:
            with self.sql_repo.get_connection() as conn:
                yield conn
        except Exception as e:
            logging.error(f"Database connection error: {e}")
            raise
    
    async def ingest_documents(
        self, 
        urls: List[str], 
        files: List[str] = None,
        flow_type: str = "standard"
    ) -> Dict[str, Any]:
        """
        Ingest documents using PocketFlow workflow.
        
        Args:
            urls: List of URLs to process
            files: List of local file paths to process
            flow_type: Type of ingestion flow ("standard", "robust", "batch")
        
        Returns:
            Ingestion results with document IDs and metadata
        """
        try:
            # Prepare input data
            files = files or []
            
            logging.info(f"Starting PocketFlow ingestion for {len(urls)} URLs, {len(files)} files")
            
            # Create shared store
            shared = create_shared_store_template()
            shared["input"]["urls"] = urls
            shared["input"]["files"] = files
            
            # Run in executor to avoid blocking async event loop
            def run_ingestion():
                with self._get_db_connection() as conn:
                    shared["database_connection"] = conn
                    
                    # Get and run ingestion flow
                    flow = get_ingestion_flow(flow_type)
                    flow.run(shared)
                    
                    return {
                        "stored_documents": shared["output"]["stored_documents"],
                        "doc_ids": shared["output"]["doc_ids"],
                        "processing_stats": {
                            "total_input": len(urls) + len(files),
                            "successful_extractions": len(shared["processing"].get("extracted_content", [])),
                            "total_chunks": len(shared["processing"].get("chunks", [])),
                            "total_embeddings": len(shared["processing"].get("chunks_with_embeddings", [])),
                            "stored_documents": len(shared["output"]["stored_documents"])
                        }
                    }
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, run_ingestion)
            
            logging.info(f"PocketFlow ingestion completed: {result['processing_stats']}")
            return result
            
        except Exception as e:
            logging.error(f"PocketFlow ingestion failed: {e}", exc_info=True)
            raise Exception(f"Document ingestion failed: {str(e)}")
    
    async def process_query(
        self, 
        query: str,
        flow_type: str = "enhanced",
        max_context_chunks: int = None
    ) -> Dict[str, Any]:
        """
        Process user query using PocketFlow RAG workflow.
        
        Args:
            query: User's question
            flow_type: Type of RAG flow ("enhanced", "simple")
            max_context_chunks: Maximum number of context chunks to use
        
        Returns:
            Generated answer with sources and metadata
        """
        try:
            if not query or not query.strip():
                return {
                    "answer": "Please provide a valid question.",
                    "sources": [],
                    "quality_metrics": {}
                }
            
            logging.info(f"Starting PocketFlow RAG query: '{query[:50]}...'")
            
            # Create shared store
            shared = create_shared_store_template()
            shared["input"]["query"] = query.strip()
            
            # Run in executor to avoid blocking async event loop
            def run_rag():
                with self._get_db_connection() as conn:
                    shared["database_connection"] = conn
                    
                    # Get and run RAG flow
                    flow = get_rag_flow(flow_type)
                    flow.run(shared)
                    
                    # Limit context chunks if specified
                    context_chunks = shared["output"]["context_chunks"]
                    if max_context_chunks and len(context_chunks) > max_context_chunks:
                        context_chunks = context_chunks[:max_context_chunks]
                        shared["output"]["context_chunks"] = context_chunks
                        
                        # Update sources accordingly
                        used_doc_ids = set(chunk.get("doc_id") for chunk in context_chunks)
                        shared["output"]["sources"] = [
                            source for source in shared["output"]["sources"] 
                            if source.get("id") in used_doc_ids
                        ]
                    
                    return {
                        "answer": shared["output"]["answer"],
                        "sources": shared["output"]["sources"],
                        "context_chunks": shared["output"]["context_chunks"],
                        "quality_metrics": shared["output"]["quality_metrics"],
                        "query_metadata": {
                            "query_type": shared["retrieval"]["query_type"],
                            "initial_chunk_count": len(shared["retrieval"]["initial_chunks"]),
                            "enhanced_chunk_count": len(shared["retrieval"].get("enhanced_chunks", [])),
                            "final_chunk_count": len(shared["output"]["context_chunks"]),
                            "agent_analysis": shared["retrieval"].get("agent_analysis", {})
                        }
                    }
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, run_rag)
            
            logging.info(f"PocketFlow RAG completed: {result['query_metadata']}")
            return result
            
        except Exception as e:
            logging.error(f"PocketFlow RAG query failed: {e}", exc_info=True)
            return {
                "answer": f"I apologize, but I encountered an error processing your question: {str(e)}",
                "sources": [],
                "quality_metrics": {},
                "query_metadata": {}
            }
    
    async def process_urls_background(
        self, 
        urls: List[str], 
        description: str = ""
    ) -> Dict[str, Any]:
        """
        Background URL processing using PocketFlow (for web processing endpoint).
        
        Args:
            urls: List of URLs to process
            description: Optional description of the processing task
        
        Returns:
            Processing results
        """
        try:
            # Use robust flow for web processing
            result = await self.ingest_documents(
                urls=urls,
                flow_type="robust"
            )
            
            # Add description to metadata
            result["description"] = description
            result["url_count"] = len(urls)
            
            return result
            
        except Exception as e:
            logging.error(f"Background URL processing failed: {e}")
            raise
    
    async def hybrid_search_enhanced(self, query: str) -> List[Dict[str, Any]]:
        """
        Enhanced search function compatible with existing enhanced pipeline.
        Returns context chunks for backward compatibility.
        
        Args:
            query: Search query
        
        Returns:
            List of context chunks
        """
        try:
            result = await self.process_query(query, flow_type="enhanced")
            return result.get("context_chunks", [])
        except Exception as e:
            logging.error(f"Enhanced search failed: {e}")
            return []
    
    async def answer_enhanced(
        self, 
        query: str, 
        context_chunks: List[Dict[str, Any]]
    ) -> str:
        """
        Enhanced answer generation compatible with existing pipeline.
        
        Args:
            query: User query
            context_chunks: Context chunks (can be empty, will trigger search)
        
        Returns:
            Generated answer
        """
        try:
            if context_chunks:
                # Use provided context directly
                from app.utils.pocketflow_utils import generate_enhanced_answer, classify_query_type
                query_type = classify_query_type(query)
                return generate_enhanced_answer(query, context_chunks, query_type)
            else:
                # No context provided, run full RAG pipeline
                result = await self.process_query(query, flow_type="enhanced")
                return result.get("answer", "I couldn't generate an answer for your question.")
        except Exception as e:
            logging.error(f"Enhanced answer generation failed: {e}")
            return f"I apologize, but I encountered an error: {str(e)}"

# ================================================================
# Factory Functions for Dependency Injection
# ================================================================

def create_pocketflow_service(sql_repo: CloudSqlRepository) -> PocketFlowService:
    """
    Factory function to create PocketFlow service instance.
    
    Args:
        sql_repo: CloudSQL repository instance
    
    Returns:
        Configured PocketFlowService
    """
    return PocketFlowService(sql_repo)

# ================================================================
# Async Wrapper Functions
# ================================================================

async def run_ingestion_workflow(
    urls: List[str],
    files: List[str],
    sql_repo: CloudSqlRepository
) -> Dict[str, Any]:
    """
    Standalone function to run ingestion workflow.
    
    Args:
        urls: URLs to process
        files: File paths to process
        sql_repo: Database repository
    
    Returns:
        Ingestion results
    """
    service = create_pocketflow_service(sql_repo)
    return await service.ingest_documents(urls, files)

async def run_rag_workflow(
    query: str,
    sql_repo: CloudSqlRepository
) -> Dict[str, Any]:
    """
    Standalone function to run RAG workflow.
    
    Args:
        query: User query
        sql_repo: Database repository
    
    Returns:
        RAG results
    """
    service = create_pocketflow_service(sql_repo)
    return await service.process_query(query)

# ================================================================
# Compatibility Layer
# ================================================================

class PocketFlowCompatibilityLayer:
    """
    Compatibility layer to replace existing pipeline components.
    Allows gradual migration from old system to PocketFlow.
    """
    
    def __init__(self, sql_repo: CloudSqlRepository):
        self.pocketflow_service = create_pocketflow_service(sql_repo)
    
    async def hybrid_search_enhanced(self, query: str) -> List[Dict[str, Any]]:
        """Drop-in replacement for enhanced pipeline hybrid search."""
        return await self.pocketflow_service.hybrid_search_enhanced(query)
    
    async def answer_enhanced(
        self, 
        query: str, 
        context_chunks: List[Dict[str, Any]]
    ) -> str:
        """Drop-in replacement for enhanced pipeline answer generation."""
        return await self.pocketflow_service.answer_enhanced(query, context_chunks)

# ================================================================
# Testing and Monitoring
# ================================================================

async def test_pocketflow_integration(sql_repo: CloudSqlRepository) -> Dict[str, bool]:
    """
    Test PocketFlow integration with the application.
    
    Args:
        sql_repo: Database repository for testing
    
    Returns:
        Test results
    """
    service = create_pocketflow_service(sql_repo)
    results = {}
    
    # Test RAG workflow
    try:
        rag_result = await service.process_query(
            "How do I create a test resource?",
            flow_type="simple"  # Use simple for testing
        )
        results["rag_workflow"] = bool(rag_result.get("answer"))
        logging.info("RAG workflow test passed")
    except Exception as e:
        logging.error(f"RAG workflow test failed: {e}")
        results["rag_workflow"] = False
    
    # Test utilities
    try:
        from app.utils.pocketflow_utils import classify_query_type, get_embedding
        
        # Test query classification
        query_type = classify_query_type("Create an AWS S3 bucket")
        results["query_classification"] = bool(query_type)
        
        # Test embedding generation
        embedding = get_embedding("test text")
        results["embedding_generation"] = bool(embedding)
        
        logging.info("Utility functions test passed")
    except Exception as e:
        logging.error(f"Utility functions test failed: {e}")
        results["query_classification"] = False
        results["embedding_generation"] = False
    
    return results 