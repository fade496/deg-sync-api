from fastapi import APIRouter, Header

from app.core.auth import check_key
from app.models.scheduler_requests import (
    SchedulerCreateRequest,
    SchedulerRunRequest,
)
from app.services.scheduler import (
    create_scheduler_job,
    list_scheduler_jobs,
    delete_scheduler_job,
    run_scheduler,
)

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.post("/jobs")
def create_job(
    payload: SchedulerCreateRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return create_scheduler_job(payload)


@router.get("/jobs")
def get_jobs(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return list_scheduler_jobs()


@router.delete("/jobs/{record_id}")
def delete_job(
    record_id: str,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return delete_scheduler_job(record_id)


@router.post("/run")
def run_jobs(
    payload: SchedulerRunRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return run_scheduler(payload)


@router.post("/run/sync-all")
def run_sync_all_now(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    return run_scheduler(SchedulerRunRequest(job_type="sync_all"))
