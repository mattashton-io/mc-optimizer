import os

import google.auth
from google.cloud import storage
from google.api_core.exceptions import Conflict, Forbidden


def get_storage_client():
    return storage.Client()

def get_bucket_name():
    """Returns the bucket name. Creates one if it doesn't exist."""
    _, project_id = google.auth.default()
    bucket_name = f"{project_id}-mc-data-prep"
    client = get_storage_client()

    try:
        client.get_bucket(bucket_name)
    except Forbidden:
        print(f"Bucket {bucket_name} exists but is not readable (403 Forbidden). Proceeding...")
    except Exception:
        print(f"Bucket {bucket_name} not found or inaccessible. Attempting to create...")
        try:
            client.create_bucket(bucket_name)
            print(f"Bucket {bucket_name} created successfully.")
        except Conflict:
            print(f"Bucket {bucket_name} already exists (409 Conflict). Proceeding...")
        except Exception as e:
            print(f"Warning: Failed to create bucket {bucket_name} (might already exist): {e}")

    return bucket_name

def upload_to_gcs(local_path: str, gcs_path: str):
    """Uploads a local file to GCS."""
    bucket_name = get_bucket_name()
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(local_path)
    return f"gs://{bucket_name}/{gcs_path}"

def download_from_gcs(gcs_path: str, local_path: str):
    """Downloads a file from GCS to local path."""
    bucket_name = get_bucket_name()
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    blob.download_to_filename(local_path)
    return local_path

def list_gcs_files(prefix: str):
    """Lists files in GCS with a given prefix."""
    bucket_name = get_bucket_name()
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)
    return [blob.name for blob in blobs]

def read_gcs_file(gcs_path: str):
    """Reads a file from GCS and returns its content."""
    bucket_name = get_bucket_name()
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    return blob.download_as_text()

def write_gcs_file(gcs_path: str, content: str):
    """Writes content to a file in GCS."""
    bucket_name = get_bucket_name()
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    blob.upload_from_string(content)
    return f"gs://{bucket_name}/{gcs_path}"
