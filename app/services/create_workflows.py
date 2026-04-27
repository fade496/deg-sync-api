from fastapi import HTTPException

from app.clients.harvest import get_harvest_records, harvest_post
from app.services.sync_clients import sync_clients
from app.models.requests import CreateClientRequest


def create_client_workflow(payload: CreateClientRequest):
    existing_clients = get_harvest_records("clients", "clients")

    for client in existing_clients:
        if (client.get("name") or "").strip().lower() == payload.name.strip().lower():
            return {
                "status": "duplicate_found",
                "message": "Client already exists in Harvest. No new client was created.",
                "harvest_client": client,
            }

    harvest_payload = {
        "name": payload.name,
        "currency": payload.currency,
        "address": payload.address or "",
        "is_active": payload.is_active,
    }

    response = harvest_post("clients", harvest_payload)

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    created_client = response.json()
    sync_result = sync_clients()

    return {
        "status": "created",
        "message": "Client created in Harvest and synced to Airtable.",
        "harvest_client": created_client,
        "sync_result": sync_result,
    }
