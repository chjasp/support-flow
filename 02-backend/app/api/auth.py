import logging
from fastapi import Depends, HTTPException, Request, status
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.config import get_settings, Settings


async def verify_token(
    request: Request,
    settings: Settings = Depends(get_settings)
) -> dict:
    """
    Verifies the Google ID token provided by the frontend. The user token is
    expected in the ``X-User-Authorization`` header and falls back to the
    standard ``Authorization`` header.

    Args:
        request: The incoming HTTP request.
        settings: Application settings containing the audience client ID.

    Returns:
        The decoded token payload if valid.

    Raises:
        HTTPException: 401 if token is invalid, expired, or has wrong audience.
                       403 if Authorization header is missing or malformed.
    """
    # Look for the user token in the custom header first and then fall back to
    # the standard Authorization header.
    auth_header = request.headers.get("x-user-authorization") or request.headers.get("authorization")

    if not auth_header:
        logging.warning("User authorization header missing")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authenticated: Authorization header missing",
        )

    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authorization header format",
        )

    credentials = auth_header.split(" ", 1)[1]

    try:
        # Verify the token against Google's public keys
        # Specify the CLIENT_ID of the frontend app that obtained the token
        idinfo = id_token.verify_oauth2_token(
            credentials,
            google_requests.Request(),
            settings.auth_google_client_id # Crucial: Verify the audience
        )

        logging.debug(f"Token verified successfully for email: {idinfo.get('email')}")
        return idinfo # Return the decoded payload (user info)

    except ValueError as e:
        # This catches invalid token format, signature, expiry, audience mismatch, etc.
        logging.error(f"Token verification failed: {e}", exc_info=True)
        message = str(e)
        if "Token expired" in message:
            detail = "Token expired. Please sign in again."
        else:
            detail = f"Invalid authentication credentials: {message}"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        # Catch any other unexpected errors during verification
        logging.error(f"Unexpected error during token verification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not process authentication token",
        )