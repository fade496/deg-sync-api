import requests

from app.core.config import get_settings


def airtable_headers():
    settings = get_settings()

    return {
        "Authorization": f"Bearer {settings.airtable_token}",
        "Content-Type": "application/json",
    }


def airtable_url(table_name: str, record_id: str | None = None):
    settings = get_settings()

    base_url = f"https://api.airtable.com/v0/{settings.airtable_base_id}/{table_name}"

    if record_id:
        return f"{base_url}/{record_id}"

    return base_url


def get_airtable_records(table_name: str, params: dict | None = None):
    records = []
    offset = None

    while True:
        request_params = dict(params or {})

        if offset:
            request_params["offset"] = offset

        response = requests.get(
            airtable_url(table_name),
            headers=airtable_headers(),
            params=request_params,
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        records.extend(data.get("records", []))

        offset = data.get("offset")

        if not offset:
            break

    return records


def find_airtable_record(table_name: str, formula: str):
    records = get_airtable_records(
        table_name,
        params={"filterByFormula": formula},
    )

    if records:
        return records[0]

    return None


def create_airtable_record(table_name: str, fields: dict):
    return requests.post(
        airtable_url(table_name),
        headers=airtable_headers(),
        json={"fields": fields},
        timeout=30,
    )


def update_airtable_record(table_name: str, record_id: str, fields: dict):
    return requests.patch(
        airtable_url(table_name, record_id),
        headers=airtable_headers(),
        json={"fields": fields},
        timeout=30,
    )
