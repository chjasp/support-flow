"""
Pub/Sub service for unified content processing.
Handles publishing messages to the content processing topic.
"""

import json
import logging
import uuid
from typing import Dict, Any
from google.cloud import pubsub_v1
from app.config import get_settings
from app.models.domain import ContentProcessingMessage

settings = get_settings()

class PubSubService:
    """Service for publishing content processing messages to Pub/Sub."""
    
    def __init__(self):
        self.project_id = settings.gcp_project_id
        self.topic_name = settings.content_processing_topic
        self.publisher = pubsub_v1.PublisherClient()
        self.topic_path = self.publisher.topic_path(self.project_id, self.topic_name)
        
    def publish_url_processing_task(
        self, 
        task_id: str, 
        urls: list[str], 
        description: str = ""
    ) -> str:
        """Publish a URL processing task to Pub/Sub."""
        
        message = ContentProcessingMessage(
            task_id=task_id,
            task_type="url_processing",
            input_data={
                "urls": urls,
                "description": description
            },
            metadata={
                "source": "web_processing_api",
                "url_count": len(urls)
            }
        )
        
        return self._publish_message(message)
    
    def publish_text_processing_task(
        self, 
        task_id: str, 
        content: str, 
        title: str,
        content_type: str = "text/plain"
    ) -> str:
        """Publish a text processing task to Pub/Sub."""
        
        message = ContentProcessingMessage(
            task_id=task_id,
            task_type="text_processing",
            input_data={
                "content": content,
                "title": title,
                "content_type": content_type
            },
            metadata={
                "source": "text_upload_api",
                "content_length": len(content)
            }
        )
        
        return self._publish_message(message)
    
    def _publish_message(self, message: ContentProcessingMessage) -> str:
        """Publish a content processing message to Pub/Sub."""
        try:
            # Convert message to JSON
            message_data = message.json().encode('utf-8')
            
            # Add attributes for filtering/routing
            attributes = {
                "task_type": message.task_type,
                "task_id": message.task_id,
                "source": message.metadata.get("source", "unknown") if message.metadata else "unknown"
            }
            
            # Publish the message
            future = self.publisher.publish(
                self.topic_path, 
                message_data, 
                **attributes
            )
            
            # Wait for the publish to complete and get message ID
            message_id = future.result()
            
            logging.info(
                f"Published {message.task_type} task {message.task_id} to Pub/Sub. "
                f"Message ID: {message_id}"
            )
            
            return message_id
            
        except Exception as e:
            logging.error(f"Failed to publish message for task {message.task_id}: {e}", exc_info=True)
            raise Exception(f"Failed to publish message: {str(e)}")
    
    def close(self):
        """Close the publisher client."""
        if hasattr(self, 'publisher'):
            self.publisher.close()


# Dependency injection function
def get_pubsub_service() -> PubSubService:
    """Get PubSub service instance."""
    return PubSubService() 