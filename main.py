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
        url = f"https
