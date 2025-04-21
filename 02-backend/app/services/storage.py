import logging
from google.cloud import storage

async def read_text_from_gcs(gcs_uri: str) -> str:
    if not gcs_uri.startswith("gs://"):
        raise ValueError("Invalid GCS URI")
    bucket_name, object_name = gcs_uri[5:].split("/", 1)
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(object_name)
    data = blob.download_as_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        logging.warning("utf-8 decode failed, falling back to latin-1")
        return data.decode("latin-1")
