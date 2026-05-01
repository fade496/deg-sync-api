from google.cloud import storage
from datetime import timedelta
import os

BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")

def upload_zip_and_create_signed_url(zip_path: str) -> str:
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)

    filename = os.path.basename(zip_path)
    blob = bucket.blob(f"lems/{filename}")

    blob.upload_from_filename(zip_path)

    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=60),
        method="GET",
    )

    return url
