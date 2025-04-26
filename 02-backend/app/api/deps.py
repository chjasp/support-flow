import logging
from functools import lru_cache
from typing import Generator
from fastapi import Depends
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
from app.services.vertex import VertexClient
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
    return FirestoreRepository()

@lru_cache()
def get_vertex() -> VertexClient:
    """Provides a VertexClient instance."""
    logging.info("Initializing VertexClient...")
    return VertexClient(project=settings.gcp_project, location=settings.gcp_location)

def get_pipeline(
    repo: FirestoreRepository = Depends(get_repo),
    vertex: VertexClient = Depends(get_vertex),
) -> DocumentPipeline:
    """Provides a DocumentPipeline instance."""
    return DocumentPipeline(settings=settings, repo=repo, vertex=vertex)


# --- Cloud SQL Dependencies (Refactored) ---

@lru_cache() # Cache the connector instance
def get_connector() -> Connector:
    """Initializes and provides a Cloud SQL Connector instance."""
    logging.info("Initializing Cloud SQL Connector...")
    # Consider adding connector options like enable_iam_auth if needed later
    return Connector()

def get_sql_repo(connector: Connector = Depends(get_connector)) -> CloudSqlRepository:
    """Provides a CloudSqlRepository instance, injecting the Connector."""
    # Pass the connector and settings needed for connection details
    return CloudSqlRepository(connector=connector, settings=settings)

# --- Gmail Service Dependency (Existing) ---
# (Keep the existing get_gmail_service function as is)
@lru_cache()
def get_gmail_service() -> GmailService:
    """Provides a GmailService instance using configured credentials."""
    logging.info("Initializing GmailService...")
    credentials = None
    scopes = ["https://www.googleapis.com/auth/gmail.readonly"] # Add other scopes like send, modify if needed

    try:
        # Priority 1: Service Account JSON with Impersonation
        if settings.google_service_account_json and os.path.exists(settings.google_service_account_json):
            if not settings.gmail_impersonate_email:
                raise ValueError("gmail_impersonate_email must be set when using google_service_account_json for Gmail.")
            credentials = service_account.Credentials.from_service_account_file(
                settings.google_service_account_json,
                scopes=scopes,
                subject=settings.gmail_impersonate_email
            )
            logging.info(f"Using Service Account JSON ({settings.google_service_account_json}) impersonating {settings.gmail_impersonate_email}")

        # Priority 2: Application Default Credentials (ADC) with Impersonation (Common in Cloud Run/Functions)
        elif settings.gmail_impersonate_email:
            adc_creds, _ = google.auth.default(scopes=scopes)
            credentials = adc_creds.with_subject(settings.gmail_impersonate_email)
            logging.info(f"Using Application Default Credentials impersonating {settings.gmail_impersonate_email}")

        # If neither impersonation nor SA key is set, raise error as direct ADC usually won't work for Gmail API access
        else:
            raise ValueError("Gmail API access requires configuration: set either 'google_service_account_json' or 'gmail_impersonate_email' (preferred with ADC).")

        # Optional: Refresh credentials if needed (good practice)
        if hasattr(credentials, 'refresh') and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                logging.info("Refreshed Gmail API credentials.")
            except Exception as refresh_error:
                logging.error(f"Failed to refresh Gmail credentials: {refresh_error}", exc_info=True)
                raise ConnectionError(f"Could not refresh Gmail credentials: {refresh_error}")


        return GmailService(credentials=credentials) # Assuming GmailService takes credentials directly

    except Exception as e:
        logging.error(f"Failed to initialize GmailService: {e}", exc_info=True)
        # Raise a specific error to indicate connection failure during startup/request
        raise ConnectionError(f"Could not initialize Gmail service: {e}")
