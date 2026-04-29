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
