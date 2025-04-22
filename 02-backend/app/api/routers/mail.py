import logging
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_vertex # Assuming get_vertex exists in deps.py
from app.services.vertex import VertexClient
from app.models.domain import GenerateReplyRequest, GenerateReplyResponse

router = APIRouter(prefix="/api", tags=["mail"]) # Using /api prefix as in frontend

@router.post("/generate-reply", response_model=GenerateReplyResponse)
async def generate_email_reply(
    body: GenerateReplyRequest,
    vertex: VertexClient = Depends(get_vertex) # Inject VertexClient
):
    """
    Receives email content and generates a suggested reply using an LLM.
    """
    try:
        logging.info(f"Generating reply for email content: '{body.email_content[:100]}...'")

        # --- Construct the Prompt ---
        # This prompt guides the LLM to act as a helpful customer service agent.
        # You can customize this extensively based on your specific needs,
        # desired tone, and available context.
        prompt = f"""
        You are a helpful and professional customer service assistant.
        A customer sent the following email:

        --- EMAIL START ---
        {body.email_content}
        --- EMAIL END ---

        Draft a polite and helpful reply to this email. Address the customer's query or concern directly.
        Keep the tone professional and empathetic. Do not add a subject line or signature, only provide the body of the reply.
        """

        # --- Generate Reply using Vertex AI ---
        generated_reply = await vertex.generate_answer(prompt) # Use the existing generate_answer method

        logging.info(f"Generated reply: '{generated_reply[:100]}...'")

        return GenerateReplyResponse(reply=generated_reply)

    except Exception as e:
        logging.error(f"Error generating email reply: {e}", exc_info=True)
        # Provide a more generic error to the client for security
        raise HTTPException(status_code=500, detail="Failed to generate email reply.")
