from fastapi import APIRouter
from app.models.lem_requests import LemGenerateRequest

router = APIRouter(prefix="/lem", tags=["lem"])


@router.get("/ping")
def ping():
    return {"lem": "ok"}


@router.post("/generate")
def generate(payload: LemGenerateRequest):
    return {"received": payload.dict()}
