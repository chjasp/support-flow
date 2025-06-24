"""Authentication helpers (Google OAuth).

This module exposes a single dependency `get_current_user` for FastAPI
routes that validates a Google ID token passed via the Authorization
header (Bearer)."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from .settings import settings

security = HTTPBearer()
_request_adapter = google_requests.Request()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Validate the incoming bearer token and return a lightweight user dict."""

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    try:
        claims = id_token.verify_oauth2_token(
            credentials.credentials, _request_adapter, settings.google_client_id
        )
        return {"user_id": claims["email"], "email": claims["email"]}
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") 