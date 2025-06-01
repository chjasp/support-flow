# flows/rag_nodes.py
"""
PocketFlow nodes for RAG (Retrieval Augmented Generation) pipeline.
Handles user queries with enhanced retrieval and generation.
"""

import logging
import json
from typing import List, Dict, Any, Optional
from enum import Enum

from pocketflow import Node
from app.utils.pocketflow_utils import (
    classify_query_type, generate_enhanced_answer, 
    get_embedding, vector_search_chunks
)

class QueryType(Enum):
    """Types of queries for specialized handling."""
    TERRAFORM = "terraform"
    CODE_GENERATION = "code_generation"
    DOCUMENTATION = "documentation"
    GENERAL_QA = "general_qa"

class AgentAction(Enum):
    """Possible actions the RAG agent can take."""
    SEARCH_MORE = "search_more"
    SEARCH_SPECIFIC = "search_specific"
    NEED_EXAMPLES = "need_examples"
    SUFFICIENT_CONTEXT = "sufficient_context"

class ClassifyQueryNode(Node):
    """
    Classifies user queries to determine the best retrieval strategy.
    Routes to specialized handling based on query type.
    """
    
    def prep(self, shared):
        """Get user query from shared store."""
        return shared["input"]["query"]
    
    def exec(self, query):
        """Classify the query type."""
        if not query or not query.strip():
            return QueryType.GENERAL_QA.value
        
        query_type = classify_query_type(query.strip())
        logging.info(f"Classified query '{query[:50]}...' as: {query_type}")
        return query_type
    
    def post(self, shared, prep_res, exec_res):
        """Store query type for downstream nodes."""
        shared["retrieval"]["query_type"] = exec_res
        shared["retrieval"]["query"] = prep_res

class InitialRetrievalNode(Node):
    """
    Performs initial vector search based on query type.
    Different strategies for different query types.
    """
    
    def __init__(self, default_limit: int = 10, **kwargs):
        super().__init__(**kwargs)
        self.default_limit = default_limit
    
    def prep(self, shared):
        """Get query and type for retrieval."""
        return {
            "query": shared["retrieval"]["query"],
            "query_type": shared["retrieval"]["query_type"],
            "database_connection": shared.get("database_connection")
        }
    
    def exec(self, inputs):
        """Perform retrieval based on query type."""
        query = inputs["query"]
        query_type = inputs["query_type"]
        conn = inputs["database_connection"]
        
        if not conn:
            raise ValueError("Database connection not available")
        
        # Generate query embedding
        query_embedding = get_embedding(query)
        if not query_embedding:
            return {
                "chunks": [],
                "query_embedding": []
            }
        
        # Adjust search parameters based on query type
        if query_type == QueryType.TERRAFORM.value:
            # For Terraform queries, get more specific results
            chunks = vector_search_chunks(
                conn, query_embedding, 
                limit=self.default_limit, 
                similarity_threshold=0.7
            )
        elif query_type == QueryType.CODE_GENERATION.value:
            # For code generation, prioritize examples
            chunks = vector_search_chunks(
                conn, query_embedding, 
                limit=self.default_limit + 5,  # Get more candidates
                similarity_threshold=0.6
            )
        else:
            # Standard retrieval for other types
            chunks = vector_search_chunks(
                conn, query_embedding, 
                limit=self.default_limit, 
                similarity_threshold=0.5
            )
        
        logging.info(f"Initial retrieval found {len(chunks)} chunks for {query_type} query")
        return {
            "chunks": chunks,
            "query_embedding": query_embedding
        }
    
    def post(self, shared, prep_res, exec_res):
        """Store initial retrieval results."""
        shared["retrieval"]["initial_chunks"] = exec_res.get("chunks", [])
        shared["retrieval"]["query_embedding"] = exec_res.get("query_embedding", [])

class RAGAgentNode(Node):
    """
    Autonomous agent that analyzes retrieval quality and decides on improvements.
    Can iterate to enhance results before generation.
    """
    
    def __init__(self, **kwargs):
        # Enable retries for analysis iterations
        super().__init__(max_retries=3, **kwargs)
    
    def prep(self, shared):
        """Get current retrieval state for analysis."""
        return {
            "query": shared["retrieval"]["query"],
            "query_type": shared["retrieval"]["query_type"],
            "initial_chunks": shared["retrieval"]["initial_chunks"],
            "enhanced_chunks": shared["retrieval"].get("enhanced_chunks", [])
        }
    
    def exec(self, inputs):
        """Analyze context quality and decide on action."""
        query = inputs["query"]
        query_type = inputs["query_type"]
        initial_chunks = inputs["initial_chunks"]
        enhanced_chunks = inputs["enhanced_chunks"]
        
        # Use the better set of chunks for analysis
        current_chunks = enhanced_chunks if enhanced_chunks else initial_chunks
        
        if not current_chunks:
            return AgentAction.SEARCH_MORE.value
        
        # Analyze context based on query type
        analysis = self._analyze_context_quality(query, query_type, current_chunks)
        
        logging.info(f"RAG Agent analysis: {analysis['action']} - {analysis['reasoning']}")
        return analysis
    
    def _analyze_context_quality(self, query: str, query_type: str, chunks: List[Dict]) -> Dict[str, Any]:
        """Analyze retrieved context and determine action."""
        
        # Quick heuristic analysis (in production, could use LLM)
        chunk_count = len(chunks)
        avg_similarity = sum(chunk.get("similarity", 0) for chunk in chunks) / chunk_count if chunk_count > 0 else 0
        
        # Check for code content if it's a code-related query
        has_code = any(self._contains_code(chunk.get("chunk_text", "")) for chunk in chunks)
        
        if query_type == QueryType.TERRAFORM.value:
            if chunk_count < 3:
                return {
                    "action": AgentAction.SEARCH_MORE.value,
                    "reasoning": "Need more Terraform documentation"
                }
            elif not has_code and "resource" in query.lower():
                return {
                    "action": AgentAction.NEED_EXAMPLES.value,
                    "reasoning": "Need Terraform resource examples"
                }
        
        elif query_type == QueryType.CODE_GENERATION.value:
            if not has_code:
                return {
                    "action": AgentAction.NEED_EXAMPLES.value,
                    "reasoning": "Need code examples for generation"
                }
            elif chunk_count < 2:
                return {
                    "action": AgentAction.SEARCH_MORE.value,
                    "reasoning": "Need more code examples"
                }
        
        # General quality check
        if avg_similarity < 0.6:
            return {
                "action": AgentAction.SEARCH_MORE.value,
                "reasoning": "Low similarity scores, need better matches"
            }
        
        # Context seems sufficient
        return {
            "action": AgentAction.SUFFICIENT_CONTEXT.value,
            "reasoning": "Context quality appears sufficient"
        }
    
    def _contains_code(self, text: str) -> bool:
        """Check if text contains code-like content."""
        code_indicators = ['{', '}', 'resource "', 'def ', 'function', 'class ', 'import ', '= ']
        return any(indicator in text for indicator in code_indicators)
    
    def post(self, shared, prep_res, exec_res):
        """Store agent decision for next step."""
        shared["retrieval"]["agent_analysis"] = exec_res
        
        # Return action as string for flow routing
        if isinstance(exec_res, dict):
            return exec_res.get("action", AgentAction.SUFFICIENT_CONTEXT.value)
        return exec_res

class EnhancedSearchNode(Node):
    """
    Performs additional targeted search based on agent analysis.
    Triggered when agent determines more context is needed.
    """
    
    def prep(self, shared):
        """Get search parameters from agent analysis."""
        return {
            "query": shared["retrieval"]["query"],
            "query_type": shared["retrieval"]["query_type"],
            "agent_analysis": shared["retrieval"]["agent_analysis"],
            "query_embedding": shared["retrieval"]["query_embedding"],
            "database_connection": shared.get("database_connection")
        }
    
    def exec(self, inputs):
        """Perform enhanced search based on agent decision."""
        query = inputs["query"]
        query_type = inputs["query_type"]
        analysis = inputs["agent_analysis"]
        query_embedding = inputs["query_embedding"]
        conn = inputs["database_connection"]
        
        if not conn or not query_embedding:
            return []
        
        action = analysis.get("action") if isinstance(analysis, dict) else analysis
        
        if action == AgentAction.SEARCH_MORE.value:
            # Broaden search with lower threshold
            return vector_search_chunks(
                conn, query_embedding, 
                limit=15, 
                similarity_threshold=0.4
            )
        
        elif action == AgentAction.NEED_EXAMPLES.value:
            # Search specifically for code examples
            return self._search_for_examples(conn, query, query_type)
        
        elif action == AgentAction.SEARCH_SPECIFIC.value:
            # Would implement specific term search here
            return []
        
        return []
    
    def _search_for_examples(self, conn, query: str, query_type: str) -> List[Dict[str, Any]]:
        """Search specifically for code examples."""
        # This is a simplified version - could be enhanced with keyword search
        example_query = f"{query} example code configuration"
        example_embedding = get_embedding(example_query)
        
        if example_embedding:
            return vector_search_chunks(
                conn, example_embedding,
                limit=10,
                similarity_threshold=0.5
            )
        return []
    
    def post(self, shared, prep_res, exec_res):
        """Store enhanced search results."""
        existing_chunks = shared["retrieval"].get("enhanced_chunks", [])
        
        # Merge with existing enhanced chunks
        all_enhanced_chunks = existing_chunks + exec_res
        
        # Deduplicate by chunk_id
        seen_ids = set()
        unique_chunks = []
        for chunk in all_enhanced_chunks:
            chunk_id = chunk.get("chunk_id")
            if chunk_id not in seen_ids:
                unique_chunks.append(chunk)
                seen_ids.add(chunk_id)
        
        shared["retrieval"]["enhanced_chunks"] = unique_chunks
        logging.info(f"Enhanced search added {len(exec_res)} new chunks")

class GenerateAnswerNode(Node):
    """
    Generates final answer using retrieved context.
    Uses query-type specific prompts for better responses.
    """
    
    def __init__(self, **kwargs):
        # Enable retries for generation failures
        super().__init__(max_retries=2, wait=1, **kwargs)
    
    def prep(self, shared):
        """Get final context for answer generation."""
        # Use enhanced chunks if available, otherwise initial chunks
        enhanced_chunks = shared["retrieval"].get("enhanced_chunks", [])
        initial_chunks = shared["retrieval"].get("initial_chunks", [])
        
        final_chunks = enhanced_chunks if enhanced_chunks else initial_chunks
        
        return {
            "query": shared["retrieval"]["query"],
            "query_type": shared["retrieval"]["query_type"],
            "context_chunks": final_chunks
        }
    
    def exec(self, inputs):
        """Generate answer using context."""
        query = inputs["query"]
        query_type = inputs["query_type"]
        context_chunks = inputs["context_chunks"]
        
        if not context_chunks:
            return self._fallback_answer(query)
        
        # Generate enhanced answer based on query type
        answer = generate_enhanced_answer(query, context_chunks, query_type)
        
        if not answer or answer.strip() == "":
            raise Exception("Empty response from LLM")
        
        return answer
    
    def _fallback_answer(self, query: str) -> str:
        """Provide fallback when no context is available."""
        return (
            f"I apologize, but I couldn't find relevant information to answer your question: '{query}'. "
            "This might be because the topic isn't covered in the available documentation. "
            "Please try rephrasing your question or ask about a different topic."
        )
    
    def exec_fallback(self, inputs, exc):
        """Fallback when generation fails."""
        logging.warning(f"Answer generation failed: {exc}")
        return self._fallback_answer(inputs["query"])
    
    def post(self, shared, prep_res, exec_res):
        """Store final answer and context sources."""
        shared["output"]["answer"] = exec_res
        
        # Extract document sources for citation
        context_chunks = prep_res["context_chunks"]
        sources = []
        seen_docs = set()
        
        for chunk in context_chunks:
            doc_id = chunk.get("doc_id")
            if doc_id and doc_id not in seen_docs:
                sources.append({
                    "id": doc_id,
                    "name": chunk.get("doc_filename", "Unknown Document"),
                    "uri": chunk.get("gcs_uri"),
                    "similarity": chunk.get("similarity", 0)
                })
                seen_docs.add(doc_id)
        
        shared["output"]["sources"] = sources
        shared["output"]["context_chunks"] = context_chunks
        
        logging.info(f"Generated answer using {len(context_chunks)} chunks from {len(sources)} sources")

class ContextQualityNode(Node):
    """
    Optional node for evaluating context quality.
    Can be used for monitoring and improvement.
    """
    
    def prep(self, shared):
        """Get context and query for evaluation."""
        return {
            "query": shared["retrieval"]["query"],
            "context_chunks": shared["output"]["context_chunks"],
            "answer": shared["output"]["answer"]
        }
    
    def exec(self, inputs):
        """Evaluate context quality."""
        query = inputs["query"]
        context_chunks = inputs["context_chunks"]
        answer = inputs["answer"]
        
        # Simple quality metrics
        metrics = {
            "chunk_count": len(context_chunks),
            "avg_similarity": sum(chunk.get("similarity", 0) for chunk in context_chunks) / len(context_chunks) if context_chunks else 0,
            "answer_length": len(answer),
            "has_code": any(self._contains_code(chunk.get("chunk_text", "")) for chunk in context_chunks),
            "source_diversity": len(set(chunk.get("doc_id") for chunk in context_chunks))
        }
        
        return metrics
    
    def _contains_code(self, text: str) -> bool:
        """Check if text contains code."""
        code_indicators = ['{', '}', 'resource "', 'def ', 'function', 'class ']
        return any(indicator in text for indicator in code_indicators)
    
    def post(self, shared, prep_res, exec_res):
        """Store quality metrics."""
        shared["output"]["quality_metrics"] = exec_res
        logging.info(f"Context quality metrics: {exec_res}") 