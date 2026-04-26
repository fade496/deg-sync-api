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


@app.get("/")
def root():
    return {"message": "DEG Sync API running"}


@app.get("/test/airtable")
def test_airtable(x_api_key: str = Header(None)):
    check_key(x_api_key)

    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients"
    headers = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}

    r = requests.get(url, headers=headers)

    try:
        body = r.json()
    except Exception:
        body = {"raw_response": r.text}

    return {
        "status_code": r.status_code,
        "ok": r.ok,
        "airtable_records_returned": len(body.get("records", [])) if isinstance(body, dict) else None,
        "response": body,
    }


@app.post("/sync/clients")
def sync_clients(x_api_key: str = Header(None)):
    check_key(x_api_key)

    harvest_url = "https://api.harvestapp.com/v2/clients"
    harvest_headers = {
        "Authorization": f"Bearer {HARVEST_TOKEN}",
        "Harvest-Account-ID": HARVEST_ACCOUNT_ID,
        "User-Agent": "DEG Sync API",
    }

    harvest_response = requests.get(harvest_url, headers=harvest_headers)
    harvest_response.raise_for_status()

    clients = harvest_response.json().get("clients", [])

    airtable_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients"
    airtable_headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json",
    }

    created = 0
    failed = []

    for client in clients:
        payload = {
            "fields": {
                "Name": client.get("name"),
                "Harvest Client ID": client.get("id"),
                "Is Active": client.get("is_active"),
                "Address": client.get("address") or "",
                "Currency": client.get("currency") or "",
            }
        }

        response = requests.post(
            airtable_url,
            headers=airtable_headers,
            json=payload,
        )

        if response.status_code in [200, 201]:
            created += 1
        else:
            failed.append(
                {
                    "client": client.get("name"),
                    "status_code": response.status_code,
                    "response": response.text,
                }
            )

    return {
        "harvest_clients": len(clients),
        "created_in_airtable": created,
        "failed": len(failed),
        "failed_examples": failed[:3],
    }
