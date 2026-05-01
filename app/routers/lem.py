from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.models.lem_requests import LemGenerateRequest
from app.services.lem import generate_lem


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
    Runs LEM generation but returns JSON instead of a binary ZIP.
    """
    zip_path = generate_lem(payload)

    return {
        "status": "success",
        "message": "LEM outputs generated successfully.",
        "filename": "lem_outputs.zip",
        "zip_path": str(zip_path),
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "project_codes": payload.project_codes,
        "include_csv": payload.include_csv,
        "include_pdf": payload.include_pdf,
        "note": "Use /lem/generate in Swagger to download the ZIP file.",
    }
