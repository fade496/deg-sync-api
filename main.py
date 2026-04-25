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


@app.post("/sync/clients")
def sync_clients(x_api_key: str = Header(None)):
    check_key(x_api_key)

    url = "https://api.harvestapp.com/v2/clients"

    headers = {
        "Authorization": f"Bearer {HARVEST_TOKEN}",
        "Harvest-Account-ID": HARVEST_ACCOUNT_ID,
        "User-Agent": "DEG Sync API"
    }

    r = requests.get(url, headers=headers)
    data = r.json()

    return {"count": len(data.get("clients", []))}


@app.get("/test/airtable")
def test_airtable(x_api_key: str = Header(None)):
    check_key(x_api_key)

    if not AIRTABLE_TOKEN:
        raise HTTPException(status_code=500, detail="AIRTABLE_TOKEN is not set")

    if not AIRTABLE_BASE_ID:
        raise HTTPException(status_code=500, detail="AIRTABLE_BASE_ID is not set")

    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients"

    headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}"
    }

    r = requests.get(url, headers=headers)

    try:
        body = r.json()
    except Exception:
        body = {"raw_response": r.text}

    return {
        "status_code": r.status_code,
        "ok": r.ok,
        "airtable_records_returned": len(body.get("records", [])) if isinstance(body, dict) else None,
        "response": body
    }
