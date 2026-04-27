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

from app.services.sync_contacts import sync_contacts
from app.models.requests import CreateContactRequest


def create_contact_workflow(payload: CreateContactRequest):
    if not payload.harvest_client_id and not payload.client_name:
        raise HTTPException(
            status_code=400,
            detail="Provide either harvest_client_id or client_name.",
        )

    harvest_client = None
    clients = get_harvest_records("clients", "clients")

    if payload.harvest_client_id:
        for client in clients:
            if client.get("id") == payload.harvest_client_id:
                harvest_client = client
                break
    else:
        for client in clients:
            if (client.get("name") or "").strip().lower() == payload.client_name.strip().lower():
                harvest_client = client
                break

    if not harvest_client:
        raise HTTPException(
            status_code=404,
            detail="Matching Harvest client not found. Create the client first.",
        )

    harvest_client_id = harvest_client.get("id")

    existing_contacts = get_harvest_records("contacts", "contacts")
    incoming_email = (payload.email or "").strip().lower()

    for contact in existing_contacts:
        contact_email = (contact.get("email") or "").strip().lower()

        if incoming_email and contact_email == incoming_email:
            return {
                "status": "duplicate_found",
                "message": "Contact already exists in Harvest by email. No new contact was created.",
                "harvest_contact": contact,
            }

        same_client = (contact.get("client") or {}).get("id") == harvest_client_id
        same_name = (
            (contact.get("first_name") or "").strip().lower() == payload.first_name.strip().lower()
            and (contact.get("last_name") or "").strip().lower() == payload.last_name.strip().lower()
        )

        if same_client and same_name:
            return {
                "status": "duplicate_found",
                "message": "Contact already exists in Harvest for this client by name. No new contact was created.",
                "harvest_contact": contact,
            }

    harvest_payload = {
        "client_id": harvest_client_id,
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "email": payload.email or "",
        "phone_office": payload.phone or "",
        "title": payload.title or "",
    }

    response = harvest_post("contacts", harvest_payload)

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    created_contact = response.json()
    sync_result = sync_contacts()

    return {
        "status": "created",
        "message": "Contact created in Harvest and synced to Airtable.",
        "harvest_client": harvest_client,
        "harvest_contact": created_contact,
        "sync_result": sync_result,
    }
