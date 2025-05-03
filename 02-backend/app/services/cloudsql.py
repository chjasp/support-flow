import logging
import uuid
import datetime as dt
from typing import List, Dict, Any, Optional, Iterator
from contextlib import contextmanager
# Remove psycopg2 imports if only used for pool/errors previously
# import psycopg2
# from psycopg2.pool import SimpleConnectionPool
from google.cloud.sql.connector import Connector, IPTypes

# Import pg8000 exceptions if you want specific error handling
# from pg8000.native import DatabaseError

from app.models.domain import DocumentItem
from app.config import Settings # Import Settings

class CloudSqlRepository:
    """Repository for interacting with document data in Cloud SQL."""

    def __init__(self, connector: Connector, settings: Settings):
        self.connector = connector
        self.settings = settings
        logging.info("Cloud SQL Repository initialized with Connector.")

    @contextmanager
    def _get_conn(self) -> Iterator[Any]: # Return type depends on driver (pg8000 connection)
        """Gets a connection using the connector and ensures it's closed."""
        conn = None
        try:
            conn = self.connector.connect(
                self.settings.cloud_sql_instance,
                "pg8000", # Explicitly use pg8000 driver
                user=self.settings.cloud_sql_user,
                password=self.settings.cloud_sql_password,
                db=self.settings.cloud_sql_db,
                ip_type=IPTypes.PUBLIC, # Match processing service, adjust if needed (e.g., IPTypes.PUBLIC)
            )
            yield conn
        # Add specific exception handling for pg8000 if needed
        # except DatabaseError as db_err:
        #     logging.error(f"Cloud SQL Connection Error: {db_err}", exc_info=True)
        #     raise # Re-raise or handle appropriately
        except Exception as e:
            logging.error(f"Failed to connect to Cloud SQL: {e}", exc_info=True)
            raise # Re-raise the exception
        finally:
            if conn:
                conn.close()
                logging.debug("Cloud SQL connection closed.")
                
    def _to_pgvector(self, vec: List[float]) -> str:
        # keep it dense → smaller payload, less parsing time
        return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"

    def list_documents(self) -> List[DocumentItem]:
        """Lists all documents from the Cloud SQL database."""
        items = []
        cur = None # Initialize cursor variable
        try:
            # Use the context manager to get a connection
            with self._get_conn() as conn:
                try: # Add try block for cursor operations
                    cur = conn.cursor() # Create cursor
                    cur.execute(
                        """
                        SELECT id, filename, created_at, status, original_gcs, error_message
                        FROM documents
                        ORDER BY created_at DESC
                        """
                    )
                    results = cur.fetchall()
                finally: # Ensure cursor is closed
                    if cur:
                        cur.close()

                for row in results:
                    doc_id, filename, created_at, status, gcs_uri, error_msg = row

                    file_type_display = None
                    if filename and '.' in filename:
                        file_type_display = filename.split('.')[-1].upper()

                    # Determine display type based on common document extensions
                    if file_type_display in ["PDF", "DOCX", "TXT", "MD"]: # Added MD
                        display_type = "Document"
                    elif file_type_display: # If there's an extension but not recognized doc
                         display_type = f"{file_type_display} File"
                    else: # No extension
                        display_type = "Unknown"


                    items.append(DocumentItem(
                        id=str(doc_id),
                        name=filename or "Unknown Filename", # Handle potential None filename
                        type=display_type,
                        fileType=file_type_display,
                        dateAdded=created_at.isoformat() if isinstance(created_at, dt.datetime) else str(created_at),
                        status=status,
                        gcsUri=gcs_uri,
                        errorMessage=error_msg
                    ))
        # Catch potential connection errors or database errors from pg8000/connector
        except Exception as error: # Broad catch, refine if needed
            logging.error(f"Error listing documents from Cloud SQL: {error}", exc_info=True)
            raise # Re-raise for the endpoint handler to catch
        return items

    def delete_document(self, doc_id: str) -> None:
        """Deletes a document and its associated chunks (via CASCADE) from Cloud SQL."""
        try:
            doc_uuid = uuid.UUID(doc_id)
        except ValueError:
            logging.error(f"Invalid UUID format for deletion: {doc_id}")
            raise ValueError("Invalid document ID format.")

        cur = None # Initialize cursor variable
        try:
            # Use the context manager to get a connection
            with self._get_conn() as conn:
                try: # Add try block for cursor operations
                    cur = conn.cursor() # Create cursor
                    # Check if document exists
                    cur.execute("SELECT 1 FROM documents WHERE id = %s", (doc_uuid,))
                    if cur.fetchone() is None:
                         raise KeyError(f"Document with ID {doc_id} not found in Cloud SQL.")

                    # Delete the document (CASCADE should handle chunks)
                    cur.execute("DELETE FROM documents WHERE id = %s", (doc_uuid,))
                    logging.info(f"Attempting to delete document {doc_id} from Cloud SQL.")

                finally: # Ensure cursor is closed
                    if cur:
                        cur.close()

                # Commit the transaction *after* the cursor is closed
                conn.commit()
                logging.info(f"Successfully deleted document {doc_id} and committed transaction.")

        # Catch specific errors first
        except (KeyError, ValueError) as e:
             raise e
        # Catch potential connection errors or database errors from pg8000/connector
        except Exception as error: # Broad catch for others, refine if needed
            logging.error(f"Error deleting document {doc_id} from Cloud SQL: {error}", exc_info=True)
            # Rollback might be needed if commit fails or error occurs after cursor close but before commit
            # However, the connection context manager should handle closing on error,
            # which implicitly rolls back uncommitted transactions for most drivers.
            # If explicit rollback is desired on *any* exception during the operation:
            # try:
            #     if conn: conn.rollback()
            # except Exception as rb_err:
            #     logging.error(f"Error during rollback attempt for {doc_id}: {rb_err}")
            raise # Re-raise for the endpoint handler

    def vector_search(self, query_vector: List[float], limit: int) -> List[Dict[str, Any]]:
        """Performs vector similarity search on the chunks table."""
        results = []
        cur = None
        # Convert the Python list vector to the string format expected by pgvector/pg8000
        vector_string = self._to_pgvector(query_vector)

        sql = """
            SELECT
                c.id,
                c.doc_id,
                c.chunk_index,
                c.text,
                d.filename as doc_filename,
                c.embedding <=> %s::vector AS distance
            FROM chunks c
            JOIN documents d ON c.doc_id = d.id
            WHERE d.status = 'Ready' -- Only search ready documents
            ORDER BY distance ASC -- ASC because <=> is distance (smaller is better)
            LIMIT %s
        """
        try:
            with self._get_conn() as conn:
                try:
                    cur = conn.cursor()
                    cur.execute(sql, (vector_string, limit))
                    rows = cur.fetchall()
                    # Get column names from cursor description
                    colnames = [desc[0] for desc in cur.description]
                    for row in rows:
                        row_dict = dict(zip(colnames, row))
                        # Map to the keys expected by the Chunk model
                        results.append({
                            "chunk_id": str(row_dict.get("id")), # Convert DB int ID to string
                            "doc_id": str(row_dict.get("doc_id")), # Ensure UUID is string
                            "doc_filename": row_dict.get("doc_filename"),
                            "chunk_order": row_dict.get("chunk_index"), # Rename key from chunk_index
                            "chunk_text": row_dict.get("text"),
                            "summary": "", # Add required summary field (placeholder)
                            "distance": row_dict.get("distance") # Optional: for debugging/info
                        })
                    logging.info(f"Vector search found {len(results)} chunks for limit {limit}")
                finally:
                    if cur:
                        cur.close()
        except Exception as e:
            logging.error(f"Error during vector search: {e}", exc_info=True)
            # Don't return partial results on error, let the caller handle it
            raise
        return results
