import logging
from fastapi import APIRouter, Depends, HTTPException, Body, Path, status
from typing import List, Optional
import datetime as _dt

from app.api.deps import get_vertex, get_repo, get_gmail_service
from app.services.vertex import VertexClient
from app.services.firestore import FirestoreRepository
from app.services.gmail import GmailService
from app.models.domain import (
    GenerateReplyRequest,
    GenerateReplyResponse,
    RefineReplyRequest,
    RefineReplyResponse,
    ChatMessage,
    AddRefinementMessageRequest,
    EmailInteractionResponse,
    UpdateDraftRequest,
    EmailMetadata,
    EmailBodyResponse,
    BaseModel
)

router = APIRouter(prefix="/api", tags=["mail"]) # Using /api prefix as in frontend

# --- Pydantic Models for Interaction Data ---
class EmailInteractionResponse(BaseModel):
    id: str
    replyDraft: Optional[str] = ""
    refinementHistory: List[ChatMessage] = []
    # lastUpdated: Optional[datetime] = None # Optional: include if needed by frontend

class UpdateDraftRequest(BaseModel):
    draft: str

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


# --- New Endpoints for Email Interaction Persistence ---

@router.get("/mail/interactions/{email_id}", response_model=EmailInteractionResponse)
async def get_email_interaction_data(
    email_id: str = Path(..., description="The ID of the email"),
    repo: FirestoreRepository = Depends(get_repo)
):
    """Retrieves the saved reply draft and refinement history for an email."""
    try:
        interaction_data = repo.get_email_interaction(email_id)
        # The repository method now returns a default structure if not found
        return EmailInteractionResponse(
            id=interaction_data.id,
            replyDraft=interaction_data.replyDraft,
            refinementHistory=interaction_data.refinementHistory
        )
    except Exception as e:
        logging.error(f"Error getting interaction data for email {email_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve email interaction data.")


@router.put("/mail/interactions/{email_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
async def update_email_draft(
    email_id: str = Path(..., description="The ID of the email"),
    body: UpdateDraftRequest = Body(...),
    repo: FirestoreRepository = Depends(get_repo)
):
    """Updates the reply draft for a specific email."""
    try:
        repo.update_reply_draft(email_id, body.draft)
        return # Return 204 No Content on success
    except Exception as e:
        logging.error(f"Error updating draft for email {email_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update email draft.")


@router.post("/mail/interactions/{email_id}/refinements", status_code=status.HTTP_204_NO_CONTENT)
async def add_email_refinement_message(
    email_id: str = Path(..., description="The ID of the email"),
    request_body: AddRefinementMessageRequest = Body(...),
    repo: FirestoreRepository = Depends(get_repo)
):
    """Adds a single message (user or AI) to the refinement history."""
    try:
        message_to_save = ChatMessage(sender=request_body.sender, text=request_body.text)
        repo.add_refinement_message(email_id, message_to_save)
        return # Return 204 No Content on success
    except Exception as e:
        logging.error(f"Error adding refinement message for email {email_id}. Request body: {request_body.dict()}. Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add refinement message.")


# --- NEW: Endpoint to clear refinement history ---
@router.delete("/mail/interactions/{email_id}/refinements", status_code=status.HTTP_204_NO_CONTENT)
async def clear_email_refinement_history(
    email_id: str = Path(..., description="The ID of the email"),
    repo: FirestoreRepository = Depends(get_repo)
):
    """Clears the refinement chat history for a specific email."""
    try:
        repo.clear_refinement_history(email_id)
        return # Return 204 No Content on success
    except Exception as e:
        logging.error(f"Error clearing refinement history for email {email_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to clear refinement history.")
