"""
Agentic RAG system that can autonomously improve retrieval.
This agent can inspect retrieved context and take additional actions.
"""

import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

from .llm_service import LLMService
from .cloudsql import CloudSqlRepository
from .enhanced_pipeline import QueryType

class AgentAction(Enum):
    """Possible actions the agent can take."""
    SEARCH_MORE = "search_more"
    SEARCH_SPECIFIC = "search_specific"
    COMBINE_RESULTS = "combine_results"
    REQUEST_BROADER_CONTEXT = "request_broader_context"
    SUFFICIENT_CONTEXT = "sufficient_context"
    NEED_EXAMPLES = "need_examples"

class RAGAgent:
    """Autonomous agent that improves RAG retrieval through reasoning."""
    
    def __init__(self, llm_service: LLMService, sql_repo: CloudSqlRepository):
        self.llm_service = llm_service
        self.sql_repo = sql_repo
        self.max_iterations = 3
        
    async def improved_retrieval(self, query: str, initial_chunks: List[Dict[str, Any]], 
                               query_type: QueryType) -> List[Dict[str, Any]]:
        """
        Use agent reasoning to improve retrieval results.
        """
        logging.info(f"Agent starting improved retrieval for query type: {query_type.value}")
        
        current_chunks = initial_chunks.copy()
        iterations = 0
        
        while iterations < self.max_iterations:
            # Analyze current context
            analysis = await self._analyze_context(query, current_chunks, query_type)
            
            if analysis["action"] == AgentAction.SUFFICIENT_CONTEXT:
                logging.info(f"Agent determined context is sufficient after {iterations} iterations")
                break
                
            # Take action based on analysis
            additional_chunks = await self._take_action(query, current_chunks, analysis, query_type)
            
            if additional_chunks:
                # Merge and deduplicate
                current_chunks = self._merge_chunks(current_chunks, additional_chunks)
                logging.info(f"Agent iteration {iterations + 1}: Added {len(additional_chunks)} chunks")
            
            iterations += 1
        
        return current_chunks
    
    async def _analyze_context(self, query: str, chunks: List[Dict[str, Any]], 
                             query_type: QueryType) -> Dict[str, Any]:
        """Analyze the retrieved context and decide what action to take."""
        
        # Create context summary
        chunk_summaries = []
        for i, chunk in enumerate(chunks[:5]):  # Analyze top 5 chunks
            text = chunk.get("chunk_text", "")[:200]  # First 200 chars
            chunk_summaries.append(f"Chunk {i+1}: {text}...")
        
        context_summary = "\n".join(chunk_summaries)
        
        # Query-type specific analysis prompts
        if query_type == QueryType.TERRAFORM:
            analysis_prompt = self._get_terraform_analysis_prompt(query, context_summary)
        elif query_type == QueryType.CODE_GENERATION:
            analysis_prompt = self._get_code_analysis_prompt(query, context_summary)
        else:
            analysis_prompt = self._get_general_analysis_prompt(query, context_summary)
        
        # Get agent's analysis
        response = await self.llm_service.generate_answer(analysis_prompt)
        
        # Parse the response to extract action
        return self._parse_analysis_response(response)
    
    def _get_terraform_analysis_prompt(self, query: str, context_summary: str) -> str:
        """Analysis prompt specific to Terraform queries."""
        return f"""You are a RAG agent analyzing retrieved context for a Terraform question.

Query: {query}

Retrieved Context Summary:
{context_summary}

Analyze this context and determine what action to take. Consider:
1. Do we have complete resource documentation?
2. Are there code examples included?
3. Is the syntax information current and complete?
4. Do we need more specific provider documentation?

Respond with ONE of these actions in JSON format:
{{
    "action": "sufficient_context|search_more|search_specific|need_examples",
    "reasoning": "Brief explanation",
    "search_terms": ["additional", "search", "terms"] (if action is search_specific)
}}"""

    def _get_code_analysis_prompt(self, query: str, context_summary: str) -> str:
        """Analysis prompt for code generation queries."""
        return f"""You are a RAG agent analyzing context for a code generation question.

Query: {query}

Retrieved Context Summary:
{context_summary}

Analyze this context and determine if we need more information. Consider:
1. Are there complete code examples?
2. Is the documentation comprehensive enough for code generation?
3. Do we need more specific implementation details?

Respond with ONE action in JSON format:
{{
    "action": "sufficient_context|search_more|need_examples|search_specific",
    "reasoning": "Brief explanation",
    "search_terms": ["terms", "if", "needed"]
}}"""

    def _get_general_analysis_prompt(self, query: str, context_summary: str) -> str:
        """General analysis prompt."""
        return f"""Analyze the retrieved context for this query and determine if more information is needed.

Query: {query}

Context Summary:
{context_summary}

Respond in JSON format:
{{
    "action": "sufficient_context|search_more|request_broader_context",
    "reasoning": "Brief explanation"
}}"""
    
    def _parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse the agent's analysis response."""
        try:
            # Try to extract JSON from the response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                parsed = json.loads(json_str)
                
                # Convert action string to enum
                action_str = parsed.get("action", "sufficient_context")
                try:
                    action = AgentAction(action_str)
                except ValueError:
                    action = AgentAction.SUFFICIENT_CONTEXT
                
                return {
                    "action": action,
                    "reasoning": parsed.get("reasoning", ""),
                    "search_terms": parsed.get("search_terms", [])
                }
        except Exception as e:
            logging.warning(f"Failed to parse agent analysis: {e}")
        
        # Default fallback
        return {
            "action": AgentAction.SUFFICIENT_CONTEXT,
            "reasoning": "Failed to parse analysis",
            "search_terms": []
        }
    
    async def _take_action(self, query: str, current_chunks: List[Dict[str, Any]], 
                         analysis: Dict[str, Any], query_type: QueryType) -> List[Dict[str, Any]]:
        """Take action based on agent analysis."""
        action = analysis["action"]
        
        if action == AgentAction.SEARCH_MORE:
            return await self._search_more_context(query)
        elif action == AgentAction.SEARCH_SPECIFIC:
            search_terms = analysis.get("search_terms", [])
            return await self._search_specific_terms(search_terms)
        elif action == AgentAction.NEED_EXAMPLES:
            return await self._search_for_examples(query, query_type)
        elif action == AgentAction.REQUEST_BROADER_CONTEXT:
            return await self._get_broader_context(current_chunks)
        else:
            return []
    
    async def _search_more_context(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for additional context using the original query."""
        query_embedding = await self.llm_service.get_embedding(query)
        if not query_embedding:
            return []
        
        # Search with higher limit to get more diverse results
        return self.sql_repo.vector_search(query_embedding, limit)
    
    async def _search_specific_terms(self, search_terms: List[str]) -> List[Dict[str, Any]]:
        """Search for specific terms identified by the agent."""
        all_results = []
        
        for term in search_terms[:3]:  # Limit to top 3 terms
            query_embedding = await self.llm_service.get_embedding(term)
            if query_embedding:
                results = self.sql_repo.vector_search(query_embedding, limit=3)
                all_results.extend(results)
        
        return self._deduplicate_chunks(all_results)
    
    async def _search_for_examples(self, query: str, query_type: QueryType) -> List[Dict[str, Any]]:
        """Search specifically for code examples."""
        if query_type == QueryType.TERRAFORM:
            example_query = f"terraform {query} example configuration"
        else:
            example_query = f"{query} example code"
        
        query_embedding = await self.llm_service.get_embedding(example_query)
        if not query_embedding:
            return []
        
        results = self.sql_repo.vector_search(query_embedding, limit=5)
        
        # Filter for chunks that likely contain code
        code_chunks = []
        for result in results:
            text = result.get("chunk_text", "")
            if self._contains_code_indicators(text):
                code_chunks.append(result)
        
        return code_chunks
    
    async def _get_broader_context(self, current_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get broader context from the same documents as current chunks."""
        if not current_chunks:
            return []
        
        additional_chunks = []
        
        # For each current chunk, try to get neighboring chunks
        for chunk in current_chunks[:2]:  # Limit to top 2 chunks
            doc_id = chunk.get("doc_id")
            chunk_order = chunk.get("chunk_order", 0)
            
            if doc_id:
                # Get chunks before and after
                neighbors = self.sql_repo.get_document_chunks_range(
                    doc_id, 
                    max(0, chunk_order - 1), 
                    chunk_order + 2
                )
                additional_chunks.extend(neighbors)
        
        return self._deduplicate_chunks(additional_chunks)
    
    def _contains_code_indicators(self, text: str) -> bool:
        """Check if text contains code indicators."""
        code_indicators = [
            "```", "resource \"", "provider \"", "variable \"",
            "module \"", "data \"", "{", "}", "terraform {",
            "config {", "example:", "configuration:"
        ]
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in code_indicators)
    
    def _merge_chunks(self, existing_chunks: List[Dict[str, Any]], 
                     new_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge new chunks with existing ones, avoiding duplicates."""
        all_chunks = existing_chunks.copy()
        existing_ids = {chunk.get("chunk_id") for chunk in existing_chunks}
        
        for chunk in new_chunks:
            chunk_id = chunk.get("chunk_id")
            if chunk_id not in existing_ids:
                all_chunks.append(chunk)
                existing_ids.add(chunk_id)
        
        return all_chunks
    
    def _deduplicate_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate chunks based on chunk_id."""
        seen_ids = set()
        unique_chunks = []
        
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id")
            if chunk_id not in seen_ids:
                unique_chunks.append(chunk)
                seen_ids.add(chunk_id)
        
        return unique_chunks


class MultiHopAgent:
    """Agent that can perform multi-hop reasoning for complex queries."""
    
    def __init__(self, llm_service: LLMService, sql_repo: CloudSqlRepository):
        self.llm_service = llm_service
        self.sql_repo = sql_repo
    
    async def multi_hop_search(self, query: str) -> List[Dict[str, Any]]:
        """
        Perform multi-hop search by breaking down complex queries.
        """
        # Break down the query into sub-questions
        sub_queries = await self._decompose_query(query)
        
        all_results = []
        for sub_query in sub_queries:
            query_embedding = await self.llm_service.get_embedding(sub_query)
            if query_embedding:
                results = self.sql_repo.vector_search(query_embedding, limit=3)
                all_results.extend(results)
        
        # Deduplicate and rank results
        unique_results = self._deduplicate_and_rank(all_results, query)
        
        return unique_results[:10]  # Return top 10 results
    
    async def _decompose_query(self, query: str) -> List[str]:
        """Break down a complex query into simpler sub-queries."""
        decomposition_prompt = f"""Break down this complex query into 2-3 simpler, more specific questions that together would answer the original query.

Original Query: {query}

Return the sub-queries as a simple list, one per line:"""

        response = await self.llm_service.generate_answer(decomposition_prompt)
        
        # Extract lines that look like questions
        lines = [line.strip() for line in response.split('\n') if line.strip()]
        sub_queries = [line for line in lines if '?' in line or len(line) > 10]
        
        # Fallback to original query if decomposition fails
        return sub_queries if sub_queries else [query]
    
    def _deduplicate_and_rank(self, chunks: List[Dict[str, Any]], original_query: str) -> List[Dict[str, Any]]:
        """Deduplicate chunks and rank them by relevance."""
        seen_ids = set()
        unique_chunks = []
        
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id")
            if chunk_id not in seen_ids:
                unique_chunks.append(chunk)
                seen_ids.add(chunk_id)
        
        # Simple ranking by distance (lower is better)
        # In a more sophisticated system, you could re-rank based on original query
        return sorted(unique_chunks, key=lambda x: x.get("distance", float('inf'))) 