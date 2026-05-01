import os
from datetime import timedelta
from google.cloud import storage


BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")  # set this in Cloud Run
URL_EXPIRATION_MINUTES = 60  # signed URL validity


def upload_zip_and_create_signed_url(zip_path: str) -> str:
    """
    Uploads a ZIP file to GCS and returns a signed download URL.
    """
    if not BUCKET_NAME:
        raise ValueError("GCS_BUCKET_NAME is not set")

    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)

    filename = os.path.basename(zip_path)
    blob = bucket.blob(f"lems/{filename}")

    # Upload file
    blob.upload_from_filename(zip_path)

    # Generate signed URL
    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=URL_EXPIRATION_MINUTES),
        method="GET",
    )

    return url
