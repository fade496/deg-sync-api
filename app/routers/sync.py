from fastapi import APIRouter, Header

from app.core.auth import check_key
from app.services.sync_clients import sync_clients
from app.services.sync_contacts import sync_contacts
from app.services.sync_projects import sync_projects
from app.services.sync_people import sync_people
from app.services.sync_tasks import sync_tasks
from app.services.sync_project_people import sync_project_people
from app.services.sync_project_tasks import sync_project_tasks
from fastapi import Query
from app.services.sync_time_entries import sync_time_entries

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

@router.post("/tasks")
def sync_tasks_route(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return sync_tasks()

@router.post("/project-people")
def sync_project_people_route(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return sync_project_people()

@router.post("/project-tasks")
def sync_project_tasks_route(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return sync_project_tasks()

@router.post("/time-entries")
def sync_time_entries_route(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
    from_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    to_date: str = Query(..., description="End date in YYYY-MM-DD format"),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return sync_time_entries(from_date=from_date, to_date=to_date)
