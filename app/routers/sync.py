from fastapi import APIRouter, Header

from app.core.auth import check_key
from app.services.sync_clients import sync_clients

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/clients")
def sync_clients_route(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return sync_clients()
