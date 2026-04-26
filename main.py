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


@app.get("/")
def root():
    return {"message": "DEG Sync API running"}


@app.get("/test/airtable")
def test_airtable(x_api_key: str = Header(None)):
    check_key(x_api_key)

    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients"
    r = requests.get(url, headers=airtable_headers())

    body = r.json()

    return {
        "status_code": r.status_code,
        "ok": r.ok,
        "airtable_records_returned": len(body.get("records", [])),
        "response": body,
    }


@app.post("/sync/clients")
def sync_clients(x_api_key: str = Header(None)):
    check_key(x_api_key)

    harvest_url = "https://api.harvestapp.com/v2/clients"
    harvest_response = requests.get(harvest_url, headers=harvest_headers())
    harvest_response.raise_for_status()

    clients = harvest_response.json().get("clients", [])

    airtable_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients"

    created = 0
    updated = 0
    failed = []

    for client in clients:
        harvest_id = client.get("id")

        payload = {
            "fields": {
                "Name": client.get("name"),
                "Harvest Client ID": harvest_id,
                "Is Active": client.get("is_active"),
                "Address": client.get("address") or "",
                "Currency": client.get("currency") or "",
            }
        }

        try:
            search_url = f"{airtable_url}?filterByFormula={{Harvest Client ID}}={harvest_id}"
            search_response = requests.get(search_url, headers=airtable_headers())
            search_response.raise_for_status()

            records = search_response.json().get("records", [])

            if records:
                record_id = records[0]["id"]
                update_url = f"{airtable_url}/{record_id}"

                update_response = requests.patch(
                    update_url,
                    headers=airtable_headers(),
                    json=payload,
                )

                if update_response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append({
                        "client": client.get("name"),
                        "action": "update",
                        "status_code": update_response.status_code,
                        "response": update_response.text,
                    })

            else:
                create_response = requests.post(
                    airtable_url,
                    headers=airtable_headers(),
                    json=payload,
                )

                if create_response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append({
                        "client": client.get("name"),
                        "action": "create",
                        "status_code": create_response.status_code,
                        "response": create_response.text,
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
def sync_contacts(x_api_key: str = Header(None)):
    check_key(x_api_key)

    # 1. Pull contacts from Harvest
    harvest_url = "https://api.harvestapp.com/v2/contacts"
    harvest_response = requests.get(harvest_url, headers=harvest_headers())
    harvest_response.raise_for_status()

    contacts = harvest_response.json().get("contacts", [])

    # 2. Load Airtable Clients so contacts can link to the right client
    clients_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients"
    clients_response = requests.get(clients_url, headers=airtable_headers())
    clients_response.raise_for_status()

    airtable_clients = clients_response.json().get("records", [])

    client_map = {}
    for record in airtable_clients:
        fields = record.get("fields", {})
        harvest_client_id = fields.get("Harvest Client ID")

        if harvest_client_id is not None:
            client_map[str(harvest_client_id)] = record["id"]

    # 3. Upsert contacts into Airtable
    contacts_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Contacts"

    created = 0
    updated = 0
    skipped = 0
    failed = []

    for contact in contacts:
        harvest_contact_id = contact.get("id")
        harvest_client = contact.get("client") or {}
        harvest_client_id = harvest_client.get("id")

        linked_client_record_id = client_map.get(str(harvest_client_id))

        if not linked_client_record_id:
            skipped += 1
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

        payload = {
            "fields": {
                "Full Name": full_name,
                "First Name": first_name,
                "Last Name": last_name,
                "Email": contact.get("email") or "",
                "Phone": phone,
                "Client": [linked_client_record_id],
                "Harvest Contact ID": harvest_contact_id,
            }
        }

        try:
            search_url = f"{contacts_url}?filterByFormula={{Harvest Contact ID}}={harvest_contact_id}"
            search_response = requests.get(search_url, headers=airtable_headers())
            search_response.raise_for_status()

            records = search_response.json().get("records", [])

            if records:
                record_id = records[0]["id"]
                update_url = f"{contacts_url}/{record_id}"

                update_response = requests.patch(
                    update_url,
                    headers=airtable_headers(),
                    json=payload,
                )

                if update_response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append({
                        "contact": full_name,
                        "action": "update",
                        "status_code": update_response.status_code,
                        "response": update_response.text,
                    })

            else:
                create_response = requests.post(
                    contacts_url,
                    headers=airtable_headers(),
                    json=payload,
                )

                if create_response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append({
                        "contact": full_name,
                        "action": "create",
                        "status_code": create_response.status_code,
                        "response": create_response.text,
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
        "skipped": skipped,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }
