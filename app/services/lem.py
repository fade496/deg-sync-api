import os
from typing import Any, Dict, List, Optional

import requests
from fastapi import HTTPException


AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appoW4AxlO3Gkezr4")
AIRTABLE_API_ROOT = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"


TABLES = {
    "mapping": "tblRFhOeKAkRcYP7x",
    "time_entries": "tblHStBhBeiBKAyDi",
}


def airtable_headers() -> Dict[str, str]:
    api_key = os.getenv("AIRTABLE_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="Missing AIRTABLE_API_KEY",
        )

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def airtable_list_records(
    table_id: str,
    *,
    field_ids: Optional[List[str]] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    offset: Optional[str] = None

    while True:
        params: Dict[str, Any] = {"pageSize": page_size}

        if field_ids:
            params["fields[]"] = field_ids

        if offset:
            params["offset"] = offset

        response = requests.get(
            f"{AIRTABLE_API_ROOT}/{table_id}",
            headers=airtable_headers(),
            params=params,
            timeout=60,
        )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Airtable read failed",
                    "table_id": table_id,
                    "status_code": response.status_code,
                    "response": response.text,
                },
            )

        data = response.json()
        records.extend(data.get("records", []))

        offset = data.get("offset")
        if not offset:
            break

    return records


def load_mapping() -> List[Dict[str, Any]]:
    records = airtable_list_records(TABLES["mapping"])

    mapping: List[Dict[str, Any]] = []

    for record in records:
        fields = record.get("fields", {})

        mapping.append({
            "record_id": record.get("id"),
            "index": fields.get("Index", 9999),
            "source": fields.get("Source", ""),
            "field": fields.get("Field", ""),
            "value": fields.get("Value", ""),
            "lem_field": fields.get("LEM Field", ""),
            "report_field": fields.get("Report Field", ""),
        })

    return sorted(mapping, key=lambda row: row["index"])


def load_time_entries() -> List[Dict[str, Any]]:
    return airtable_list_records(TABLES["time_entries"])


def generate_lem(payload):
    mapping = load_mapping()
    time_entries = load_time_entries()

    return {
        "status": "mapping_and_time_entries_loaded",
        "from_date": payload.from_date,
        "to_date": payload.to_date,
        "mapping_count": len(mapping),
        "time_entries_count": len(time_entries),
        "mapping_preview": mapping[:5],
        "time_entries_preview": time_entries[:3],
    }
