from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.models.lem_requests import LemGenerateRequest
from app.services.lem import generate_lem
from app.services.dropbox_storage import upload_zip_and_create_shared_link


router = APIRouter(prefix="/lem", tags=["lem"])


@router.get("/ping")
def ping():
    return {"lem": "ok"}


@router.post("/generate")
def generate(payload: LemGenerateRequest):
    """
    Swagger/manual endpoint.
    Returns the ZIP file directly.
    """
    zip_path = generate_lem(payload)

    return FileResponse(
        path=zip_path,
        filename="lem_outputs.zip",
        media_type="application/zip",
    )


@router.post("/generate-json")
def generate_json(payload: LemGenerateRequest):
    """
    ChatGPT Action-safe endpoint.
    Generates LEM ZIP, uploads it to Dropbox, and returns a download link.
    """
    try:
        zip_path = generate_lem(payload)

        download_url = upload_zip_and_create_shared_link(
            zip_path,
            from_date=str(payload.from_date),
            to_date=str(payload.to_date),
        )

        return {
            "status": "success",
            "message": "LEM outputs generated successfully.",
            "filename": "lem_outputs.zip",
            "download_url": download_url,
            "from_date": str(payload.from_date),
            "to_date": str(payload.to_date),
            "project_codes": payload.project_codes,
            "include_csv": payload.include_csv,
            "include_pdf": payload.include_pdf,
        }

    except Exception as e:
        return {
            "status": "error",
            "message": "LEM generation failed.",
            "error": str(e),
            "type": type(e).__name__,
        }
