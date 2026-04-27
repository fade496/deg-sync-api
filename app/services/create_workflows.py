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

from app.models.requests import CreateClientWithContactRequest


def create_client_with_contact_workflow(payload: CreateClientWithContactRequest):
    clients = get_harvest_records("clients", "clients")
    harvest_client = None
    client_created = False

    for client in clients:
        if (client.get("name") or "").strip().lower() == payload.client_name.strip().lower():
            harvest_client = client
            break

    if not harvest_client:
        harvest_client_payload = {
            "name": payload.client_name,
            "currency": payload.currency,
            "address": payload.address or "",
            "is_active": payload.is_active,
        }

        client_response = harvest_post("clients", harvest_client_payload)

        if client_response.status_code not in [200, 201]:
            raise HTTPException(
                status_code=client_response.status_code,
                detail=client_response.text,
            )

        harvest_client = client_response.json()
        client_created = True

    harvest_client_id = harvest_client.get("id")

    contacts = get_harvest_records("contacts", "contacts")
    harvest_contact = None
    contact_created = False

    incoming_email = (payload.contact_email or "").strip().lower()

    for contact in contacts:
        contact_email = (contact.get("email") or "").strip().lower()

        if incoming_email and contact_email == incoming_email:
            harvest_contact = contact
            break

        same_client = (contact.get("client") or {}).get("id") == harvest_client_id
        same_name = (
            (contact.get("first_name") or "").strip().lower()
            == payload.contact_first_name.strip().lower()
            and (contact.get("last_name") or "").strip().lower()
            == payload.contact_last_name.strip().lower()
        )

        if same_client and same_name:
            harvest_contact = contact
            break

    if not harvest_contact:
        harvest_contact_payload = {
            "client_id": harvest_client_id,
            "first_name": payload.contact_first_name,
            "last_name": payload.contact_last_name,
            "email": payload.contact_email or "",
            "phone_office": payload.contact_phone or "",
            "title": payload.contact_title or "",
        }

        contact_response = harvest_post("contacts", harvest_contact_payload)

        if contact_response.status_code not in [200, 201]:
            raise HTTPException(
                status_code=contact_response.status_code,
                detail=contact_response.text,
            )

        harvest_contact = contact_response.json()
        contact_created = True

    clients_sync_result = sync_clients()
    contacts_sync_result = sync_contacts()

    return {
        "status": "completed",
        "message": "Client/contact workflow completed through Harvest and synced to Airtable.",
        "client_created": client_created,
        "contact_created": contact_created,
        "harvest_client": harvest_client,
        "harvest_contact": harvest_contact,
        "clients_sync_result": clients_sync_result,
        "contacts_sync_result": contacts_sync_result,
    }

from app.models.requests import CreatePersonRequest
from app.services.sync_people import sync_people


def create_person_workflow(payload: CreatePersonRequest):
    existing_users = get_harvest_records("users", "users")
    incoming_email = payload.email.strip().lower()

    for user in existing_users:
        user_email = (user.get("email") or "").strip().lower()

        if user_email == incoming_email:
            return {
                "status": "duplicate_found",
                "message": "Person already exists in Harvest by email. No new user was created.",
                "harvest_user": user,
            }

    harvest_payload = {
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "email": payload.email,
        "telephone": payload.telephone or "",
        "is_contractor": payload.is_contractor,
        "is_active": payload.is_active,
    }

    if payload.default_hourly_rate is not None:
        harvest_payload["default_hourly_rate"] = payload.default_hourly_rate

    if payload.cost_rate is not None:
        harvest_payload["cost_rate"] = payload.cost_rate

    response = harvest_post("users", harvest_payload)

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    created_user = response.json()
    sync_result = sync_people()

    return {
        "status": "created",
        "message": "Person created in Harvest and synced to Airtable.",
        "harvest_user": created_user,
        "sync_result": sync_result,
    }

from app.models.requests import CreateProjectRequest
from app.services.sync_projects import sync_projects


def create_project_workflow(payload: CreateProjectRequest):
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

    existing_projects = get_harvest_records("projects", "projects")

    incoming_name = payload.name.strip().lower()
    incoming_code = (payload.code or "").strip().lower()

    for project in existing_projects:
        project_client_id = (project.get("client") or {}).get("id")
        project_name = (project.get("name") or "").strip().lower()
        project_code = (project.get("code") or "").strip().lower()

        same_client = project_client_id == harvest_client_id
        same_name = project_name == incoming_name
        same_code = incoming_code and project_code == incoming_code

        if same_client and (same_name or same_code):
            return {
                "status": "duplicate_found",
                "message": "Project already exists in Harvest for this client. No new project was created.",
                "harvest_project": project,
            }

    harvest_payload = {
        "client_id": harvest_client_id,
        "name": payload.name,
        "code": payload.code or "",
        "is_active": payload.is_active,
        "is_billable": payload.is_billable,
        "is_fixed_fee": payload.is_fixed_fee,
        "bill_by": payload.bill_by,
        "budget_is_monthly": payload.budget_is_monthly,
        "notes": payload.notes or "",
    }

    if payload.hourly_rate is not None:
        harvest_payload["hourly_rate"] = payload.hourly_rate

    if payload.budget is not None:
        harvest_payload["budget"] = payload.budget

    if payload.budget_by:
        harvest_payload["budget_by"] = payload.budget_by

    if payload.fee is not None:
        harvest_payload["fee"] = payload.fee

    response = harvest_post("projects", harvest_payload)

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    created_project = response.json()
    sync_result = sync_projects()

    return {
        "status": "created",
        "message": "Project created in Harvest and synced to Airtable.",
        "harvest_client": harvest_client,
        "harvest_project": created_project,
        "sync_result": sync_result,
    }
