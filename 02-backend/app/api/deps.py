import logging
from functools import lru_cache
from typing import Generator
from fastapi import Depends, HTTPException, status
import os
import google.auth
from google.oauth2 import service_account
from google.auth.transport.requests import Request

# Cloud SQL Connector
from google.cloud.sql.connector import Connector, IPTypes
# Remove psycopg2 pool import
# import psycopg2 # Keep if needed elsewhere, but not for pool
# from psycopg2.pool import SimpleConnectionPool # Remove this

from app.config import get_settings, Settings
from app.services.llm_service import LLMService
from app.services.firestore import FirestoreRepository
from app.services.pipeline import DocumentPipeline
from app.services.cloudsql import CloudSqlRepository
from app.services.gmail import GmailService

settings = get_settings() # Get settings at module level

# --- Firestore / Vertex / Pipeline Dependencies (Existing) ---

@lru_cache()
def get_repo() -> FirestoreRepository:
    """Provides a FirestoreRepository instance (now primarily for chats)."""
    logging.info("Initializing FirestoreRepository...")
    project_id = settings.gcp_project  # Ensure this is correctly set in your config
    return FirestoreRepository(project_id=project_id)

@lru_cache()
def get_llm_service() -> LLMService:
    """Provides an LLMService instance."""
    logging.info("Initializing LLMService...")
    return LLMService()

# --- Cloud SQL Dependencies (Refactored) ---

@lru_cache() # Cache the connector instance
def get_connector() -> Connector:
    """Initializes and provides a Cloud SQL Connector instance."""
    logging.info("Initializing Cloud SQL Connector...")
    # Consider adding connector options like enable_iam_auth if needed later
    return Connector()

# Renamed function to avoid conflict if you had an old get_sql_repo
@lru_cache() # Cache the repository instance as well
def get_cloudsql_repo(connector: Connector = Depends(get_connector)) -> CloudSqlRepository:
    """Provides a CloudSqlRepository instance, injecting the Connector."""
    # Pass the connector and settings needed for connection details
    logging.info("Initializing CloudSqlRepository...")
    return CloudSqlRepository(connector=connector, settings=settings)


# --- Pipeline Dependency (Updated) ---

def get_pipeline(
    repo: FirestoreRepository = Depends(get_repo),
    llm_service: LLMService = Depends(get_llm_service),
    sql_repo: CloudSqlRepository = Depends(get_cloudsql_repo), # Inject CloudSqlRepository
) -> DocumentPipeline:
    """Provides a DocumentPipeline instance with necessary repositories."""
    # Pass all required dependencies to the constructor
    return DocumentPipeline(settings=settings, repo=repo, llm_service=llm_service, sql_repo=sql_repo)


# --- Gmail Service Dependency (Updated) ---
def get_gmail_service(settings: Settings = Depends(get_settings)) -> GmailService:
    """Provides a GmailService instance using configured settings."""
    try:
        # GmailService now handles its own credential building using settings
        service = GmailService(settings=settings)
        # Check if the service was built successfully within the class
        if not service.service:
             raise ConnectionError("Gmail service object could not be built within GmailService class.")
        logging.info("GmailService instance created successfully via dependency.")
        return service

    except ConnectionError as ce: # Catch specific connection errors raised during build
        logging.error(f"Failed to initialize GmailService (ConnectionError): {ce}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not connect to Gmail: {ce}"
        )
    except Exception as e:
        logging.error(f"Failed to initialize GmailService (General Error): {e}", exc_info=True)
        # Raise a specific error to indicate initialization failure
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not initialize Gmail service: {e}"
        )
