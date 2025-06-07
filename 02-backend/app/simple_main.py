"""
Simplified FastAPI Backend for AI Customer Service
Consolidates core functionality with minimal complexity
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from google.cloud import firestore
import vertexai
from vertexai.generative_models import GenerativeModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Vertex AI (you'll need to set your project ID)
PROJECT_ID = "main-dev-431619"  # Replace with your actual project ID
LOCATION = "europe-west3"  # Replace with your preferred location
vertexai.init(project=PROJECT_ID, location=LOCATION)

# Initialize Firestore
db = firestore.Client(project=PROJECT_ID)

# Initialize LLM
model = GenerativeModel("gemini-1.5-flash")

# Security
security = HTTPBearer()

# FastAPI app
app = FastAPI(
    title="Simple AI Customer Service Backend",
    description="Simplified API for chat and document management",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---
class ChatMessage(BaseModel):
    id: Optional[str] = None
    text: str
    sender: str  # "user" or "bot"
    timestamp: Optional[datetime] = None

class ChatSession(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

class QueryRequest(BaseModel):
    query: str

class DocumentItem(BaseModel):
    id: str
    name: str
    content: str
    created_at: datetime

# --- Authentication (Simplified) ---
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Simple auth check - you can enhance this with actual JWT verification"""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    # For now, just return a dummy user - replace with real JWT verification
    return {"user_id": "demo_user", "email": "demo@example.com"}

# --- Services ---
class ChatService:
    """Handles all chat-related operations"""
    
    def __init__(self, db_client: firestore.Client, llm_model: GenerativeModel):
        self.db = db_client
        self.model = llm_model
    
    def create_chat(self, user_id: str) -> ChatSession:
        """Create a new chat session"""
        chat_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        chat_data = {
            "id": chat_id,
            "title": "New Chat",
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        
        self.db.collection("chats").document(chat_id).set(chat_data)
        return ChatSession(**chat_data)
    
    def get_chats(self, user_id: str) -> List[ChatSession]:
        """Get all chats for a user"""
        docs = self.db.collection("chats").where("user_id", "==", user_id).order_by("updated_at", direction=firestore.Query.DESCENDING).stream()
        return [ChatSession(**doc.to_dict()) for doc in docs]
    
    def get_messages(self, chat_id: str) -> List[ChatMessage]:
        """Get all messages for a chat"""
        docs = self.db.collection("chats").document(chat_id).collection("messages").order_by("timestamp").stream()
        return [ChatMessage(**doc.to_dict()) for doc in docs]
    
    def add_message(self, chat_id: str, message: ChatMessage) -> ChatMessage:
        """Add a message to a chat"""
        message.id = str(uuid.uuid4())
        message.timestamp = datetime.now(timezone.utc)
        
        # Save message
        self.db.collection("chats").document(chat_id).collection("messages").document(message.id).set(message.dict())
        
        # Update chat timestamp and title if first user message
        if message.sender == "user":
            chat_ref = self.db.collection("chats").document(chat_id)
            chat_doc = chat_ref.get()
            if chat_doc.exists:
                chat_data = chat_doc.to_dict()
                updates = {"updated_at": message.timestamp}
                
                # Update title if it's still "New Chat"
                if chat_data.get("title") == "New Chat":
                    # Use first 50 characters of user message as title
                    updates["title"] = message.text[:50] + ("..." if len(message.text) > 50 else "")
                
                chat_ref.update(updates)
        
        return message
    
    async def generate_response(self, query: str) -> str:
        """Generate AI response to user query"""
        try:
            response = await self.model.generate_content_async(
                f"You are a helpful customer service assistant. Please respond to: {query}"
            )
            return response.text
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I apologize, but I'm having trouble generating a response right now. Please try again."

class DocumentService:
    """Handles document operations"""
    
    def __init__(self, db_client: firestore.Client):
        self.db = db_client
    
    def add_document(self, user_id: str, name: str, content: str) -> DocumentItem:
        """Add a new document"""
        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        doc_data = {
            "id": doc_id,
            "name": name,
            "content": content,
            "user_id": user_id,
            "created_at": now,
        }
        
        self.db.collection("documents").document(doc_id).set(doc_data)
        return DocumentItem(**doc_data)
    
    def get_documents(self, user_id: str) -> List[DocumentItem]:
        """Get all documents for a user"""
        docs = self.db.collection("documents").where("user_id", "==", user_id).order_by("created_at", direction=firestore.Query.DESCENDING).stream()
        return [DocumentItem(**doc.to_dict()) for doc in docs]
    
    def delete_document(self, doc_id: str, user_id: str):
        """Delete a document"""
        doc_ref = self.db.collection("documents").document(doc_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Document not found")
        
        doc_data = doc.to_dict()
        if doc_data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this document")
        
        doc_ref.delete()

# Initialize services
chat_service = ChatService(db, model)
document_service = DocumentService(db)

# --- Chat Endpoints ---
@app.post("/chats", response_model=ChatSession)
async def create_chat(user: dict = Depends(get_current_user)):
    """Create a new chat session"""
    return chat_service.create_chat(user["user_id"])

@app.get("/chats", response_model=List[ChatSession])
async def get_chats(user: dict = Depends(get_current_user)):
    """Get all chat sessions for the user"""
    return chat_service.get_chats(user["user_id"])

@app.get("/chats/{chat_id}/messages", response_model=List[ChatMessage])
async def get_chat_messages(chat_id: str, user: dict = Depends(get_current_user)):
    """Get messages for a specific chat"""
    return chat_service.get_messages(chat_id)

@app.post("/chats/{chat_id}/messages")
async def send_message(
    chat_id: str, 
    query: QueryRequest, 
    user: dict = Depends(get_current_user)
):
    """Send a message and get AI response"""
    try:
        # Add user message
        user_message = ChatMessage(text=query.query, sender="user")
        saved_user_message = chat_service.add_message(chat_id, user_message)
        
        # Generate AI response
        ai_response = await chat_service.generate_response(query.query)
        
        # Add AI message
        ai_message = ChatMessage(text=ai_response, sender="bot")
        saved_ai_message = chat_service.add_message(chat_id, ai_message)
        
        return {
            "user_message": saved_user_message,
            "bot_message": saved_ai_message
        }
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail="Failed to process message")

# --- Document Endpoints ---
@app.post("/documents", response_model=DocumentItem)
async def add_document(
    name: str,
    content: str,
    user: dict = Depends(get_current_user)
):
    """Add a new document"""
    return document_service.add_document(user["user_id"], name, content)

@app.get("/documents", response_model=List[DocumentItem])
async def get_documents(user: dict = Depends(get_current_user)):
    """Get all documents for the user"""
    return document_service.get_documents(user["user_id"])

@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    """Delete a document"""
    document_service.delete_document(doc_id, user["user_id"])
    return {"message": "Document deleted successfully"}

# --- Health Check ---
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "message": "Service is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 