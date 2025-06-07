import logging
from functools import lru_cache
from typing import Generator, Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import firestore

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
from app.services.pocketflow_service import PocketFlowService


# Firestore client (removed unused import)

# Authentication dependencies
from .auth import verify_token, get_current_user_email

# Service Imports (removed missing RAG service)

settings = get_settings() # Get settings at module level

# --- Simplified Logging Utility ---
def log_error(message: str, exception: Exception = None):
    """Centralized error logging."""
    if exception:
        logging.error(f"{message}: {exception}", exc_info=True)
    else:
        logging.error(message)

# --- Security Scheme ---
security = HTTPBearer(auto_error=False)

# --- Authentication Dependency ---
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Dependency to verify JWT token and extract user information.
    Raises HTTPException if authentication fails.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Create a token credential object for verify_token
        from fastapi.security import HTTPAuthorizationCredentials
        token_creds = HTTPAuthorizationCredentials(
            scheme="Bearer", 
            credentials=credentials.credentials
        )
        # Verify the token and get user info
        user_info = await verify_token(token_creds)
        logging.debug(f"User authenticated: {user_info.get('email')}")
        return user_info
    except ValueError as ve:
        log_error("Token verification failed", ve)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {ve}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        log_error("Unexpected authentication error", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error"
        )

# --- RAG Service Dependency (removed) ---

# --- Firestore Repository Dependency (removed unused function) ---

# --- Firestore / Vertex / Pipeline Dependencies (Existing) ---

@lru_cache()
def get_repo() -> FirestoreRepository:
    """Provides a FirestoreRepository instance (now primarily for chats)."""
    logging.info("Initializing FirestoreRepository...")
    project_id = settings.gcp_project_id  # Ensure this is correctly set in your config
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


@lru_cache()
def get_pocketflow_service(
    sql_repo: CloudSqlRepository = Depends(get_cloudsql_repo),
) -> PocketFlowService:
    """Provides a PocketFlowService instance."""
    logging.info("Initializing PocketFlowService...")
    return PocketFlowService(sql_repo)

