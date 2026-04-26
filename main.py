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

    # -----------------------
    # 1. GET FROM HARVEST
    # -----------------------
    harvest_url = "https://api.harvestapp.com/v2/clients"

    harvest_headers = {
        "Authorization": f"Bearer {HARVEST_TOKEN}",
        "Harvest-Account-ID": HARVEST_ACCOUNT_ID,
        "User-Agent": "DEG Sync API"
    }

    r = requests.get(harvest_url, headers=harvest_headers)
    data = r.json()
    clients = data.get("clients", [])

    # -----------------------
    # 2. SEND TO AIRTABLE
    # -----------------------
    airtable_url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Clients"

    airtable_headers = {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json"
    }

    created = 0

    for client in clients:
        payload = {
            "fields": {
                "Name": client.get("name"),
                "Harvest ID": str(client.get("id"))
            }
        }

        res = requests.post(airtable_url, headers=airtable_headers, json=payload)

        if res.status_code == 200:
            created += 1

    return {
        "harvest_clients": len(clients),
        "created_in_airtable": created
    }
