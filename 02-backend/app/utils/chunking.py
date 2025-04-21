from typing import List

def split(text: str, chunk_size: int = 10_000, overlap: int = 500) -> List[str]:
    """Smart whitespace‑aware text chunker."""
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")

    chunks: List[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        ideal_end = start + chunk_size
        if ideal_end >= text_len:
            actual_end = text_len
        else:
            window_start = max(start, ideal_end - chunk_size // 2)
            last_space = text.rfind(' ', window_start, ideal_end)
            last_nl = text.rfind('\n', window_start, ideal_end)
            split_pos = max(last_space, last_nl)
            actual_end = split_pos + 1 if split_pos > start else ideal_end

        chunk = text[start:actual_end]
        if chunk.strip():
            chunks.append(chunk)

        start = start + chunk_size - overlap
        if start >= text_len or actual_end == start:
            break
    return chunks
