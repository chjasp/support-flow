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
    gcs_generation BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'Processing' CHECK (status IN ('Processing', 'Ready', 'Failed')),
    error_message TEXT,
    CONSTRAINT unique_document_version UNIQUE (original_gcs, gcs_generation)
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

-- Create table for 3D reduced embeddings for visualization
CREATE TABLE IF NOT EXISTS chunks_3d (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER REFERENCES chunks(id) ON DELETE CASCADE,
    x REAL NOT NULL,
    y REAL NOT NULL,
    z REAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    reduction_method VARCHAR(20) DEFAULT 'umap' CHECK (reduction_method IN ('umap', 'tsne', 'pca')),
    UNIQUE (chunk_id, reduction_method)
);

-- Create index for faster 3D coordinate queries
CREATE INDEX IF NOT EXISTS idx_chunks_3d_coordinates ON chunks_3d (x, y, z);
CREATE INDEX IF NOT EXISTS idx_chunks_3d_chunk_id ON chunks_3d (chunk_id);