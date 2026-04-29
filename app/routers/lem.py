from fastapi import APIRouter

from app.models.lem_requests import LemGenerateRequest
from app.services.lem import generate_lem

router = APIRouter(prefix="/lem", tags=["lem"])


@router.get("/ping")
def ping():
    return {"lem": "ok"}


@router.post("/generate")
def generate(payload: LemGenerateRequest):
    return generate_lem(payload)
