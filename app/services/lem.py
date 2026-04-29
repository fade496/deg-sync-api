import os
from typing import Any, Dict, List, Optional

import requests
from fastapi import HTTPException


AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appoW4AxlO3Gkezr4")
AIRTABLE_API_ROOT = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"


TABLES = {
    "mapping": "tblRFhOeKAkRcYP7x",
    "time_entries": "tblHStBhBeiBKAyDi",
    "projects": "tblDSMSWBOtotSwEX",
    "people": "tblr5TZn5JPgcLPdd",
    "tasks": "tblrzzJqP5fNH2lOn",
}


# ----------------------------
# Airtable helpers
# ----------------------------

def airtable_headers() -> Dict[str, str]:
    api_key = os.getenv("AIRTABLE_API_KEY")

    if not api_key:
        raise HTTPException(status_code=500, detail="Missing AIRTABLE_API_KEY")

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def airtable_list_records(
    table_id: str,
    *,
    formula: Optional[str] = None,
) -> List[Dict[str, Any]]:
    records = []
    offset = None

    while True:
        params = {"pageSize": 100}

        if formula:
            params["filterByFormula"] = formula

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
                detail=response.text,
            )

        data = response.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")

        if not offset:
            break

    return records


def airtable_get_by_ids(table_id: str, ids: List[str]):
    if not ids:
        return {}

    result = {}

    for i in range(0, len(ids), 20):
        chunk = ids[i:i + 20]

        formula = "OR(" + ",".join(
            [f"RECORD_ID()='{x}'" for x in chunk]
        ) + ")"

        records = airtable_list_records(table_id, formula=formula)

        for r in records:
            result[r["id"]] = r["fields"]

    return result


# ----------------------------
# Core helpers
# ----------------------------

def first_link(value):
    if isinstance(value, list) and value:
        return value[0]
    return None


def load_mapping():
    records = airtable_list_records(TABLES["mapping"])

    mapping = []

    for r in records:
        f = r["fields"]

        mapping.append({
            "index": f.get("Index", 9999),
            "source": f.get("Source"),
            "field": f.get("Field"),
            "value": f.get("Value"),
            "lem_field": f.get("LEM Field"),
        })

    return sorted(mapping, key=lambda x: x["index"])


def load_time_entries(from_date, to_date):
    formula = (
        "AND("
        f"IS_AFTER({{Spent Date}}, DATEADD('{from_date}', -1, 'days')), "
        f"IS_BEFORE({{Spent Date}}, DATEADD('{to_date}', 1, 'days'))"
        ")"
    )

    return airtable_list_records(TABLES["time_entries"], formula=formula)


def hydrate(time_entries):
    project_ids = set()
    person_ids = set()
    task_ids = set()

    for r in time_entries:
        f = r["fields"]

        project_ids.add(first_link(f.get("Project")))
        person_ids.add(first_link(f.get("Person")))
        task_ids.add(first_link(f.get("Task")))

    return (
        airtable_get_by_ids(TABLES["projects"], list(project_ids)),
        airtable_get_by_ids(TABLES["people"], list(person_ids)),
        airtable_get_by_ids(TABLES["tasks"], list(task_ids)),
    )


# ----------------------------
# Mapping engine
# ----------------------------

def extract_value(row, mapping_row):
    source = mapping_row["source"]
    field = mapping_row["field"]
    value = mapping_row["value"]

    if value:
        return value

    if source == "Time Entries":
        return row["time"].get(field)

    if source == "Projects":
        return row["project"].get(field)

    if source == "People":
        return row["person"].get(field)

    if source == "Tasks":
        return row["task"].get(field)

    return None


# ----------------------------
# MAIN
# ----------------------------

def generate_lem(payload):
    mapping = load_mapping()
    time_entries = load_time_entries(payload.from_date, payload.to_date)

    projects, people, tasks = hydrate(time_entries)

    lem_rows = []

    for r in time_entries:
        f = r["fields"]

        project_id = first_link(f.get("Project"))
        person_id = first_link(f.get("Person"))
        task_id = first_link(f.get("Task"))

        row = {
            "time": f,
            "project": projects.get(project_id, {}),
            "person": people.get(person_id, {}),
            "task": tasks.get(task_id, {}),
        }

        lem_row = {}

        for m in mapping:
            if not m["lem_field"]:
                continue

            val = extract_value(row, m)
            lem_row[m["lem_field"]] = val

        lem_rows.append(lem_row)

    return {
        "status": "lem_rows_built",
        "row_count": len(lem_rows),
        "sample": lem_rows[:5],
    }
