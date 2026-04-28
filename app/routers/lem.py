from fastapi import APIRouter, Header

from app.core.auth import check_key
from app.models.lem_requests import LemGenerateRequest
from app.services.lem import generate_lem

router = APIRouter(prefix="/lem", tags=["lem"])


@router.post("/generate")
def generate_lem_route(
    payload: LemGenerateRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return generate_lem(payload)
