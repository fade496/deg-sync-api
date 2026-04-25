import os
import requests
from fastapi import FastAPI, Header, HTTPException

app = FastAPI()

API_KEY = os.getenv("API_KEY")
HARVEST_TOKEN = os.getenv("HARVEST_TOKEN")
HARVEST_ACCOUNT_ID = os.getenv("HARVEST_ACCOUNT_ID")


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
