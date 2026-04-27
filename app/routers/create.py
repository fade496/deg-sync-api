from fastapi import APIRouter, Header

from app.core.auth import check_key
from app.models.requests import CreateClientRequest
from app.services.create_workflows import create_client_workflow
from app.models.requests import CreateContactRequest
from app.services.create_workflows import create_contact_workflow

router = APIRouter(prefix="/create", tags=["create"])


@router.post("/client")
def create_client_route(
    payload: CreateClientRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return create_client_workflow(payload)

@router.post("/contact")
def create_contact_route(
    payload: CreateContactRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return create_contact_workflow(payload)
