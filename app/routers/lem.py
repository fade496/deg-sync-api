from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models.lem_requests import LemGenerateRequest
from app.services.lem import generate_lem


router = APIRouter(prefix="/lem", tags=["lem"])

BASE_URL = "https://deg-sync-api-417046885785.northamerica-northeast1.run.app"


@router.get("/ping")
def ping():
    return {"lem": "ok"}


@router.post("/generate")
def generate(payload: LemGenerateRequest):
    zip_path = generate_lem(payload)
    zip_path = Path(zip_path)
    zip_name = zip_path.name

    return {
        "status": "success",
        "filename": zip_name,
        "download_url": f"{BASE_URL}/lem/download/{zip_name}",
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "include_csv": payload.include_csv,
        "include_pdf": payload.include_pdf,
    }


@router.get("/download/{filename}")
def download_lem_file(filename: str):
    output_dir = Path("outputs/lem").resolve()
    file_path = (output_dir / filename).resolve()

    if output_dir not in file_path.parents:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="LEM file not found")

    return FileResponse(
        path=file_path,
        media_type="application/zip",
        filename=filename,
    )
