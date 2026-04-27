import requests

from app.core.config import get_settings


def harvest_headers():
    settings = get_settings()

    return {
        "Authorization": f"Bearer {settings.harvest_token}",
        "Harvest-Account-ID": settings.harvest_account_id,
        "User-Agent": "DEG Sync API",
    }


def harvest_get(endpoint: str, params: dict | None = None):
    response = requests.get(
        f"https://api.harvestapp.com/v2/{endpoint}",
        headers=harvest_headers(),
        params=params or {},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def harvest_post(endpoint: str, payload: dict):
    return requests.post(
        f"https://api.harvestapp.com/v2/{endpoint}",
        headers=harvest_headers(),
        json=payload,
        timeout=30,
    )


def harvest_patch(endpoint: str, payload: dict):
    return requests.patch(
        f"https://api.harvestapp.com/v2/{endpoint}",
        headers=harvest_headers(),
        json=payload,
        timeout=30,
    )


def get_harvest_records(endpoint: str, key: str):
    records = []
    page = 1

    while True:
        data = harvest_get(
            endpoint,
            params={"page": page, "per_page": 100},
        )

        records.extend(data.get(key, []))

        if not data.get("next_page"):
            break

        page = data["next_page"]

    return records
