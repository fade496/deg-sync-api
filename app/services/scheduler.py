from datetime import datetime, timezone

from fastapi import HTTPException

from app.clients.airtable import (
    get_airtable_records,
    create_airtable_record,
    update_airtable_record,
)
from app.models.scheduler_requests import SchedulerCreateRequest, SchedulerRunRequest
from app.services.sync_clients import sync_clients
from app.services.sync_contacts import sync_contacts
from app.services.sync_projects import sync_projects
from app.services.sync_people import sync_people
from app.services.sync_tasks import sync_tasks
from app.services.sync_project_people import sync_project_people
from app.services.sync_project_tasks import sync_project_tasks


SCHEDULER_TABLE = "Scheduler Jobs"


def utc_now():
    return datetime.now(timezone.utc)


def utc_now_iso():
    return utc_now().isoformat()


def normalize_text(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def create_scheduler_job(payload: SchedulerCreateRequest):
    fields = {
        "Name": payload.name,
        "Job Type": payload.job_type,
        "Frequency": payload.frequency,
        "Day": payload.day or "",
        "Time": payload.time or "",
        "Active": payload.active,
    }

    response = create_airtable_record(SCHEDULER_TABLE, fields)

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    return {
        "status": "created",
        "record": response.json(),
    }


def list_scheduler_jobs():
    records = get_airtable_records(SCHEDULER_TABLE)

    return {
        "count": len(records),
        "jobs": records,
    }


def delete_scheduler_job(record_id: str):
    raise HTTPException(
        status_code=501,
        detail="Delete is not implemented yet. For now, set Active to false in Airtable.",
    )


def is_job_due(fields: dict):
    active = fields.get("Active") is True

    if not active:
        return False

    frequency = normalize_text(fields.get("Frequency"))
    day = normalize_text(fields.get("Day"))
    scheduled_time = normalize_text(fields.get("Time"))

    now = utc_now()

    if frequency == "manual":
        return False

    if scheduled_time:
        current_time = now.strftime("%H:%M")
        if current_time != scheduled_time:
            return False

    if frequency == "daily":
        return True

    if frequency == "weekly":
        current_day = now.strftime("%A").lower()
        return day == current_day

    return False


def run_sync_all():
    results = {}

    results["clients"] = sync_clients()
    results["contacts"] = sync_contacts()
    results["projects"] = sync_projects()
    results["people"] = sync_people()
    results["tasks"] = sync_tasks()
    results["project_people"] = sync_project_people()
    results["project_tasks"] = sync_project_tasks()

    return results


def run_time_entries_job():
    raise HTTPException(
        status_code=501,
        detail="Scheduled time entries sync needs from_date/to_date logic before enabling.",
    )


def run_job_by_type(job_type: str):
    job_type_normalized = normalize_text(job_type)

    if job_type_normalized == "sync_all":
        return run_sync_all()

    if job_type_normalized == "time_entries":
        return run_time_entries_job()

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported job type: {job_type}",
    )


def run_scheduler(payload: SchedulerRunRequest):
    records = get_airtable_records(SCHEDULER_TABLE)

    ran_jobs = []
    skipped_jobs = []

    for record in records:
        record_id = record.get("id")
        fields = record.get("fields", {})
        job_type = fields.get("Job Type")
        name = fields.get("Name", record_id)

        if payload.job_type and normalize_text(payload.job_type) != normalize_text(job_type):
            skipped_jobs.append({
                "record_id": record_id,
                "name": name,
                "reason": "job_type_filter_did_not_match",
            })
            continue

        if payload.job_type:
            due = True
        else:
            due = is_job_due(fields)

        if not due:
            skipped_jobs.append({
                "record_id": record_id,
                "name": name,
                "reason": "not_due",
            })
            continue

        result = run_job_by_type(job_type)

        update_airtable_record(
            SCHEDULER_TABLE,
            record_id,
            {
                "Last Run": utc_now_iso(),
            },
        )

        ran_jobs.append({
            "record_id": record_id,
            "name": name,
            "job_type": job_type,
            "result": result,
        })

    return {
        "status": "completed",
        "ran": len(ran_jobs),
        "skipped": len(skipped_jobs),
        "ran_jobs": ran_jobs,
        "skipped_jobs": skipped_jobs,
    }
