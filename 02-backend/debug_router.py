"""
Debug router for testing URL processing without authentication
"""

import logging
import json
from fastapi import APIRouter, Request
from app.api.routers.web_processing import UrlProcessRequest

debug_router = APIRouter(
    prefix="/debug",
    tags=["debug"]
)

@debug_router.post("/test-url-validation")
async def test_url_validation(request: Request):
    """Debug endpoint to test URL validation without authentication"""
    try:
        body = await request.body()
        headers = dict(request.headers)
        
        logging.info(f"DEBUG: Raw body: {body}")
        logging.info(f"DEBUG: Headers: {headers}")
        logging.info(f"DEBUG: Content-Type: {request.headers.get('content-type')}")
        
        if body:
            try:
                json_data = json.loads(body)
                logging.info(f"DEBUG: Parsed JSON: {json_data}")
                
                # Try to create UrlProcessRequest from the JSON
                url_request = UrlProcessRequest(**json_data)
                logging.info(f"DEBUG: Pydantic validation succeeded: {url_request}")
                
                return {
                    "status": "success", 
                    "parsed_data": json_data, 
                    "validated": True,
                    "validated_urls": [str(url) for url in url_request.urls]
                }
            except json.JSONDecodeError as e:
                logging.error(f"DEBUG: JSON decode error: {e}")
                return {"status": "error", "error": f"JSON decode error: {e}"}
            except Exception as e:
                logging.error(f"DEBUG: Pydantic validation error: {e}")
                import traceback
                traceback.print_exc()
                return {"status": "error", "error": f"Validation error: {e}"}
        else:
            return {"status": "error", "error": "No body received"}
            
    except Exception as e:
        logging.error(f"DEBUG: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": f"Unexpected error: {e}"} 