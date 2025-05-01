import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.config import get_settings, Settings

# Reusable HTTPBearer instance
oauth2_scheme = HTTPBearer()

async def verify_token(
    token: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings)
) -> dict:
    """
    Verifies the Google ID token provided in the Authorization header.

    Args:
        token: The bearer token credential.
        settings: Application settings containing the audience client ID.

    Returns:
        The decoded token payload if valid.

    Raises:
        HTTPException: 401 if token is invalid, expired, or has wrong audience.
                       403 if Authorization header is missing or malformed.
    """
    if token is None:
        logging.warning("Authorization header missing")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authenticated: Authorization header missing",
        )

    credentials = token.credentials # This is the actual token string

    try:
        # Verify the token against Google's public keys
        # Specify the CLIENT_ID of the frontend app that obtained the token
        idinfo = id_token.verify_oauth2_token(
            credentials,
            google_requests.Request(),
            settings.auth_google_client_id # Crucial: Verify the audience
        )

        # --- Optional: Add more checks if needed ---
        # Example: Check if the issuer is Google
        # if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
        #     raise ValueError('Wrong issuer.')

        # Example: Check if the user's email domain is allowed (if applicable)
        # allowed_domains = ["yourcompany.com"]
        # if idinfo.get('hd') not in allowed_domains:
        #      raise ValueError('Unauthorized domain.')

        logging.debug(f"Token verified successfully for email: {idinfo.get('email')}")
        return idinfo # Return the decoded payload (user info)

    except ValueError as e:
        # This catches invalid token format, signature, expiry, audience mismatch, etc.
        logging.error(f"Token verification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        # Catch any other unexpected errors during verification
        logging.error(f"Unexpected error during token verification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not process authentication token",
        )

# Optional: Dependency to get just the user email easily
async def get_current_user_email(
    user_info: dict = Depends(verify_token)
) -> str:
    """Extracts user email from verified token payload."""
    email = user_info.get("email")
    if not email:
         logging.error("Email not found in verified token payload.")
         raise HTTPException(
             status_code=status.HTTP_401_UNAUTHORIZED,
             detail="Could not identify user from token.",
         )
    return email 