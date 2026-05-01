import os
from datetime import timedelta

from google.cloud import storage
from google.auth import default


BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
URL_EXPIRATION_MINUTES = 60


def upload_zip_and_create_signed_url(zip_path: str) -> str:
    """
    Uploads a ZIP file to GCS and returns a signed download URL.
    Works in Cloud Run using IAM (no private key file required).
    """
    if not BUCKET_NAME:
        raise ValueError("GCS_BUCKET_NAME is not set")

    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)

    filename = os.path.basename(zip_path)
    blob = bucket.blob(f"lems/{filename}")

    # Upload file
    blob.upload_from_filename(zip_path)

    # Get default credentials (Cloud Run service account)
    credentials, _ = default()

    # Generate signed URL using IAM signing
    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=URL_EXPIRATION_MINUTES),
        method="GET",
        credentials=credentials,
    )

    return url
