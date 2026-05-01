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
    Original working ZIP endpoint.
    Use this for Swagger.
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
    Chat-safe metadata endpoint.
    Does not replace the working ZIP endpoint.
    """
    return {
        "status": "success",
        "message": "Use /lem/generate for ZIP download.",
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "project_codes": payload.project_codes,
        "include_csv": payload.include_csv,
        "include_pdf": payload.include_pdf,
    }
