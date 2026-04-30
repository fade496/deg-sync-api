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

    return {
        "status": "success",
        "filename": zip_name,
        "download_url": f"/lem/download/{zip_name}",
        "from_date": request.from_date,
        "to_date": request.to_date,
        "include_csv": request.include_csv,
        "include_pdf": request.include_pdf
    }
