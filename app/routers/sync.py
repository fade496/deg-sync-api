from fastapi import APIRouter, Header

from app.core.auth import check_key
from app.services.sync_clients import sync_clients
from app.services.sync_contacts import sync_contacts
from app.services.sync_projects import sync_projects
from app.services.sync_people import sync_people

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/clients")
def sync_clients_route(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return sync_clients()

@router.post("/contacts")
def sync_contacts_route(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return sync_contacts()

@router.post("/projects")
def sync_projects_route(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return sync_projects()

@router.post("/people")
def sync_people_route(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return sync_people()
