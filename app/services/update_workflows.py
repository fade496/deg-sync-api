from fastapi import HTTPException

from app.clients.harvest import harvest_get, harvest_patch
from app.models.requests import UpdateRequest
from app.services.sync_people import sync_people
from app.services.sync_clients import sync_clients
from app.services.sync_projects import sync_projects
from app.services.sync_tasks import sync_tasks


def update_workflow(payload: UpdateRequest):
    endpoint_map = {
        "person": "users",
        "client": "clients",
        "project": "projects",
        "task": "tasks",
    }

    endpoint = endpoint_map.get(payload.entity)

    if not endpoint:
        raise HTTPException(status_code=400, detail="Invalid entity")

    current_data = harvest_get(f"{endpoint}/{payload.harvest_id}")
    old_value = current_data.get(payload.field)

    if payload.operation == "increment":
        if payload.amount is None:
            raise HTTPException(status_code=400, detail="Missing amount")

        new_value = float(old_value or 0) + payload.amount
    else:
        new_value = payload.value

    update_response = harvest_patch(
        f"{endpoint}/{payload.harvest_id}",
        {payload.field: new_value},
    )

    if update_response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=update_response.status_code,
            detail=update_response.text,
        )

    if payload.entity == "person":
        sync_people()
    elif payload.entity == "client":
        sync_clients()
    elif payload.entity == "project":
        sync_projects()
    elif payload.entity == "task":
        sync_tasks()

    return {
        "status": "updated",
        "old_value": old_value,
        "new_value": new_value,
    }
