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

    # 1. Pull clients from Harvest
    harvest_url = "https://api.harvestapp.com/v2/clients"

    harvest_headers = {
        "Authorization": f"Bearer {HARVEST_TOKEN}",
        "Harvest-Account-ID": HARVEST_ACCOUNT_ID,
        "User-Agent": "DEG Sync API",
    }

    harvest_response = requests.get(harvest_url, headers=harvest_headers)
    harvest_response.raise_for_status()

    clients = harvest_response.json().get("clients", [])

    # 2. Airtable setup
    airtable_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients"

    airtable_headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json",
    }

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
            # Search Airtable by Harvest Client ID
            search_url = (
                f"{airtable_url}"
                f"?filterByFormula={{Harvest Client ID}}={harvest_id}"
            )

            search_response = requests.get(
                search_url,
                headers=airtable_headers,
            )

            search_response.raise_for_status()
            records = search_response.json().get("records", [])

            if records:
                # Update existing record
                record_id = records[0]["id"]
                update_url = f"{airtable_url}/{record_id}"

                update_response = requests.patch(
                    update_url,
                    headers=airtable_headers,
                    json=payload,
                )

                if update_response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append(
                        {
                            "client": client.get("name"),
                            "action": "update",
                            "status_code": update_response.status_code,
                            "response": update_response.text,
                        }
                    )

            else:
                # Create new record
                create_response = requests.post(
                    airtable_url,
                    headers=airtable_headers,
                    json=payload,
                )

                if create_response.status_code in [200, 201]:
                    created += 1
                else:
                    failed.append(
                        {
                            "client": client.get("name"),
                            "action": "create",
                            "status_code": create_response.status_code,
                            "response": create_response.text,
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
