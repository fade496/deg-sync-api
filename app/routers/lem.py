from pathlib import Path
import shutil

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models.lem_requests import LemGenerateRequest
from app.services.lem import generate_lem


router = APIRouter(prefix="/lem", tags=["lem"])

BASE_URL = "https://deg-sync-api-417046885785.northamerica-northeast1.run.app"
LEM_OUTPUT_DIR = Path("/tmp/lem_outputs")


@router.get("/ping")
def ping():
    return {"lem": "ok"}


@router.post("/generate")
def generate(payload: LemGenerateRequest):
    LEM_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    temp_zip_path = Path(generate_lem(payload))

    if not temp_zip_path.exists():
        raise HTTPException(status_code=500, detail="LEM ZIP was not created")

    from_date = str(payload.from_date)
    to_date = str(payload.to_date)

    zip_name = f"lem_{from_date}_{to_date}.zip"
    final_zip_path = LEM_OUTPUT_DIR / zip_name

    shutil.copyfile(temp_zip_path, final_zip_path)

    return {
        "status": "success",
        "filename": zip_name,
        "download_url": f"{BASE_URL}/lem/download/{zip_name}",
        "from_date": from_date,
        "to_date": to_date,
        "include_csv": payload.include_csv,
        "include_pdf": payload.include_pdf,
    }


@router.get("/download/{filename}")
def download_lem_file(filename: str):
    LEM_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    file_path = (LEM_OUTPUT_DIR / filename).resolve()
    output_dir = LEM_OUTPUT_DIR.resolve()

    if output_dir not in file_path.parents:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="LEM file not found")

    return FileResponse(
        path=str(file_path),
        media_type="application/zip",
        filename=filename,
    )
