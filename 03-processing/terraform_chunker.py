"""
Specialized chunking for Terraform documentation.
Preserves resource blocks, examples, and structured documentation.
"""

import re
import logging
from typing import List, Dict, Any, Tuple
import tiktoken

# Initialize tokenizer
tokenizer = tiktoken.get_encoding("cl100k_base")

class TerraformDocumentChunker:
    """Specialized chunker for Terraform documentation."""
    
    def __init__(self, max_tokens: int = 1000, overlap: int = 100):
        self.max_tokens = max_tokens
        self.overlap = overlap
        
    def chunk_terraform_doc(self, text: str, doc_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Chunk Terraform documentation with structure preservation.
        Returns list of enriched chunks with metadata.
        """
        filename = doc_metadata.get("filename", "").lower()
        
        if self._is_terraform_doc(filename, text):
            return self._chunk_terraform_content(text, doc_metadata)
        else:
            # Fall back to standard chunking for non-Terraform docs
            return self._standard_chunking(text, doc_metadata)
    
    def _is_terraform_doc(self, filename: str, text: str) -> bool:
        """Determine if this is Terraform documentation."""
        terraform_indicators = [
            "terraform", "provider", ".tf", "hcl",
            "resource \"", "data \"", "variable \"", "output \"",
            "module \"", "terraform {"
        ]
        
        return (any(indicator in filename for indicator in terraform_indicators) or
                any(indicator in text[:2000].lower() for indicator in terraform_indicators))
    
    def _chunk_terraform_content(self, text: str, doc_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Chunk Terraform content with structure awareness."""
        chunks = []
        
        # First, try to extract resource blocks
        resource_chunks = self._extract_resource_blocks(text)
        
        # If we found structured content, use it
        if resource_chunks:
            logging.info(f"Found {len(resource_chunks)} resource blocks")
            
            for i, chunk_data in enumerate(resource_chunks):
                # Enhance each chunk with metadata
                enriched_chunk = {
                    **chunk_data,
                    "chunk_index": i,
                    "doc_metadata": doc_metadata,
                    "chunk_type": "terraform_resource"
                }
                chunks.append(enriched_chunk)
        
        # Handle remaining text (intro, general docs, etc.)
        remaining_text = self._get_remaining_text(text, resource_chunks)
        if remaining_text:
            standard_chunks = self._standard_chunking(remaining_text, doc_metadata)
            
            # Adjust indices and add to main chunks
            start_idx = len(chunks)
            for i, chunk in enumerate(standard_chunks):
                chunk["chunk_index"] = start_idx + i
                chunk["chunk_type"] = "terraform_general"
                chunks.append(chunk)
        
        return chunks
    
    def _extract_resource_blocks(self, text: str) -> List[Dict[str, Any]]:
        """Extract individual resource/provider/module blocks."""
        blocks = []
        
        # Patterns for different Terraform block types
        block_patterns = [
            (r'resource\s+"([^"]+)"\s+"([^"]+)"\s*{', "resource"),
            (r'data\s+"([^"]+)"\s+"([^"]+)"\s*{', "data"),
            (r'provider\s+"([^"]+)"\s*{', "provider"),
            (r'module\s+"([^"]+)"\s*{', "module"),
            (r'variable\s+"([^"]+)"\s*{', "variable"),
            (r'output\s+"([^"]+)"\s*{', "output"),
        ]
        
        for pattern, block_type in block_patterns:
            blocks.extend(self._extract_blocks_by_pattern(text, pattern, block_type))
        
        return blocks
    
    def _extract_blocks_by_pattern(self, text: str, pattern: str, block_type: str) -> List[Dict[str, Any]]:
        """Extract blocks matching a specific pattern."""
        blocks = []
        
        for match in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
            start_pos = match.start()
            
            # Find the complete block (handle nested braces)
            block_text = self._extract_complete_block(text, start_pos)
            
            if block_text and len(tokenizer.encode(block_text)) <= self.max_tokens:
                # Extract resource type and name if available
                groups = match.groups()
                resource_type = groups[0] if len(groups) > 0 else None
                resource_name = groups[1] if len(groups) > 1 else None
                
                blocks.append({
                    "text": block_text,
                    "block_type": block_type,
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "start_position": start_pos
                })
        
        # Sort by position to maintain document order
        return sorted(blocks, key=lambda x: x["start_position"])
    
    def _extract_complete_block(self, text: str, start_pos: int) -> str:
        """Extract a complete block by matching braces."""
        brace_count = 0
        i = start_pos
        block_start = start_pos
        
        # Find the opening brace
        while i < len(text) and text[i] != '{':
            i += 1
        
        if i >= len(text):
            return ""
        
        # Count braces to find block end
        while i < len(text):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    # Found the end of the block
                    return text[block_start:i+1]
            i += 1
        
        return ""  # Incomplete block
    
    def _get_remaining_text(self, original_text: str, extracted_blocks: List[Dict[str, Any]]) -> str:
        """Get text that wasn't included in extracted blocks."""
        if not extracted_blocks:
            return original_text
        
        # Create a list of (start, end) positions for extracted blocks
        block_positions = []
        for block in extracted_blocks:
            start = block["start_position"]
            end = start + len(block["text"])
            block_positions.append((start, end))
        
        # Sort by start position
        block_positions.sort()
        
        # Extract text between blocks
        remaining_parts = []
        last_end = 0
        
        for start, end in block_positions:
            if start > last_end:
                part = original_text[last_end:start].strip()
                if part:
                    remaining_parts.append(part)
            last_end = end
        
        # Add any remaining text after the last block
        if last_end < len(original_text):
            part = original_text[last_end:].strip()
            if part:
                remaining_parts.append(part)
        
        return "\n\n".join(remaining_parts)
    
    def _standard_chunking(self, text: str, doc_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Standard token-based chunking with overlap."""
        chunks = []
        tokens = tokenizer.encode(text)
        
        start = 0
        chunk_index = 0
        
        while start < len(tokens):
            end = min(start + self.max_tokens, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = tokenizer.decode(chunk_tokens)
            
            chunks.append({
                "text": chunk_text,
                "chunk_index": chunk_index,
                "doc_metadata": doc_metadata,
                "chunk_type": "standard"
            })
            
            if end == len(tokens):
                break
            
            start = end - self.overlap if self.overlap else end
            chunk_index += 1
        
        return chunks


class CodeExampleExtractor:
    """Extract and enrich code examples from documentation."""
    
    @staticmethod
    def extract_code_examples(text: str) -> List[Dict[str, Any]]:
        """Extract code blocks from markdown-style documentation."""
        examples = []
        
        # Pattern for fenced code blocks
        code_block_pattern = r'```(\w+)?\n(.*?)\n```'
        
        for match in re.finditer(code_block_pattern, text, re.DOTALL):
            language = match.group(1) or "unknown"
            code = match.group(2)
            
            if language.lower() in ["hcl", "terraform", "tf"] or CodeExampleExtractor._looks_like_terraform(code):
                examples.append({
                    "code": code,
                    "language": language,
                    "start_position": match.start(),
                    "is_terraform": True
                })
        
        return examples
    
    @staticmethod
    def _looks_like_terraform(code: str) -> bool:
        """Heuristic to determine if code looks like Terraform."""
        terraform_keywords = [
            "resource", "provider", "variable", "output", "module", "data",
            "terraform", "locals"
        ]
        
        code_lower = code.lower()
        keyword_count = sum(1 for keyword in terraform_keywords if keyword in code_lower)
        
        # If we find multiple Terraform keywords, it's likely Terraform code
        return keyword_count >= 2


# Integration function for the main processing pipeline
def chunk_with_terraform_awareness(text: str, doc_metadata: Dict[str, Any], 
                                 max_tokens: int = 1000, overlap: int = 100) -> List[str]:
    """
    Integration function that returns plain text chunks for compatibility
    with existing pipeline, but uses Terraform-aware chunking internally.
    """
    chunker = TerraformDocumentChunker(max_tokens, overlap)
    enriched_chunks = chunker.chunk_terraform_doc(text, doc_metadata)
    
    # Extract just the text for compatibility with existing pipeline
    return [chunk["text"] for chunk in enriched_chunks]


def should_use_terraform_chunking(filename: str, text_sample: str) -> bool:
    """
    Determine if a document should use Terraform-aware chunking.
    Can be called before processing to make chunking decisions.
    """
    chunker = TerraformDocumentChunker()
    return chunker._is_terraform_doc(filename.lower(), text_sample) 