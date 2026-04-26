import os
import json
import requests
from urllib.parse import urlencode, parse_qs

from fastapi import Request
from fastapi.responses import RedirectResponse, JSONResponse

from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel
from jose import jwt
from jose.exceptions import JWTError

app = FastAPI()

API_KEY = os.getenv("API_KEY")
HARVEST_TOKEN = os.getenv("HARVEST_TOKEN")
HARVEST_ACCOUNT_ID = os.getenv("HARVEST_ACCOUNT_ID")
AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

MS_TENANT_ID = os.getenv("MS_TENANT_ID")
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET")
MS_ALLOWED_GROUP_ID = os.getenv("MS_ALLOWED_GROUP_ID")


# ============================================================
# Authentication
# ============================================================

def microsoft_openid_config():
    url = f"https://login.microsoftonline.com/{MS_TENANT_ID}/v2.0/.well-known/openid-configuration"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def microsoft_jwks():
    config = microsoft_openid_config()
    jwks_uri = config["jwks_uri"]

    response = requests.get(jwks_uri)
    response.raise_for_status()

    return response.json()


def verify_microsoft_token(authorization):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    token = authorization.split(" ", 1)[1]

    try:
        jwks = microsoft_jwks()
        unverified_header = jwt.get_unverified_header(token)

        key = None
        for jwk in jwks["keys"]:
            if jwk["kid"] == unverified_header["kid"]:
                key = jwk
                break

        if not key:
            raise HTTPException(status_code=401, detail="Microsoft signing key not found")

        valid_issuers = [
            f"https://login.microsoftonline.com/{MS_TENANT_ID}/v2.0",
            f"https://sts.windows.net/{MS_TENANT_ID}/"
        ]
        
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=f"api://{MS_CLIENT_ID}",
            issuer=valid_issuers,
        )

        if MS_ALLOWED_GROUP_ID:
            groups = claims.get("groups", [])

            if MS_ALLOWED_GROUP_ID not in groups:
                raise HTTPException(
                    status_code=403,
                    detail="User is not in the allowed Microsoft group",
                )

        return claims

    except JWTError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid Microsoft token: {str(e)}",
        )


def check_key(x_api_key=None, authorization=None):
    # Temporary legacy API key support
    if x_api_key and x_api_key == API_KEY:
        return {
            "auth_method": "api_key",
        }

    # Microsoft OAuth support
    if authorization:
        claims = verify_microsoft_token(authorization)

        return {
            "auth_method": "microsoft_oauth",
            "claims": claims,
        }

    raise HTTPException(status_code=401, detail="Unauthorized")


# ============================================================
# Headers / helpers
# ============================================================

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


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def write_sync_log(
    sync_type,
    started_at,
    status,
    created=0,
    updated=0,
    skipped=0,
    failed=0,
    details=None,
):
    finished_at = utc_now_iso()

    fields = {
        "Name": f"{sync_type} - {finished_at}",
        "Sync Type": sync_type,
        "Started At": started_at,
        "Finished At": finished_at,
        "Status": status,
        "Created": created,
        "Updated": updated,
        "Skipped": skipped,
        "Failed": failed,
        "Details": json.dumps(details or {}, default=str)[:95000],
    }

    try:
        response = create_airtable_record("Sync Log", fields)
        return response.status_code in [200, 201]
    except Exception:
        return False


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


def build_task_map():
    task_map = {}

    for record in get_airtable_records("Tasks"):
        fields = record.get("fields", {})
        harvest_task_id = fields.get("Harvest Task ID")

        if harvest_task_id is not None:
            task_map[str(harvest_task_id)] = record["id"]

    return task_map


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




# ============================================================
# OAuth proxy endpoints for ChatGPT Actions
# ============================================================

@app.get("/oauth/authorize")
def oauth_authorize(
    response_type: str = Query("code"),
    client_id: Optional[str] = Query(None),
    redirect_uri: str = Query(...),
    scope: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """
    ChatGPT calls this endpoint first.

    This endpoint redirects the browser to Microsoft Entra.
    Microsoft redirects back to ChatGPT's callback URL with the code.
    """

    if response_type != "code":
        raise HTTPException(
            status_code=400,
            detail="Only authorization code flow is supported.",
        )

    if not MS_TENANT_ID:
        raise HTTPException(status_code=500, detail="MS_TENANT_ID is not set")

    azure_client_id = MS_CLIENT_ID or client_id

    if not azure_client_id:
        raise HTTPException(status_code=500, detail="MS_CLIENT_ID is not set")

    # Use the requested ChatGPT scope if provided; otherwise default to the exposed API scope.
    requested_scope = scope or f"api://{azure_client_id}/access_as_admin"

    params = {
        "client_id": azure_client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": requested_scope,
    }

    if state:
        params["state"] = state

    microsoft_auth_url = (
        f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/authorize"
        f"?{urlencode(params)}"
    )

    return RedirectResponse(microsoft_auth_url)


@app.post("/oauth/token")
async def oauth_token(request: Request):
    """
    ChatGPT calls this endpoint after Microsoft returns an authorization code.

    This endpoint exchanges the code with Microsoft and returns the token payload
    in the format ChatGPT Actions expects.
    """

    body = await request.body()
    form = parse_qs(body.decode())

    def first(name, default=None):
        values = form.get(name)
        if not values:
            return default
        return values[0]

    code = first("code")
    redirect_uri = first("redirect_uri")
    grant_type = first("grant_type", "authorization_code")

    incoming_client_id = first("client_id")
    incoming_client_secret = first("client_secret")

    azure_client_id = MS_CLIENT_ID or incoming_client_id
    azure_client_secret = MS_CLIENT_SECRET or incoming_client_secret

    if grant_type != "authorization_code":
        raise HTTPException(
            status_code=400,
            detail="Only authorization_code grant_type is supported.",
        )

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    if not redirect_uri:
        raise HTTPException(status_code=400, detail="Missing redirect_uri")

    if not MS_TENANT_ID:
        raise HTTPException(status_code=500, detail="MS_TENANT_ID is not set")

    if not azure_client_id:
        raise HTTPException(status_code=500, detail="MS_CLIENT_ID is not set")

    if not azure_client_secret:
        raise HTTPException(status_code=500, detail="MS_CLIENT_SECRET is not set")

    token_url = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/token"

    data = {
        "client_id": azure_client_id,
        "client_secret": azure_client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }

    token_response = requests.post(
        token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if token_response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=token_response.status_code,
            detail=token_response.text,
        )

    token_data = token_response.json()

    result = {
        "access_token": token_data.get("access_token"),
        "token_type": token_data.get("token_type", "Bearer"),
        "expires_in": token_data.get("expires_in", 3600),
    }

    if token_data.get("refresh_token"):
        result["refresh_token"] = token_data["refresh_token"]

    if token_data.get("id_token"):
        result["id_token"] = token_data["id_token"]

    return JSONResponse(result)


# ============================================================
# Basic routes
# ============================================================

@app.get("/")
def root():
    return {"message": "DEG Sync API running"}


@app.get("/status")
def status(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    auth_info = check_key(
        x_api_key=x_api_key,
        authorization=authorization,
    )

    checks = {
        "api": True,
        "auth_method": auth_info.get("auth_method"),
        "harvest_token_set": bool(HARVEST_TOKEN),
        "harvest_account_id_set": bool(HARVEST_ACCOUNT_ID),
        "airtable_token_set": bool(AIRTABLE_TOKEN),
        "airtable_base_id_set": bool(AIRTABLE_BASE_ID),
        "microsoft_tenant_id_set": bool(MS_TENANT_ID),
        "microsoft_client_id_set": bool(MS_CLIENT_ID),
        "microsoft_allowed_group_id_set": bool(MS_ALLOWED_GROUP_ID),
    }

    harvest_ok = False
    airtable_ok = False

    try:
        response = requests.get(
            "https://api.harvestapp.com/v2/users/me",
            headers=harvest_headers(),
        )
        harvest_ok = response.status_code == 200
    except Exception:
        harvest_ok = False

    try:
        response = requests.get(
            f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients",
            headers=airtable_headers(),
            params={"pageSize": 1},
        )
        airtable_ok = response.status_code == 200
    except Exception:
        airtable_ok = False

    checks["harvest_connection_ok"] = harvest_ok
    checks["airtable_connection_ok"] = airtable_ok

    overall_status = "ok" if all(
        value for key, value in checks.items() if key != "auth_method"
    ) else "warning"

    return {
        "status": overall_status,
        "checks": checks,
    }


@app.get("/test/airtable")
def test_airtable(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

    records = get_airtable_records("Clients")

    return {
        "status_code": 200,
        "ok": True,
        "airtable_records_returned": len(records),
    }


# ============================================================
# Sync endpoints
# ============================================================

@app.post("/sync/clients")
def sync_clients(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

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
                    failed.append({
                        "client": client.get("name"),
                        "action": "update",
                        "status_code": response.status_code,
                        "response": response.text,
                    })
            else:
                response = create_airtable_record("Clients", fields)

                if response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append({
                        "client": client.get("name"),
                        "action": "create",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

        except Exception as e:
            failed.append({
                "client": client.get("name"),
                "action": "exception",
                "response": str(e),
            })

    return {
        "harvest_clients": len(clients),
        "created": created,
        "updated": updated,
        "failed": len(failed),
        "failed_examples": failed[:3],
    }


@app.post("/sync/contacts")
def sync_contacts(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

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
            failed.append({
                "contact": f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip(),
                "reason": "No matching Airtable client found",
                "harvest_client_id": harvest_client_id,
            })
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
                    failed.append({
                        "contact": full_name,
                        "action": "update",
                        "status_code": response.status_code,
                        "response": response.text,
                    })
            else:
                response = create_airtable_record("Contacts", fields)

                if response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append({
                        "contact": full_name,
                        "action": "create",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

        except Exception as e:
            failed.append({
                "contact": full_name,
                "action": "exception",
                "response": str(e),
            })

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
def sync_projects(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

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
            failed.append({
                "project": project.get("name"),
                "reason": "No matching Airtable client found",
                "harvest_client_id": harvest_client_id,
            })
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
                    failed.append({
                        "project": project.get("name"),
                        "action": "update",
                        "status_code": response.status_code,
                        "response": response.text,
                    })
            else:
                response = create_airtable_record("Projects", fields)

                if response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append({
                        "project": project.get("name"),
                        "action": "create",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

        except Exception as e:
            failed.append({
                "project": project.get("name"),
                "action": "exception",
                "response": str(e),
            })

    return {
        "harvest_projects": len(projects),
        "created": created,
        "updated": updated,
        "skipped_missing_client": skipped_missing_client,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }


@app.post("/sync/people")
def sync_people(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

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
                    failed.append({
                        "user": full_name,
                        "action": "update",
                        "status_code": response.status_code,
                        "response": response.text,
                    })
            else:
                response = create_airtable_record("People", fields)

                if response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append({
                        "user": full_name,
                        "action": "create",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

        except Exception as e:
            failed.append({
                "user": full_name,
                "action": "exception",
                "response": str(e),
            })

    return {
        "harvest_users": len(users),
        "created": created,
        "updated": updated,
        "skipped_inactive": skipped_inactive,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }


@app.post("/sync/project-people")
def sync_project_people(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

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
                    failed.append({
                        "assignment": assignment_id,
                        "action": "update",
                        "status_code": response.status_code,
                        "response": response.text,
                    })
            else:
                response = create_airtable_record("Project People", fields)

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
def sync_tasks(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

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
def sync_project_tasks(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

    assignments = get_harvest_records("task_assignments", "task_assignments")

    project_map = build_project_map(active_only=True)
    task_map = build_task_map()

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


@app.post("/sync/time-entries")
def sync_time_entries(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
    from_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    to_date: str = Query(..., description="End date in YYYY-MM-DD format"),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    started_at = utc_now_iso()

    entries = []
    page = 1

    while True:
        response = requests.get(
            "https://api.harvestapp.com/v2/time_entries",
            headers=harvest_headers(),
            params={
                "from": from_date,
                "to": to_date,
                "page": page,
                "per_page": 100,
            },
        )

        response.raise_for_status()
        data = response.json()

        entries.extend(data.get("time_entries", []))

        if not data.get("next_page"):
            break

        page = data.get("next_page")

    project_map = build_project_map()
    people_map = build_people_map()
    task_map = build_task_map()

    existing_time_entry_map = {}
    for record in get_airtable_records("Time Entries"):
        fields = record.get("fields", {})
        harvest_time_entry_id = fields.get("Harvest Time Entry ID")

        if harvest_time_entry_id is not None:
            existing_time_entry_map[str(harvest_time_entry_id)] = record["id"]

    created = 0
    updated = 0
    skipped_missing_links = 0
    failed = []

    for entry in entries:
        entry_id = entry.get("id")

        project_id = (entry.get("project") or {}).get("id")
        task_id = (entry.get("task") or {}).get("id")
        user_id = (entry.get("user") or {}).get("id")

        project_record_id = project_map.get(str(project_id))
        task_record_id = task_map.get(str(task_id))
        person_record_id = people_map.get(str(user_id))

        if not project_record_id or not task_record_id or not person_record_id:
            skipped_missing_links += 1
            continue

        spent_date = entry.get("spent_date")
        hours = entry.get("hours")

        project_name = (entry.get("project") or {}).get("name") or ""
        task_name = (entry.get("task") or {}).get("name") or ""
        user_name = (entry.get("user") or {}).get("name") or ""

        name = f"{spent_date} - {user_name} - {project_name} - {task_name}"

        fields = {
            "Name": name,
            "Harvest Time Entry ID": entry_id,
            "Project": [project_record_id],
            "Task": [task_record_id],
            "Person": [person_record_id],
            "Hours": hours,
            "Notes": entry.get("notes") or "",
            "Billable": entry.get("billable"),
            "Approved": entry.get("is_approved"),
            "Spent Date": spent_date,
        }

        try:
            existing_record_id = existing_time_entry_map.get(str(entry_id))

            if existing_record_id:
                response = update_airtable_record(
                    "Time Entries",
                    existing_record_id,
                    fields,
                )

                if response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append({
                        "entry": entry_id,
                        "action": "update",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

            else:
                response = create_airtable_record("Time Entries", fields)

                if response.status_code in [200, 201]:
                    created += 1

                    try:
                        existing_time_entry_map[str(entry_id)] = response.json()["id"]
                    except Exception:
                        pass

                else:
                    failed.append({
                        "entry": entry_id,
                        "action": "create",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

        except Exception as e:
            failed.append({
                "entry": entry_id,
                "action": "exception",
                "response": str(e),
            })

    skipped = skipped_missing_links
    status_value = "success" if len(failed) == 0 else "partial"

    result = {
        "from_date": from_date,
        "to_date": to_date,
        "harvest_time_entries": len(entries),
        "created": created,
        "updated": updated,
        "skipped_missing_links": skipped_missing_links,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }

    write_sync_log(
        sync_type="time-entries",
        started_at=started_at,
        status=status_value,
        created=created,
        updated=updated,
        skipped=skipped,
        failed=len(failed),
        details=result,
    )

    return result


@app.post("/sync/invoices")
def sync_invoices(
    x_api_key: str = Header(None),
    authorization: str = Header(None),
    from_date: str = Query(...),
    to_date: str = Query(...),
):
    check_key(x_api_key=x_api_key, authorization=authorization)
    started_at = utc_now_iso()

    invoices = []
    page = 1

    while True:
        response = requests.get(
            "https://api.harvestapp.com/v2/invoices",
            headers=harvest_headers(),
            params={
                "from": from_date,
                "to": to_date,
                "page": page,
                "per_page": 100,
            },
        )

        response.raise_for_status()
        data = response.json()

        invoices.extend(data.get("invoices", []))

        if not data.get("next_page"):
            break

        page = data.get("next_page")

    client_map = build_client_map()

    existing_invoice_map = {}
    for record in get_airtable_records("Invoices"):
        fields = record.get("fields", {})
        harvest_invoice_id = fields.get("Harvest Invoice ID")

        if harvest_invoice_id is not None:
            existing_invoice_map[str(harvest_invoice_id)] = record["id"]

    created = 0
    updated = 0
    skipped_missing_client = 0
    failed = []

    for invoice in invoices:
        invoice_id = invoice.get("id")

        client_id = (invoice.get("client") or {}).get("id")
        client_record_id = client_map.get(str(client_id))

        if not client_record_id:
            skipped_missing_client += 1
            continue

        fields = {
            "Invoice Number": invoice.get("number"),
            "Harvest Invoice ID": invoice_id,
            "Client": [client_record_id],
            "Amount": invoice.get("amount"),
            "Due Amount": invoice.get("due_amount"),
            "Issue Date": invoice.get("issue_date"),
            "Due Date": invoice.get("due_date"),
            "State": invoice.get("state") or "",
        }

        try:
            existing_record_id = existing_invoice_map.get(str(invoice_id))

            if existing_record_id:
                response = update_airtable_record(
                    "Invoices",
                    existing_record_id,
                    fields,
                )

                if response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append({
                        "invoice": invoice_id,
                        "action": "update",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

            else:
                response = create_airtable_record("Invoices", fields)

                if response.status_code in [200, 201]:
                    created += 1

                    try:
                        existing_invoice_map[str(invoice_id)] = response.json()["id"]
                    except Exception:
                        pass

                else:
                    failed.append({
                        "invoice": invoice_id,
                        "action": "create",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

        except Exception as e:
            failed.append({
                "invoice": invoice_id,
                "action": "exception",
                "response": str(e),
            })

    skipped = skipped_missing_client
    status_value = "success" if len(failed) == 0 else "partial"

    result = {
        "from_date": from_date,
        "to_date": to_date,
        "harvest_invoices": len(invoices),
        "created": created,
        "updated": updated,
        "skipped_missing_client": skipped_missing_client,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }

    write_sync_log(
        sync_type="invoices",
        started_at=started_at,
        status=status_value,
        created=created,
        updated=updated,
        skipped=skipped,
        failed=len(failed),
        details=result,
    )

    return result


# ============================================================
# Create endpoints
# ============================================================

class CreateClientRequest(BaseModel):
    name: str
    currency: str = "CAD"
    address: Optional[str] = ""
    is_active: bool = True


@app.post("/create/client")
def create_client(
    payload: CreateClientRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

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

    response = requests.post(
        "https://api.harvestapp.com/v2/clients",
        headers=harvest_headers(),
        json=harvest_payload,
    )

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    created_client = response.json()
    sync_result = sync_clients(x_api_key=x_api_key, authorization=authorization)

    return {
        "status": "created",
        "message": "Client created in Harvest and synced to Airtable.",
        "harvest_client": created_client,
        "sync_result": sync_result,
    }


class CreateContactRequest(BaseModel):
    client_name: Optional[str] = None
    harvest_client_id: Optional[int] = None
    first_name: str
    last_name: str
    email: Optional[str] = ""
    phone: Optional[str] = ""
    title: Optional[str] = ""


@app.post("/create/contact")
def create_contact(
    payload: CreateContactRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

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

    response = requests.post(
        "https://api.harvestapp.com/v2/contacts",
        headers=harvest_headers(),
        json=harvest_payload,
    )

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    created_contact = response.json()
    sync_result = sync_contacts(x_api_key=x_api_key, authorization=authorization)

    return {
        "status": "created",
        "message": "Contact created in Harvest and synced to Airtable.",
        "harvest_client": harvest_client,
        "harvest_contact": created_contact,
        "sync_result": sync_result,
    }


class CreateClientWithContactRequest(BaseModel):
    client_name: str
    currency: str = "CAD"
    address: Optional[str] = ""
    is_active: bool = True

    contact_first_name: str
    contact_last_name: str
    contact_email: Optional[str] = ""
    contact_phone: Optional[str] = ""
    contact_title: Optional[str] = ""


@app.post("/create/client-with-contact")
def create_client_with_contact(
    payload: CreateClientWithContactRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

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

        client_response = requests.post(
            "https://api.harvestapp.com/v2/clients",
            headers=harvest_headers(),
            json=harvest_client_payload,
        )

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

        contact_response = requests.post(
            "https://api.harvestapp.com/v2/contacts",
            headers=harvest_headers(),
            json=harvest_contact_payload,
        )

        if contact_response.status_code not in [200, 201]:
            raise HTTPException(
                status_code=contact_response.status_code,
                detail=contact_response.text,
            )

        harvest_contact = contact_response.json()
        contact_created = True

    clients_sync_result = sync_clients(x_api_key=x_api_key, authorization=authorization)
    contacts_sync_result = sync_contacts(x_api_key=x_api_key, authorization=authorization)

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


class CreatePersonRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    telephone: Optional[str] = ""
    is_contractor: bool = False
    is_active: bool = True
    default_hourly_rate: Optional[float] = None
    cost_rate: Optional[float] = None


@app.post("/create/person")
def create_person(
    payload: CreatePersonRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

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

    response = requests.post(
        "https://api.harvestapp.com/v2/users",
        headers=harvest_headers(),
        json=harvest_payload,
    )

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    created_user = response.json()
    sync_result = sync_people(x_api_key=x_api_key, authorization=authorization)

    return {
        "status": "created",
        "message": "Person created in Harvest and synced to Airtable.",
        "harvest_user": created_user,
        "sync_result": sync_result,
    }


class CreateProjectRequest(BaseModel):
    client_name: Optional[str] = None
    harvest_client_id: Optional[int] = None

    name: str
    code: Optional[str] = ""
    is_active: bool = True
    is_billable: bool = True
    is_fixed_fee: bool = False
    bill_by: Optional[str] = "Project"

    hourly_rate: Optional[float] = None
    budget: Optional[float] = None
    budget_by: Optional[str] = None
    budget_is_monthly: bool = False
    fee: Optional[float] = None
    notes: Optional[str] = ""


@app.post("/create/project")
def create_project(
    payload: CreateProjectRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    check_key(x_api_key=x_api_key, authorization=authorization)

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

    response = requests.post(
        "https://api.harvestapp.com/v2/projects",
        headers=harvest_headers(),
        json=harvest_payload,
    )

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text,
        )

    created_project = response.json()
    sync_result = sync_projects(x_api_key=x_api_key, authorization=authorization)

    return {
        "status": "created",
        "message": "Project created in Harvest and synced to Airtable.",
        "harvest_client": harvest_client,
        "harvest_project": created_project,
        "sync_result": sync_result,
    }
