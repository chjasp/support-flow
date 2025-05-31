# flows/pocketflow_flows.py
"""
PocketFlow flow definitions for data ingestion and RAG pipelines.
Connects nodes into complete workflows.
"""

import logging
from pocketflow import Flow

# Import nodes
from .ingestion_nodes import (
    ValidateInputNode, ExtractContentNode, ChunkDocumentNode,
    GenerateEmbeddingsNode, StoreDatabaseNode, RobustWebScrapingNode
)
from .rag_nodes import (
    ClassifyQueryNode, InitialRetrievalNode, RAGAgentNode,
    EnhancedSearchNode, GenerateAnswerNode, ContextQualityNode,
    AgentAction
)

# ================================================================
# Data Ingestion Flow
# ================================================================

def create_ingestion_flow():
    """
    Create and return a data ingestion flow.
    
    Flow: Validate -> Extract -> Chunk -> Embed -> Store
    """
    # Create nodes
    validate_node = ValidateInputNode()
    extract_node = ExtractContentNode()
    chunk_node = ChunkDocumentNode()
    embed_node = GenerateEmbeddingsNode()
    store_node = StoreDatabaseNode()
    
    # Connect nodes in sequence
    validate_node >> extract_node >> chunk_node >> embed_node >> store_node
    
    # Create flow starting with validation
    flow = Flow(start=validate_node)
    
    return flow

def create_robust_web_ingestion_flow():
    """
    Create a more robust web ingestion flow with retry capabilities.
    """
    # Create nodes with enhanced error handling
    robust_scraping_node = RobustWebScrapingNode()
    chunk_node = ChunkDocumentNode()
    embed_node = GenerateEmbeddingsNode()
    store_node = StoreDatabaseNode()
    
    # Connect nodes
    robust_scraping_node >> chunk_node >> embed_node >> store_node
    
    return Flow(start=robust_scraping_node)

# ================================================================
# RAG Query Flow
# ================================================================

def create_rag_flow():
    """
    Create and return a RAG query flow with agent-enhanced retrieval.
    
    Flow: Classify -> Retrieve -> Agent -> [Enhanced Search] -> Generate
    """
    # Create nodes
    classify_node = ClassifyQueryNode()
    retrieve_node = InitialRetrievalNode()
    agent_node = RAGAgentNode()
    enhanced_search_node = EnhancedSearchNode()
    generate_node = GenerateAnswerNode()
    quality_node = ContextQualityNode()
    
    # Basic flow connections
    classify_node >> retrieve_node >> agent_node
    
    # Agent decision routing
    agent_node - AgentAction.SUFFICIENT_CONTEXT.value >> generate_node
    agent_node - AgentAction.SEARCH_MORE.value >> enhanced_search_node
    agent_node - AgentAction.NEED_EXAMPLES.value >> enhanced_search_node
    agent_node - AgentAction.SEARCH_SPECIFIC.value >> enhanced_search_node
    
    # Enhanced search loops back to agent for re-evaluation
    enhanced_search_node >> agent_node
    
    # Final generation and quality evaluation
    generate_node >> quality_node
    
    return Flow(start=classify_node)

def create_simple_rag_flow():
    """
    Create a simplified RAG flow without agent enhancement.
    Useful for basic queries or as a fallback.
    """
    classify_node = ClassifyQueryNode()
    retrieve_node = InitialRetrievalNode()
    generate_node = GenerateAnswerNode()
    
    # Simple linear flow
    classify_node >> retrieve_node >> generate_node
    
    return Flow(start=classify_node)

# ================================================================
# Combined Flows
# ================================================================

def create_batch_ingestion_flow():
    """
    Create a flow optimized for batch processing multiple documents.
    """
    # Use batch-optimized nodes
    validate_node = ValidateInputNode()
    extract_node = ExtractContentNode()  # Already a BatchNode
    chunk_node = ChunkDocumentNode()     # Already a BatchNode
    embed_node = GenerateEmbeddingsNode() # Already a BatchNode
    store_node = StoreDatabaseNode()
    
    # Connect in sequence
    validate_node >> extract_node >> chunk_node >> embed_node >> store_node
    
    return Flow(start=validate_node)

# ================================================================
# Flow Factory Functions
# ================================================================

def get_ingestion_flow(flow_type: str = "standard"):
    """
    Factory function to get different types of ingestion flows.
    
    Args:
        flow_type: "standard", "robust", or "batch"
    
    Returns:
        Configured PocketFlow Flow
    """
    if flow_type == "robust":
        return create_robust_web_ingestion_flow()
    elif flow_type == "batch":
        return create_batch_ingestion_flow()
    else:
        return create_ingestion_flow()

def get_rag_flow(flow_type: str = "enhanced"):
    """
    Factory function to get different types of RAG flows.
    
    Args:
        flow_type: "enhanced" (with agent) or "simple"
    
    Returns:
        Configured PocketFlow Flow
    """
    if flow_type == "simple":
        return create_simple_rag_flow()
    else:
        return create_rag_flow()

# ================================================================
# Flow Configuration Templates
# ================================================================

def create_shared_store_template():
    """
    Create a template for the shared store structure.
    """
    return {
        "input": {
            "urls": [],
            "files": [],
            "query": "",
        },
        "processing": {
            "documents": [],
            "extracted_content": [],
            "chunks": [],
            "embeddings": [],
            "chunks_with_embeddings": [],
            "metadata": {}
        },
        "retrieval": {
            "query": "",
            "query_type": "",
            "query_embedding": [],
            "initial_chunks": [],
            "enhanced_chunks": [],
            "agent_analysis": {},
            "context": ""
        },
        "output": {
            "answer": "",
            "sources": [],
            "doc_ids": [],
            "stored_documents": {},
            "context_chunks": [],
            "quality_metrics": {}
        },
        "database_connection": None  # Will be injected at runtime
    }

# ================================================================
# Example Usage Functions
# ================================================================

def run_document_ingestion(urls: list, database_connection):
    """
    Example function showing how to run document ingestion.
    
    Args:
        urls: List of URLs to process
        database_connection: Database connection object
    
    Returns:
        Processing results
    """
    # Create shared store
    shared = create_shared_store_template()
    shared["input"]["urls"] = urls
    shared["database_connection"] = database_connection
    
    # Get and run ingestion flow
    flow = get_ingestion_flow("standard")
    flow.run(shared)
    
    # Return results
    return {
        "stored_documents": shared["output"]["stored_documents"],
        "doc_ids": shared["output"]["doc_ids"]
    }

def run_rag_query(query: str, database_connection):
    """
    Example function showing how to run RAG query.
    
    Args:
        query: User's question
        database_connection: Database connection object
    
    Returns:
        Generated answer and sources
    """
    # Create shared store
    shared = create_shared_store_template()
    shared["input"]["query"] = query
    shared["database_connection"] = database_connection
    
    # Get and run RAG flow
    flow = get_rag_flow("enhanced")
    flow.run(shared)
    
    # Return results
    return {
        "answer": shared["output"]["answer"],
        "sources": shared["output"]["sources"],
        "quality_metrics": shared["output"]["quality_metrics"]
    }

# ================================================================
# Flow Testing Functions
# ================================================================

def test_ingestion_flow():
    """Test the ingestion flow with mock data."""
    shared = create_shared_store_template()
    shared["input"]["urls"] = ["https://example.com"]
    
    # Mock database connection for testing
    class MockConnection:
        def cursor(self):
            return MockCursor()
        def commit(self):
            pass
        def rollback(self):
            pass
    
    class MockCursor:
        def execute(self, query, params=None):
            pass
        def fetchall(self):
            return []
        def fetchone(self):
            return None
    
    shared["database_connection"] = MockConnection()
    
    flow = get_ingestion_flow("standard")
    
    try:
        flow.run(shared)
        logging.info("Ingestion flow test completed successfully")
        return True
    except Exception as e:
        logging.error(f"Ingestion flow test failed: {e}")
        return False

def test_rag_flow():
    """Test the RAG flow with mock data."""
    shared = create_shared_store_template()
    shared["input"]["query"] = "How do I create an AWS S3 bucket?"
    
    # Mock database connection
    class MockConnection:
        def cursor(self):
            return MockCursor()
    
    class MockCursor:
        def execute(self, query, params=None):
            pass
        def fetchall(self):
            # Return mock search results
            return [
                ("chunk1", "Create an S3 bucket using terraform", 0, "doc1", "s3-docs.md", None, 0.8),
                ("chunk2", "resource aws_s3_bucket example", 1, "doc1", "s3-docs.md", None, 0.7)
            ]
    
    shared["database_connection"] = MockConnection()
    
    flow = get_rag_flow("enhanced")
    
    try:
        flow.run(shared)
        logging.info("RAG flow test completed successfully")
        logging.info(f"Generated answer: {shared['output']['answer'][:100]}...")
        return True
    except Exception as e:
        logging.error(f"RAG flow test failed: {e}")
        return False

if __name__ == "__main__":
    # Run tests when executed directly
    logging.basicConfig(level=logging.INFO)
    
    print("Testing ingestion flow...")
    test_ingestion_flow()
    
    print("\nTesting RAG flow...")
    test_rag_flow() 