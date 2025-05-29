import uuid, logging, datetime
from fastapi import APIRouter, Depends, HTTPException, status, Path
from typing import List
from collections import OrderedDict

from app.api.deps import get_repo, get_pipeline, get_enhanced_pipeline
from app.services.firestore import FirestoreRepository, _DEFAULT_CHAT_TITLE, NotFound
from app.services.pipeline import DocumentPipeline
from app.services.enhanced_pipeline import EnhancedDocumentPipeline
from app.models.domain import (
    QueryRequest,
    # QueryResponse, # No longer used here
    # Chunk, # No longer used here
    ChatMessage,
    ChatMetadata,
    NewChatResponse,
    PostMessageResponse,
    DocumentSource
)
from app.config import get_settings

router = APIRouter(prefix="/chats", tags=["chats"])
settings = get_settings()

@router.get("/", response_model=List[ChatMetadata])
async def get_chat_list(repo: FirestoreRepository = Depends(get_repo)):
    """Retrieves metadata for all chat sessions, ordered by last activity."""
    try:
        return repo.list_chats()
    except Exception as e:
        logging.error(f"Error listing chats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve chat list.")

@router.post("/", response_model=NewChatResponse, status_code=status.HTTP_201_CREATED)
async def create_new_chat(repo: FirestoreRepository = Depends(get_repo)):
    """Creates a new, empty chat session."""
    try:
        # Optionally add an initial bot message here if desired
        # initial_bot_message = ChatMessage(text="Hello! How can I help you today?", sender="bot")
        # new_chat_meta = repo.create_chat(initial_message=initial_bot_message)
        new_chat_meta = repo.create_chat()

        # Fetch initial messages if any were added (e.g., welcome message)
        initial_messages = []
        if new_chat_meta.id:
             try:
                 initial_messages = repo.get_chat_messages(new_chat_meta.id)
             except Exception as e:
                 logging.warning(f"Could not fetch initial messages for new chat {new_chat_meta.id}: {e}")


        return NewChatResponse(
            id=new_chat_meta.id,
            title=new_chat_meta.title,
            messages=initial_messages,
            createdAt=new_chat_meta.createdAt,
            lastActivity=new_chat_meta.lastActivity
        )
    except Exception as e:
        logging.error(f"Error creating new chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create new chat.")

@router.get("/{chat_id}/messages", response_model=List[ChatMessage])
async def get_messages_for_chat(
    chat_id: str = Path(..., title="The ID of the chat session"),
    repo: FirestoreRepository = Depends(get_repo)
):
    """Retrieves all messages for a specific chat session."""
    try:
        return repo.get_chat_messages(chat_id)
    except NotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chat {chat_id} not found.")
    except Exception as e:
        logging.error(f"Error getting messages for chat {chat_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve messages.")

@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(
    chat_id: str = Path(..., title="The ID of the chat session to delete"),
    repo: FirestoreRepository = Depends(get_repo)
):
    """Deletes a specific chat session and all its messages."""
    try:
        repo.delete_chat(chat_id)
        return
    except NotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chat {chat_id} not found.")
    except Exception as e:
        logging.error(f"Error deleting chat {chat_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete chat.")

query_router = APIRouter(prefix="/chat", tags=["chat query"])

@query_router.post("/{chat_id}", response_model=PostMessageResponse)
async def post_message_to_chat(
    body: QueryRequest,
    chat_id: str = Path(..., title="The ID of the chat session"),
    repo: FirestoreRepository = Depends(get_repo),
    enhanced_pipeline: EnhancedDocumentPipeline = Depends(get_enhanced_pipeline),
    fallback_pipeline: DocumentPipeline = Depends(get_pipeline)
):
    """
    Sends a user message to a chat, generates a bot response using enhanced RAG,
    saves both messages, updates chat metadata, and returns both saved messages.
    """
    try:
        # 1. Save User Message
        user_message_to_save = ChatMessage(text=body.query, sender="user")
        saved_user_message = repo.add_message_to_chat(chat_id, user_message_to_save)

        # 2. Perform Enhanced RAG Pipeline
        logging.info(f"Performing enhanced RAG for chat {chat_id} with query: '{body.query[:50]}...'")
        
        try:
            # Try enhanced pipeline first
            context_chunks = await enhanced_pipeline.hybrid_search_enhanced(body.query)
            answer = await enhanced_pipeline.answer_enhanced(body.query, context_chunks)
        except Exception as e:
            logging.warning(f"Enhanced pipeline failed, falling back to standard pipeline: {e}")
            # Fallback to standard pipeline
            context_chunks = await fallback_pipeline.hybrid_search(body.query)
            answer = await fallback_pipeline.answer(body.query, context_chunks)
            
        logging.info(f"Generated answer for chat {chat_id}: '{answer[:50]}...'")

        # 3. Build the distinct document list
        unique_docs = OrderedDict()
        for c in context_chunks:
            doc_id = c.get("doc_id") or c.get("document_id")
            if doc_id and doc_id not in unique_docs:
                unique_docs[doc_id] = DocumentSource(
                    id=str(doc_id),
                    name=c.get("doc_filename") or "Unknown Document",
                    uri=c.get("gcs_uri"),
                )
        sources = list(unique_docs.values())

        # 4. Save Bot Message
        bot_message_to_save = ChatMessage(text=answer, sender="bot", sources=sources)
        saved_bot_message = repo.add_message_to_chat(chat_id, bot_message_to_save)

        # 5. Return the response
        return PostMessageResponse(
            user_message=saved_user_message,
            bot_message=saved_bot_message
        )

    except NotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logging.error(f"Error processing message for chat {chat_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process message due to an internal error.")
