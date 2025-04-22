import os
import base64
import email
import logging
from typing import List, Dict, Optional
from google.oauth2 import service_account, credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

from app.config import Settings # Use your settings

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

class GmailService:
    """Handles Gmail API interactions."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.service: Optional[Resource] = None
        self._build_service()

    def _build_creds(self) -> Optional[credentials.Credentials]:
        """Builds credentials using the service account."""
        sa_path = self.settings.google_service_account_json
        impersonate_email = self.settings.gmail_impersonate_email

        if not sa_path or not impersonate_email:
            logging.error("Missing GOOGLE_SERVICE_ACCOUNT_JSON or GMAIL_IMPERSONATE_EMAIL settings.")
            return None
        if not os.path.exists(sa_path):
             logging.error(f"Service account file not found at: {sa_path}")
             return None

        try:
            creds = service_account.Credentials.from_service_account_file(
                sa_path, scopes=SCOPES
            )
            # Impersonate the real mailbox user
            delegated_creds = creds.with_subject(impersonate_email)
            logging.info(f"Successfully created delegated credentials for {impersonate_email}")
            return delegated_creds
        except Exception as e:
            logging.error(f"Failed to create service account credentials: {e}", exc_info=True)
            return None

    def _build_service(self):
        """Builds the Gmail API service resource."""
        creds = self._build_creds()
        if creds:
            try:
                self.service = build("gmail", "v1", credentials=creds, cache_discovery=False)
                logging.info("Gmail API service built successfully.")
            except Exception as e:
                 logging.error(f"Failed to build Gmail service: {e}", exc_info=True)
                 self.service = None
        else:
            self.service = None

    def list_messages(self, max_results: int = 20, query: Optional[str] = None) -> List[Dict]:
        """Lists messages with metadata."""
        if not self.service:
            raise ConnectionError("Gmail service not initialized.")

        try:
            # Initial list request (only gets IDs)
            results = self.service.users().messages().list(
                userId="me", maxResults=max_results, q=query
            ).execute()

            messages_summary = []
            batch = self.service.new_batch_http_request(callback=self._batch_callback(messages_summary))

            # Batch request for metadata of each message
            message_ids = [m['id'] for m in results.get('messages', [])]
            if not message_ids:
                return []

            for msg_id in message_ids:
                batch.add(self.service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"]
                ))

            batch.execute()
            # Sort by date descending (internalDate is ms epoch string)
            messages_summary.sort(key=lambda x: int(x.get("date", 0)), reverse=True)
            return messages_summary

        except HttpError as error:
            logging.error(f"An API error occurred during message list: {error}")
            raise ConnectionError(f"Gmail API error: {error.resp.status} {error._get_reason()}")
        except Exception as e:
            logging.error(f"Unexpected error listing messages: {e}", exc_info=True)
            raise

    def _batch_callback(self, messages_list):
        """Callback for batch requests to process each message's metadata."""
        def callback(request_id, response, exception):
            if exception:
                logging.error(f"Batch request failed for ID {request_id}: {exception}")
            else:
                try:
                    headers = {h["name"]: h["value"] for h in response["payload"]["headers"]}
                    messages_list.append({
                        "id": response["id"],
                        "threadId": response.get("threadId"),
                        "subject": headers.get("Subject", "(no subject)"),
                        "from": headers.get("From"),
                        "date": response.get("internalDate"), # ms epoch string
                        "snippet": response.get("snippet"),
                    })
                except Exception as e:
                    logging.error(f"Error processing batch response item {response.get('id', 'N/A')}: {e}")
        return callback


    def get_message_body(self, msg_id: str) -> str:
        """Gets the text/plain body of a specific message."""
        if not self.service:
            raise ConnectionError("Gmail service not initialized.")

        try:
            full_message = self.service.users().messages().get(
                userId="me", id=msg_id, format="full" # Fetch full format
            ).execute()

            payload = full_message.get('payload', {})
            parts = payload.get('parts', [])
            body_data = payload.get('body', {}).get('data')

            # Find the text/plain part
            text_plain_data = None
            if payload.get('mimeType') == 'text/plain' and body_data:
                 text_plain_data = body_data
            elif parts:
                 # Look through parts for text/plain
                 for part in parts:
                     if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
                         text_plain_data = part['body']['data']
                         break
                     # Check nested parts (multipart/alternative)
                     elif part.get('parts'):
                         for sub_part in part.get('parts', []):
                             if sub_part.get('mimeType') == 'text/plain' and sub_part.get('body', {}).get('data'):
                                 text_plain_data = sub_part['body']['data']
                                 break
                         if text_plain_data: break # Found in sub-part

            # If no text/plain, try the first part's body data as fallback (might be HTML)
            if not text_plain_data and not body_data and parts:
                 first_part_body = parts[0].get('body', {})
                 text_plain_data = first_part_body.get('data')

            # If still no data, use the main body data if it exists (might be HTML)
            if not text_plain_data and body_data:
                text_plain_data = body_data


            if text_plain_data:
                # Decode base64url data
                decoded_bytes = base64.urlsafe_b64decode(text_plain_data)
                # Decode bytes to string, trying common encodings
                try:
                    return decoded_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        return decoded_bytes.decode('latin-1')
                    except UnicodeDecodeError:
                        logging.warning(f"Could not decode message body for {msg_id} using utf-8 or latin-1.")
                        return decoded_bytes.decode('ascii', 'ignore') # Fallback
            else:
                logging.warning(f"No suitable text/plain body found for message {msg_id}")
                return "(Could not extract plain text body)"

        except HttpError as error:
            logging.error(f"An API error occurred getting message {msg_id}: {error}")
            raise ConnectionError(f"Gmail API error: {error.resp.status} {error._get_reason()}")
        except Exception as e:
            logging.error(f"Unexpected error getting message {msg_id}: {e}", exc_info=True)
            raise
