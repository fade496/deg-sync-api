from fastapi import APIRouter, Header

from app.core.auth import check_key
from app.models.requests import UpdateRequest
from app.services.update_workflows import update_workflow

router = APIRouter(tags=["update"])


@router.post("/update")
def update_route(
    payload: UpdateRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return update_workflow(payload)
