import logging
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_vertex # Assuming get_vertex exists in deps.py
from app.services.vertex import VertexClient
from app.models.domain import (
    GenerateReplyRequest,
    GenerateReplyResponse,
    RefineReplyRequest,
    RefineReplyResponse
)

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


# --- New Refinement Endpoint ---
@router.post("/refine-reply", response_model=RefineReplyResponse)
async def refine_email_reply(
    body: RefineReplyRequest,
    vertex: VertexClient = Depends(get_vertex)
):
    """
    Receives original email, current draft, and an instruction,
    then refines the draft using an LLM.
    """
    try:
        logging.info(f"Refining reply draft based on instruction: '{body.instruction}'")

        # --- Construct the Prompt for Refinement ---
        # This prompt needs to provide all necessary context to the LLM.
        prompt = f"""
        You are editing an email reply draft.
        Here is the original email received:

        --- ORIGINAL EMAIL START ---
        {body.email_content}
        --- ORIGINAL EMAIL END ---

        Here is the current draft of the reply:

        --- CURRENT DRAFT START ---
        {body.current_draft}
        --- CURRENT DRAFT END ---

        Please refine the current draft based on the following instruction:
        Instruction: "{body.instruction}"

        Output only the refined reply body, without any extra explanations, preamble, or signature.
        Ensure the refined reply still appropriately addresses the original email.
        """

        # --- Generate Refined Reply using Vertex AI ---
        refined_reply_text = await vertex.generate_answer(prompt)

        logging.info(f"Refined reply: '{refined_reply_text[:100]}...'")

        return RefineReplyResponse(refined_reply=refined_reply_text)

    except Exception as e:
        logging.error(f"Error refining email reply: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to refine email reply.")
