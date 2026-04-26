import os
import requests
from fastapi import FastAPI, Header, HTTPException

app = FastAPI()

API_KEY = os.getenv("API_KEY")
HARVEST_TOKEN = os.getenv("HARVEST_TOKEN")
HARVEST_ACCOUNT_ID = os.getenv("HARVEST_ACCOUNT_ID")
AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")


def check_key(x_api_key):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def harvest_headers():
    return {
        "Authorization": f"Bearer {HARVEST_TOKEN}",
        "Harvest-Account-ID": HARVEST_ACCOUNT_ID,
        "User-Agent": "DEG Sync API",
    }


def airtable_headers():
    return {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json",
    }


def get_harvest_records(endpoint, key):
    records = []
    page = 1

    while True:
        url = f"https://api.harvestapp.com/v2/{endpoint}"
        response = requests.get(
            url,
            headers=harvest_headers(),
            params={"page": page, "per_page": 100},
        )
        response.raise_for_status()

        data = response.json()
        records.extend(data.get(key, []))

        next_page = data.get("next_page")
        if not next_page:
            break

        page = next_page

    return records


def get_airtable_records(table_name):
    records = []
    offset = None

    while True:
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}"
        params = {}

        if offset:
            params["offset"] = offset

        response = requests.get(url, headers=airtable_headers(), params=params)
        response.raise_for_status()

        data = response.json()
        records.extend(data.get("records", []))

        offset = data.get("offset")
        if not offset:
            break

    return records


def find_airtable_record(table_name, formula):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}"

    response = requests.get(
        url,
        headers=airtable_headers(),
        params={"filterByFormula": formula},
    )

    response.raise_for_status()
    records = response.json().get("records", [])

    if records:
        return records[0]

    return None


def create_airtable_record(table_name, fields):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}"

    return requests.post(
        url,
        headers=airtable_headers(),
        json={"fields": fields},
    )


def update_airtable_record(table_name, record_id, fields):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}/{record_id}"

    return requests.patch(
        url,
        headers=airtable_headers(),
        json={"fields": fields},
    )


def build_client_map():
    client_map = {}

    for record in get_airtable_records("Clients"):
        fields = record.get("fields", {})
        harvest_client_id = fields.get("Harvest Client ID")

        if harvest_client_id is not None:
            client_map[str(harvest_client_id)] = record["id"]

    return client_map


def build_project_map(active_only=False):
    project_map = {}

    for record in get_airtable_records("Projects"):
        fields = record.get("fields", {})

        if active_only and fields.get("Is Active") is not True:
            continue

        harvest_project_id = fields.get("Harvest Project ID")

        if harvest_project_id is not None:
            project_map[str(harvest_project_id)] = record["id"]

    return project_map


def build_people_map(active_only=False):
    people_map = {}

    for record in get_airtable_records("People"):
        fields = record.get("fields", {})

        if active_only and fields.get("Is Active") is not True:
            continue

        harvest_user_id = fields.get("Harvest User ID")

        if harvest_user_id is not None:
            people_map[str(harvest_user_id)] = record["id"]

    return people_map


def map_project_billing_method(project):
    if project.get("is_fixed_fee"):
        return "Fixed fee"

    if not project.get("is_billable"):
        return "Non-billable"

    bill_by = project.get("bill_by")

    mapping = {
        "Project": "Project hourly rate",
        "Person": "Person hourly rate",
        "People": "Person hourly rate",
        "Task": "Task hourly rate",
        "Tasks": "Task hourly rate",
        "none": "Non-billable",
        "None": "Non-billable",
    }

    return mapping.get(bill_by)


@app.get("/")
def root():
    return {"message": "DEG Sync API running"}


@app.get("/test/airtable")
def test_airtable(x_api_key: str = Header(None)):
    check_key(x_api_key)

    records = get_airtable_records("Clients")

    return {
        "status_code": 200,
        "ok": True,
        "airtable_records_returned": len(records),
    }


@app.post("/sync/clients")
def sync_clients(x_api_key: str = Header(None)):
    check_key(x_api_key)

    clients = get_harvest_records("clients", "clients")

    created = 0
    updated = 0
    failed = []

    for client in clients:
        harvest_id = client.get("id")

        fields = {
            "Name": client.get("name"),
            "Harvest Client ID": harvest_id,
            "Is Active": client.get("is_active"),
            "Address": client.get("address") or "",
            "Currency": client.get("currency") or "",
        }

        try:
            existing = find_airtable_record(
                "Clients",
                f"{{Harvest Client ID}}={harvest_id}",
            )

            if existing:
                response = update_airtable_record("Clients", existing["id"], fields)

                if response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append(
                        {
                            "client": client.get("name"),
                            "action": "update",
                            "status_code": response.status_code,
                            "response": response.text,
                        }
                    )
            else:
                response = create_airtable_record("Clients", fields)

                if response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append(
                        {
                            "client": client.get("name"),
                            "action": "create",
                            "status_code": response.status_code,
                            "response": response.text,
                        }
                    )

        except Exception as e:
            failed.append(
                {
                    "client": client.get("name"),
                    "action": "exception",
                    "response": str(e),
                }
            )

    return {
        "harvest_clients": len(clients),
        "created": created,
        "updated": updated,
        "failed": len(failed),
        "failed_examples": failed[:3],
    }


@app.post("/sync/contacts")
def sync_contacts(x_api_key: str = Header(None)):
    check_key(x_api_key)

    contacts = get_harvest_records("contacts", "contacts")
    client_map = build_client_map()

    created = 0
    updated = 0
    skipped_missing_client = 0
    skipped_inactive = 0
    failed = []

    for contact in contacts:
        if contact.get("is_active") is False:
            skipped_inactive += 1
            continue

        harvest_contact_id = contact.get("id")
        harvest_client = contact.get("client") or {}
        harvest_client_id = harvest_client.get("id")

        linked_client_record_id = client_map.get(str(harvest_client_id))

        if not linked_client_record_id:
            skipped_missing_client += 1
            failed.append(
                {
                    "contact": f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip(),
                    "reason": "No matching Airtable client found",
                    "harvest_client_id": harvest_client_id,
                }
            )
            continue

        first_name = contact.get("first_name") or ""
        last_name = contact.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip()
        phone = contact.get("phone_office") or contact.get("phone_mobile") or ""

        fields = {
            "Full Name": full_name,
            "First Name": first_name,
            "Last Name": last_name,
            "Email": contact.get("email") or "",
            "Phone": phone,
            "Client": [linked_client_record_id],
            "Harvest Contact ID": str(harvest_contact_id),
        }

        try:
            existing = find_airtable_record(
                "Contacts",
                f"{{Harvest Contact ID}}='{harvest_contact_id}'",
            )

            if existing:
                response = update_airtable_record("Contacts", existing["id"], fields)

                if response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append(
                        {
                            "contact": full_name,
                            "action": "update",
                            "status_code": response.status_code,
                            "response": response.text,
                        }
                    )
            else:
                response = create_airtable_record("Contacts", fields)

                if response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append(
                        {
                            "contact": full_name,
                            "action": "create",
                            "status_code": response.status_code,
                            "response": response.text,
                        }
                    )

        except Exception as e:
            failed.append(
                {
                    "contact": full_name,
                    "action": "exception",
                    "response": str(e),
                }
            )

    return {
        "harvest_contacts": len(contacts),
        "created": created,
        "updated": updated,
        "skipped_missing_client": skipped_missing_client,
        "skipped_inactive": skipped_inactive,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }


@app.post("/sync/projects")
def sync_projects(x_api_key: str = Header(None)):
    check_key(x_api_key)

    projects = get_harvest_records("projects", "projects")
    client_map = build_client_map()

    created = 0
    updated = 0
    skipped_missing_client = 0
    failed = []

    for project in projects:
        harvest_project_id = project.get("id")
        harvest_client = project.get("client") or {}
        harvest_client_id = harvest_client.get("id")

        linked_client_record_id = client_map.get(str(harvest_client_id))

        if not linked_client_record_id:
            skipped_missing_client += 1
            failed.append(
                {
                    "project": project.get("name"),
                    "reason": "No matching Airtable client found",
                    "harvest_client_id": harvest_client_id,
                }
            )
            continue

        fields = {
            "Name": project.get("name"),
            "Harvest Project ID": harvest_project_id,
            "Client": [linked_client_record_id],
            "Code": project.get("code") or "",
            "Short Code": project.get("code") or "",
            "Is Active": project.get("is_active"),
            "Is Billable": project.get("is_billable"),
            "Is Fixed Fee": project.get("is_fixed_fee"),
            "Hourly Rate": project.get("hourly_rate"),
            "Budget": project.get("budget"),
            "Budget Is Monthly": project.get("budget_is_monthly"),
            "Fee": project.get("fee"),
            "Notes": project.get("notes") or "",
        }

        billing_method = map_project_billing_method(project)
        if billing_method:
            fields["Billing Method"] = billing_method

        try:
            existing = find_airtable_record(
                "Projects",
                f"{{Harvest Project ID}}={harvest_project_id}",
            )

            if existing:
                response = update_airtable_record("Projects", existing["id"], fields)

                if response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append(
                        {
                            "project": project.get("name"),
                            "action": "update",
                            "status_code": response.status_code,
                            "response": response.text,
                        }
                    )
            else:
                response = create_airtable_record("Projects", fields)

                if response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append(
                        {
                            "project": project.get("name"),
                            "action": "create",
                            "status_code": response.status_code,
                            "response": response.text,
                        }
                    )

        except Exception as e:
            failed.append(
                {
                    "project": project.get("name"),
                    "action": "exception",
                    "response": str(e),
                }
            )

    return {
        "harvest_projects": len(projects),
        "created": created,
        "updated": updated,
        "skipped_missing_client": skipped_missing_client,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }


@app.post("/sync/people")
def sync_people(x_api_key: str = Header(None)):
    check_key(x_api_key)

    users = get_harvest_records("users", "users")

    created = 0
    updated = 0
    skipped_inactive = 0
    failed = []

    for user in users:
        harvest_user_id = user.get("id")

        if user.get("is_active") is False:
            skipped_inactive += 1
            continue

        first_name = user.get("first_name") or ""
        last_name = user.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip()

        fields = {
            "Full Name": full_name,
            "First Name": first_name,
            "Last Name": last_name,
            "Email": user.get("email") or "",
            "Telephone": user.get("telephone") or "",
            "Harvest User ID": harvest_user_id,
            "Is Active": user.get("is_active"),
            "Is Contractor": user.get("is_contractor"),
            "Default Hourly Rate": user.get("default_hourly_rate"),
            "Cost Rate": user.get("cost_rate"),
        }

        try:
            existing = find_airtable_record(
                "People",
                f"{{Harvest User ID}}={harvest_user_id}",
            )

            if existing:
                response = update_airtable_record("People", existing["id"], fields)

                if response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append(
                        {
                            "user": full_name,
                            "action": "update",
                            "status_code": response.status_code,
                            "response": response.text,
                        }
                    )
            else:
                response = create_airtable_record("People", fields)

                if response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append(
                        {
                            "user": full_name,
                            "action": "create",
                            "status_code": response.status_code,
                            "response": response.text,
                        }
                    )

        except Exception as e:
            failed.append(
                {
                    "user": full_name,
                    "action": "exception",
                    "response": str(e),
                }
            )

    return {
        "harvest_users": len(users),
        "created": created,
        "updated": updated,
        "skipped_inactive": skipped_inactive,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }


@app.post("/sync/project-people")
def sync_project_people(x_api_key: str = Header(None)):
    check_key(x_api_key)

    assignments = get_harvest_records("user_assignments", "user_assignments")

    project_map = build_project_map(active_only=True)
    people_map = build_people_map(active_only=True)

    created = 0
    updated = 0
    skipped_missing_links = 0
    skipped_inactive_assignment = 0
    skipped_inactive_or_missing_project = 0
    skipped_inactive_or_missing_person = 0
    failed = []

    for assignment in assignments:
        assignment_id = assignment.get("id")

        if assignment.get("is_active") is False:
            skipped_inactive_assignment += 1
            continue

        harvest_project_id = (assignment.get("project") or {}).get("id")
        harvest_user_id = (assignment.get("user") or {}).get("id")

        project_record_id = project_map.get(str(harvest_project_id))
        person_record_id = people_map.get(str(harvest_user_id))

        if not project_record_id:
            skipped_inactive_or_missing_project += 1
            continue

        if not person_record_id:
            skipped_inactive_or_missing_person += 1
            continue

        if not project_record_id or not person_record_id:
            skipped_missing_links += 1
            continue

        user_name = (assignment.get("user") or {}).get("name") or ""
        project_name = (assignment.get("project") or {}).get("name") or ""
        name = f"{user_name} - {project_name}".strip(" -")

        fields = {
            "Name": name,
            "Project": [project_record_id],
            "Person": [person_record_id],
            "Harvest Assignment ID": assignment_id,
            "Is Active": assignment.get("is_active"),
            "Is Project Manager": assignment.get("is_project_manager"),
            "Use Default Rates": assignment.get("use_default_rates"),
            "Hourly Rate": assignment.get("hourly_rate"),
        }

        try:
            existing = find_airtable_record(
                "Project People",
                f"{{Harvest Assignment ID}}={assignment_id}",
            )

            if existing:
                response = update_airtable_record(
                    "Project People",
                    existing["id"],
                    fields,
                )

                if response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append(
                        {
                            "assignment": assignment_id,
                            "action": "update",
                            "status_code": response.status_code,
                            "response": response.text,
                        }
                    )
            else:
                response = create_airtable_record("Project People", fields)

                if response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append(
                        {
                            "assignment": assignment_id,
                            "action": "create",
                            "status_code": response.status_code,
                            "response": response.text,
                        }
                    )

        except Exception as e:
            failed.append(
                {
                    "assignment": assignment_id,
                    "action": "exception",
                    "response": str(e),
                }
            )

    return {
        "harvest_assignments": len(assignments),
        "created": created,
        "updated": updated,
        "skipped_inactive_assignment": skipped_inactive_assignment,
        "skipped_inactive_or_missing_project": skipped_inactive_or_missing_project,
        "skipped_inactive_or_missing_person": skipped_inactive_or_missing_person,
        "skipped_missing_links": skipped_missing_links,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }

@app.post("/sync/tasks")
def sync_tasks(x_api_key: str = Header(None)):
    check_key(x_api_key)

    tasks = get_harvest_records("tasks", "tasks")

    created = 0
    updated = 0
    failed = []

    for task in tasks:
        harvest_task_id = task.get("id")

        fields = {
            "Name": task.get("name"),
            "Harvest Task ID": harvest_task_id,
            "Is Active": task.get("is_active"),
            "Billable By Default": task.get("billable_by_default"),
            "Default Hourly Rate": task.get("default_hourly_rate"),
        }

        try:
            existing = find_airtable_record(
                "Tasks",
                f"{{Harvest Task ID}}={harvest_task_id}",
            )

            if existing:
                response = update_airtable_record("Tasks", existing["id"], fields)

                if response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append({
                        "task": task.get("name"),
                        "action": "update",
                        "status_code": response.status_code,
                        "response": response.text,
                    })
            else:
                response = create_airtable_record("Tasks", fields)

                if response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append({
                        "task": task.get("name"),
                        "action": "create",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

        except Exception as e:
            failed.append({
                "task": task.get("name"),
                "action": "exception",
                "response": str(e),
            })

    return {
        "harvest_tasks": len(tasks),
        "created": created,
        "updated": updated,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }

@app.post("/sync/project-tasks")
def sync_project_tasks(x_api_key: str = Header(None)):
    check_key(x_api_key)

    assignments = get_harvest_records("task_assignments", "task_assignments")

    project_map = build_project_map(active_only=True)
    task_map = {}

    # Build task map
    for record in get_airtable_records("Tasks"):
        fields = record.get("fields", {})
        harvest_task_id = fields.get("Harvest Task ID")

        if harvest_task_id is not None:
            task_map[str(harvest_task_id)] = record["id"]

    created = 0
    updated = 0
    skipped_inactive = 0
    skipped_missing_links = 0
    failed = []

    for assignment in assignments:
        assignment_id = assignment.get("id")

        if assignment.get("is_active") is False:
            skipped_inactive += 1
            continue

        harvest_project_id = (assignment.get("project") or {}).get("id")
        harvest_task_id = (assignment.get("task") or {}).get("id")

        project_record_id = project_map.get(str(harvest_project_id))
        task_record_id = task_map.get(str(harvest_task_id))

        if not project_record_id or not task_record_id:
            skipped_missing_links += 1
            continue

        project_name = (assignment.get("project") or {}).get("name") or ""
        task_name = (assignment.get("task") or {}).get("name") or ""
        name = f"{project_name} - {task_name}".strip(" -")

        fields = {
            "Name": name,
            "Project": [project_record_id],
            "Task": [task_record_id],
            "Harvest Task Assignment ID": assignment_id,
            "Is Active": assignment.get("is_active"),
            "Billable": assignment.get("billable"),
            "Hourly Rate": assignment.get("hourly_rate"),
        }

        try:
            existing = find_airtable_record(
                "Project Tasks",
                f"{{Harvest Task Assignment ID}}={assignment_id}",
            )

            if existing:
                response = update_airtable_record(
                    "Project Tasks",
                    existing["id"],
                    fields,
                )

                if response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append({
                        "assignment": assignment_id,
                        "action": "update",
                        "status_code": response.status_code,
                        "response": response.text,
                    })
            else:
                response = create_airtable_record("Project Tasks", fields)

                if response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append({
                        "assignment": assignment_id,
                        "action": "create",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

        except Exception as e:
            failed.append({
                "assignment": assignment_id,
                "action": "exception",
                "response": str(e),
            })

    return {
        "harvest_task_assignments": len(assignments),
        "created": created,
        "updated": updated,
        "skipped_inactive": skipped_inactive,
        "skipped_missing_links": skipped_missing_links,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }
