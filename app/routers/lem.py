from pathlib import Path
import shutil

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models.lem_requests import LemGenerateRequest
from app.services.lem import generate_lem


router = APIRouter(prefix="/lem", tags=["lem"])

BASE_URL = "https://deg-sync-api-417046885785.northamerica-northeast1.run.app"
LEM_OUTPUT_DIR = Path("/tmp/lem_outputs")
LEM_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/ping")
def ping():
    return {"lem": "ok"}


@router.post("/generate")
def generate(payload: LemGenerateRequest):
    temp_zip_path = Path(generate_lem(payload))

    if not temp_zip_path.exists():
        raise HTTPException(status_code=500, detail="LEM ZIP was not created")

    zip_name = (
        f"lem_{payload.from_date}_{payload.to_date}.zip"
        .replace("/", "-")
        .replace(":", "-")
    )

    final_zip_path = LEM_OUTPUT_DIR / zip_name
    shutil.copyfile(temp_zip_path, final_zip_path)

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
    file_path = (LEM_OUTPUT_DIR / filename).resolve()

    if LEM_OUTPUT_DIR.resolve() not in file_path.parents:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="LEM file not found")

    return FileResponse(
        path=file_path,
        media_type="application/zip",
        filename=filename,
    )
