import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Literal
from enum import Enum

from .llm_service import LLMService
from .firestore import FirestoreRepository
from .cloudsql import CloudSqlRepository
from app.config import get_settings, Settings
from .rag_agent import RAGAgent

class QueryType(Enum):
    """Types of queries that require different retrieval strategies."""
    CODE_GENERATION = "code_generation"
    TERRAFORM = "terraform"
    DOCUMENTATION_LOOKUP = "documentation"
    GENERAL_QA = "general_qa"
    TROUBLESHOOTING = "troubleshooting"

class DocumentType(Enum):
    """Types of documents that may need special handling."""
    TERRAFORM_DOCS = "terraform_docs"
    API_REFERENCE = "api_reference"
    CODE_EXAMPLES = "code_examples"
    GENERAL_DOCS = "general_docs"
    PDF_DOCUMENT = "pdf_document"

class EnhancedDocumentPipeline:
    """Enhanced RAG pipeline with multiple retrieval strategies."""

    def __init__(self,
                 settings: Settings,
                 repo: FirestoreRepository,
                 llm_service: LLMService,
                 sql_repo: CloudSqlRepository) -> None:
        self.settings = settings
        self.repo = repo
        self.llm_service = llm_service
        self.sql_repo = sql_repo
        
        # Initialize the RAG agent
        self.rag_agent = RAGAgent(llm_service, sql_repo)

    # ------------------------------------------------------------------ #
    # Query Classification
    # ------------------------------------------------------------------ #
    
    async def classify_query(self, query: str) -> QueryType:
        """Classify the query to determine the best retrieval strategy."""
        query_lower = query.lower()
        
        # Terraform-specific patterns
        terraform_patterns = [
            r'terraform', r'\.tf\b', r'resource\s+"', r'provider\s+"',
            r'variable\s+"', r'output\s+"', r'module\s+"', r'data\s+"',
            r'aws_\w+', r'google_\w+', r'azurerm_\w+', r'hcl\b'
        ]
        
        # Code generation patterns
        code_patterns = [
            r'create\s+\w+\s+resource', r'generate\s+code', r'write\s+\w+\s+for',
            r'how\s+to\s+create', r'example\s+of\s+\w+\s+resource',
            r'configuration\s+for', r'syntax\s+for'
        ]
        
        # Check for Terraform
        if any(re.search(pattern, query_lower) for pattern in terraform_patterns):
            return QueryType.TERRAFORM
            
        # Check for code generation intent
        if any(re.search(pattern, query_lower) for pattern in code_patterns):
            return QueryType.CODE_GENERATION
            
        # Documentation lookup patterns
        doc_patterns = [
            r'what\s+is', r'explain', r'describe', r'definition\s+of',
            r'documentation\s+for', r'reference\s+for'
        ]
        
        if any(re.search(pattern, query_lower) for pattern in doc_patterns):
            return QueryType.DOCUMENTATION_LOOKUP
            
        return QueryType.GENERAL_QA

    def classify_document_by_metadata(self, doc_metadata: Dict[str, Any]) -> DocumentType:
        """Classify document type based on metadata."""
        filename = doc_metadata.get("doc_filename", "").lower()
        gcs_uri = doc_metadata.get("gcs_uri", "").lower()
        
        if any(term in filename for term in ["terraform", "provider", ".tf"]):
            return DocumentType.TERRAFORM_DOCS
        elif any(term in filename for term in ["api", "reference", "spec"]):
            return DocumentType.API_REFERENCE
        elif filename.endswith('.pdf'):
            return DocumentType.PDF_DOCUMENT
        else:
            return DocumentType.GENERAL_DOCS

    # ------------------------------------------------------------------ #
    # Enhanced Retrieval Strategies
    # ------------------------------------------------------------------ #

    async def hybrid_search_enhanced(self, query: str) -> List[Dict[str, Any]]:
        """Enhanced search that uses different strategies based on query type."""
        query_type = await self.classify_query(query)
        
        logging.info(f"Classified query as: {query_type.value}")
        
        # Get initial retrieval results
        if query_type == QueryType.TERRAFORM:
            initial_chunks = await self._terraform_retrieval(query)
        elif query_type == QueryType.CODE_GENERATION:
            initial_chunks = await self._code_generation_retrieval(query)
        elif query_type == QueryType.DOCUMENTATION_LOOKUP:
            initial_chunks = await self._documentation_retrieval(query)
        else:
            initial_chunks = await self._general_retrieval(query)

        # Use RAG agent to improve results for code-related queries
        if query_type in [QueryType.TERRAFORM, QueryType.CODE_GENERATION] and initial_chunks:
            logging.info("Using RAG agent to improve retrieval results")
            improved_chunks = await self.rag_agent.improved_retrieval(query, initial_chunks, query_type)
            return improved_chunks
        
        return initial_chunks

    async def _terraform_retrieval(self, query: str) -> List[Dict[str, Any]]:
        """Specialized retrieval for Terraform queries."""
        logging.info("Using Terraform-specialized retrieval")
        
        # Extract resource type if mentioned
        resource_match = re.search(r'(aws|google|azurerm)_(\w+)', query.lower())
        
        if resource_match:
            provider = resource_match.group(1)
            resource_type = resource_match.group(2)
            
            # First, try to find exact resource documentation
            exact_chunks = await self._search_for_resource_docs(provider, resource_type)
            
            if exact_chunks:
                logging.info(f"Found {len(exact_chunks)} exact resource docs for {provider}_{resource_type}")
                # Get related chunks (same resource, different sections)
                related_chunks = await self._get_related_resource_chunks(exact_chunks[0], limit=3)
                
                # Combine and deduplicate
                all_chunks = exact_chunks + related_chunks
                seen_ids = set()
                unique_chunks = []
                for chunk in all_chunks:
                    chunk_id = chunk.get("chunk_id")
                    if chunk_id not in seen_ids:
                        unique_chunks.append(chunk)
                        seen_ids.add(chunk_id)
                
                return unique_chunks[:self.settings.max_context_chunks]
        
        # Fallback to enhanced vector search with Terraform document prioritization
        return await self._prioritized_vector_search(query, [DocumentType.TERRAFORM_DOCS])

    async def _code_generation_retrieval(self, query: str) -> List[Dict[str, Any]]:
        """Specialized retrieval for code generation queries."""
        logging.info("Using code generation retrieval strategy")
        
        # Get both examples and documentation
        example_chunks = await self._search_for_examples(query, limit=3)
        doc_chunks = await self._prioritized_vector_search(
            query, 
            [DocumentType.TERRAFORM_DOCS, DocumentType.API_REFERENCE],
            limit=4
        )
        
        # Prioritize examples first, then documentation
        return example_chunks + doc_chunks

    async def _documentation_retrieval(self, query: str) -> List[Dict[str, Any]]:
        """Retrieval focused on finding comprehensive documentation."""
        logging.info("Using documentation-focused retrieval")
        
        # Use larger chunks and get more context
        return await self._get_comprehensive_context(query)

    async def _general_retrieval(self, query: str) -> List[Dict[str, Any]]:
        """Standard vector search for general queries."""
        logging.info("Using standard vector search")
        
        query_embedding = await self.llm_service.get_embedding(query)
        if not query_embedding:
            return []
        
        return self.sql_repo.vector_search(query_embedding, self.settings.max_context_chunks)

    # ------------------------------------------------------------------ #
    # Specialized Search Methods
    # ------------------------------------------------------------------ #

    async def _search_for_resource_docs(self, provider: str, resource_type: str) -> List[Dict[str, Any]]:
        """Search for specific Terraform resource documentation."""
        # This would need to be implemented based on how you store your Terraform docs
        # For now, using keyword search as an example
        
        search_terms = [
            f"{provider}_{resource_type}",
            f"resource \"{provider}_{resource_type}\"",
            f"{resource_type} resource"
        ]
        
        # Use a combination of vector search and keyword matching
        all_results = []
        for term in search_terms:
            query_embedding = await self.llm_service.get_embedding(term)
            if query_embedding:
                results = self.sql_repo.vector_search(query_embedding, limit=5)
                # Filter for Terraform docs
                filtered = [r for r in results if self._is_terraform_doc(r)]
                all_results.extend(filtered)
        
        # Deduplicate and return top results
        seen_ids = set()
        unique_results = []
        for result in all_results:
            chunk_id = result.get("chunk_id")
            if chunk_id not in seen_ids:
                unique_results.append(result)
                seen_ids.add(chunk_id)
        
        return unique_results[:3]

    async def _get_related_resource_chunks(self, base_chunk: Dict[str, Any], limit: int = 3) -> List[Dict[str, Any]]:
        """Get chunks related to a specific resource (same document, nearby chunks)."""
        doc_id = base_chunk.get("doc_id")
        chunk_order = base_chunk.get("chunk_order", 0)
        
        if not doc_id:
            return []
        
        # Get nearby chunks from the same document
        return self.sql_repo.get_document_chunks_range(
            doc_id, 
            start_index=max(0, chunk_order - 2), 
            end_index=chunk_order + limit + 2
        )

    async def _search_for_examples(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Search specifically for code examples."""
        # Look for chunks that contain code patterns
        example_query = f"example {query} code configuration"
        query_embedding = await self.llm_service.get_embedding(example_query)
        
        if not query_embedding:
            return []
        
        results = self.sql_repo.vector_search(query_embedding, limit * 2)
        
        # Filter for chunks that likely contain code
        code_chunks = []
        for result in results:
            text = result.get("chunk_text", "")
            if self._contains_code(text):
                code_chunks.append(result)
        
        return code_chunks[:limit]

    async def _prioritized_vector_search(self, query: str, 
                                       preferred_doc_types: List[DocumentType], 
                                       limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Vector search that prioritizes certain document types."""
        if limit is None:
            limit = self.settings.max_context_chunks
        
        query_embedding = await self.llm_service.get_embedding(query)
        if not query_embedding:
            return []
        
        # Get more results than needed to allow for filtering
        results = self.sql_repo.vector_search(query_embedding, limit * 3)
        
        # Separate preferred and other results
        preferred = []
        others = []
        
        for result in results:
            doc_type = self.classify_document_by_metadata(result)
            if doc_type in preferred_doc_types:
                preferred.append(result)
            else:
                others.append(result)
        
        # Return preferred first, then others to fill remaining slots
        combined = preferred + others
        return combined[:limit]

    async def _get_comprehensive_context(self, query: str) -> List[Dict[str, Any]]:
        """Get comprehensive context by retrieving multiple related chunks."""
        query_embedding = await self.llm_service.get_embedding(query)
        if not query_embedding:
            return []
        
        # Get initial results
        initial_results = self.sql_repo.vector_search(query_embedding, 5)
        
        if not initial_results:
            return []
        
        # For the top result, get additional context from the same document
        top_result = initial_results[0]
        additional_context = await self._get_related_resource_chunks(top_result, limit=3)
        
        # Combine and deduplicate
        all_chunks = initial_results + additional_context
        seen_ids = set()
        unique_chunks = []
        for chunk in all_chunks:
            chunk_id = chunk.get("chunk_id")
            if chunk_id not in seen_ids:
                unique_chunks.append(chunk)
                seen_ids.add(chunk_id)
        
        return unique_chunks[:self.settings.max_context_chunks]

    # ------------------------------------------------------------------ #
    # Helper Methods
    # ------------------------------------------------------------------ #

    def _is_terraform_doc(self, chunk: Dict[str, Any]) -> bool:
        """Check if a chunk is from Terraform documentation."""
        text = chunk.get("chunk_text", "").lower()
        filename = chunk.get("doc_filename", "").lower()
        
        terraform_indicators = [
            "terraform", "provider", "resource", "variable", "output",
            "module", "data source", ".tf", "hcl"
        ]
        
        return (any(indicator in filename for indicator in terraform_indicators) or
                any(indicator in text for indicator in terraform_indicators))

    def _contains_code(self, text: str) -> bool:
        """Check if text contains code blocks or configuration."""
        code_indicators = [
            "resource \"", "provider \"", "variable \"", "output \"",
            "module \"", "data \"", "terraform {", "```", 
            "resource {", "config {", "{", "}"
        ]
        
        return any(indicator in text for indicator in code_indicators)

    # ------------------------------------------------------------------ #
    # Enhanced Answer Generation
    # ------------------------------------------------------------------ #

    async def answer_enhanced(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """Enhanced answer generation with query-type specific prompts."""
        if not context_chunks:
            return await self._fallback_answer(query)
        
        query_type = await self.classify_query(query)
        
        if query_type == QueryType.TERRAFORM:
            return await self._generate_terraform_answer(query, context_chunks)
        elif query_type == QueryType.CODE_GENERATION:
            return await self._generate_code_answer(query, context_chunks)
        else:
            return await self._generate_standard_answer(query, context_chunks)

    async def _generate_terraform_answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """Generate Terraform-specific answers with proper code formatting."""
        # Separate code examples from documentation
        code_chunks = [c for c in context_chunks if self._contains_code(c.get("chunk_text", ""))]
        doc_chunks = [c for c in context_chunks if not self._contains_code(c.get("chunk_text", ""))]
        
        code_context = "\n---\n".join([c.get("chunk_text", "") for c in code_chunks])
        doc_context = "\n---\n".join([c.get("chunk_text", "") for c in doc_chunks])
        
        prompt = f"""You are a Terraform expert. Answer the user's question using the provided documentation and code examples.

IMPORTANT GUIDELINES:
1. Provide complete, valid Terraform configuration
2. Include all required arguments for resources
3. Use the exact syntax from the documentation
4. Explain what each block does
5. If showing code, format it properly with ```hcl blocks

Code Examples:
{code_context}

Documentation:
{doc_context}

Question: {query}

Provide a complete answer with working Terraform configuration:"""

        return await self.llm_service.generate_answer(prompt)

    async def _generate_code_answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """Generate code-focused answers."""
        ctx = "\n---\n".join([c.get("chunk_text", "") for c in context_chunks if c.get("chunk_text")])
        
        prompt = f"""Answer the user's code-related question using the provided documentation.

GUIDELINES:
1. Provide working, complete code examples
2. Explain the code clearly
3. Use proper formatting with code blocks
4. Include any necessary imports or dependencies
5. Mention any prerequisites or setup required

Documentation:
{ctx}

Question: {query}

Answer with complete code examples:"""

        return await self.llm_service.generate_answer(prompt)

    async def _generate_standard_answer(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """Standard answer generation."""
        ctx = "\n---\n".join([c.get("chunk_text", "") for c in context_chunks if c.get("chunk_text")])
        
        prompt = f"""Answer the user's question based on the provided context.

Context:
{ctx}

Question: {query}

Answer (Markdown):"""

        return await self.llm_service.generate_answer(prompt)

    async def _fallback_answer(self, query: str) -> str:
        """Fallback when no context is available."""
        query_type = await self.classify_query(query)
        
        if query_type in [QueryType.TERRAFORM, QueryType.CODE_GENERATION]:
            return ("I don't have access to the specific documentation needed to provide "
                   "accurate code examples for your question. Please check the official "
                   "documentation or add the relevant documentation to your knowledge base.")
        else:
            prompt = f"Answer the question using general knowledge.\n\nQuestion: {query}\n\nAnswer:"
            return await self.llm_service.generate_answer(prompt) 