-- Migration: Add processing_tasks table for unified content processing
-- This table replaces the in-memory task tracking for URL and text processing

CREATE TABLE IF NOT EXISTS processing_tasks (
    task_id UUID PRIMARY KEY,
    task_type VARCHAR(50) NOT NULL, -- 'url_processing', 'text_processing', etc.
    status VARCHAR(20) NOT NULL DEFAULT 'queued', -- 'queued', 'processing', 'completed', 'failed'
    input_data JSONB NOT NULL, -- Store URLs, text content, or other input parameters
    result_data JSONB, -- Store processing results when completed
    error_message TEXT, -- Store error details when failed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Add constraints
    CONSTRAINT valid_task_type CHECK (task_type IN ('url_processing', 'text_processing', 'file_processing')),
    CONSTRAINT valid_status CHECK (status IN ('queued', 'processing', 'completed', 'failed'))
);

-- Add index for efficient querying
CREATE INDEX IF NOT EXISTS idx_processing_tasks_status ON processing_tasks(status);
CREATE INDEX IF NOT EXISTS idx_processing_tasks_created_at ON processing_tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_processing_tasks_task_type ON processing_tasks(task_type);

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_processing_tasks_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER processing_tasks_updated_at
    BEFORE UPDATE ON processing_tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_processing_tasks_updated_at(); 