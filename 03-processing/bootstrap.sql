-- Connect to the 'docs' database first
\c docs;

-- Enable the pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create the documents table (adjust types/constraints as needed)
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY,
    filename TEXT NOT NULL,
    original_gcs TEXT,
    processed_gcs TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create the chunks table (adjust vector dimensions)
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY, -- Or use UUID
    doc_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT,
    embedding vector(768), -- Adjust 768 to match your embedding model's dimensions (text-embedding-004 is 768)
    UNIQUE (doc_id, chunk_index)
);