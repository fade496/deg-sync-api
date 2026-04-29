import os
import requests
from typing import Any, Dict, List

AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appoW4AxlO3Gkezr4")


def airtable_headers():
    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key:
        raise Exception("Missing AIRTABLE_API_KEY")
    return {"Authorization": f"Bearer {api_key}"}


def airtable_list(table_id: str):
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_id}"
    records = []

    while url:
        res = requests.get(url, headers=airtable_headers())
        res.raise_for_status()
        data = res.json()

        records.extend(data.get("records", []))

        offset = data.get("offset")
        if offset:
            url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_id}?offset={offset}"
        else:
            url = None

    return records


# ================================
# TABLE IDs
# ================================

TABLES = {
    "mapping": "tblRFhOeKAkRcYP7x",
    "time_entries": "tblHStBhBeiBKAyDi",
    "projects": "tblDSMSWBOtotSwEX",
    "people": "tblr5TZn5JPgcLPdd",
    "tasks": "tblrzzJqP5fNH2lOn",
}


# ================================
# STEP 1: LOAD MAPPING
# ================================

def load_mapping():
    records = airtable_list(TABLES["mapping"])

    mapping = []

    for r in records:
        f = r["fields"]

        mapping.append({
            "index": f.get("Index", 999),
            "source": f.get("Source"),
            "field": f.get("Field"),
            "value": f.get("Value"),
            "lem_field": f.get("LEM Field"),
            "report_field": f.get("Report Field"),
        })

    return sorted(mapping, key=lambda x: x["index"])


# ================================
# STEP 2: LOAD TIME ENTRIES
# ================================

def load_time_entries():
    return airtable_list(TABLES["time_entries"])


# ================================
# STEP 3: DEBUG OUTPUT
# ================================

def generate_lem(payload):
    mapping = load_mapping()
    time_entries = load_time_entries()

    return {
        "status": "mapping_loaded",
        "mapping_count": len(mapping),
        "time_entries_count": len(time_entries),
        "mapping_preview": mapping[:5],
        "time_entries_preview": time_entries[:3],
    }
