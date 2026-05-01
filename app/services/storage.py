import os
from datetime import timedelta

from google.cloud import storage


BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
URL_EXPIRATION_MINUTES = 60


def upload_zip_and_create_signed_url(zip_path: str) -> str:
    if not BUCKET_NAME:
        raise ValueError("GCS_BUCKET_NAME is not set")

    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)

    filename = os.path.basename(zip_path)
    blob = bucket.blob(f"lems/{filename}")

    # Upload file
    blob.upload_from_filename(zip_path)

    # ✅ This now works because IAM role is set
    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=URL_EXPIRATION_MINUTES),
        method="GET",
    )

    return url
