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
    zip_path = generate_lem(payload)

    return FileResponse(
        path=zip_path,
        filename="lem_outputs.zip",
        media_type="application/zip",
    )

@router.post("/generate-json")
def generate_json(payload: LemGenerateRequest):
    zip_path = generate_lem(payload)

    return {
        "status": "success",
        "filename": "lem_outputs.zip",
        "download_url": f"/lem/generate-download?from_date={payload.from_date}&to_date={payload.to_date}",
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "include_csv": payload.include_csv,
        "include_pdf": payload.include_pdf,
    }
