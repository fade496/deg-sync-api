import os
import csv
import tempfile
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

def airtable_headers():
    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing AIRTABLE_API_KEY")
    return {"Authorization": f"Bearer {api_key}"}


def airtable_list_records(table_id, formula=None):
    records = []
    offset = None

    while True:
        params = {"pageSize": 100}
        if formula:
            params["filterByFormula"] = formula
        if offset:
            params["offset"] = offset

        r = requests.get(
            f"{AIRTABLE_API_ROOT}/{table_id}",
            headers=airtable_headers(),
            params=params,
        )

        if r.status_code >= 400:
            raise HTTPException(status_code=500, detail=r.text)

        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")

        if not offset:
            break

    return records


def airtable_get_by_ids(table_id, ids):
    if not ids:
        return {}

    out = {}

    for i in range(0, len(ids), 20):
        chunk = ids[i:i + 20]

        formula = "OR(" + ",".join([f"RECORD_ID()='{x}'" for x in chunk]) + ")"

        recs = airtable_list_records(table_id, formula)

        for r in recs:
            out[r["id"]] = r["fields"]

    return out


# ----------------------------
# Core helpers
# ----------------------------

def first_link(v):
    return v[0] if isinstance(v, list) and v else None


def load_mapping():
    recs = airtable_list_records(TABLES["mapping"])

    mapping = []
    for r in recs:
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

    return airtable_list_records(TABLES["time_entries"], formula)


def hydrate(time_entries):
    p_ids, u_ids, t_ids = set(), set(), set()

    for r in time_entries:
        f = r["fields"]
        p_ids.add(first_link(f.get("Project")))
        u_ids.add(first_link(f.get("Person")))
        t_ids.add(first_link(f.get("Task")))

    return (
        airtable_get_by_ids(TABLES["projects"], list(p_ids)),
        airtable_get_by_ids(TABLES["people"], list(u_ids)),
        airtable_get_by_ids(TABLES["tasks"], list(t_ids)),
    )


# ----------------------------
# Mapping engine
# ----------------------------

def extract(row, m):
    if m["value"]:
        return m["value"]

    src = m["source"]
    fld = m["field"]

    if src == "Time Entries":
        return row["time"].get(fld)
    if src == "Projects":
        return row["project"].get(fld)
    if src == "People":
        return row["person"].get(fld)
    if src == "Tasks":
        return row["task"].get(fld)

    return None


# ----------------------------
# CSV Writer
# ----------------------------

def write_csv(rows):
    if not rows:
        return None

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")

    headers = list(rows[0].keys())

    with open(tmp.name, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    return tmp.name


# ----------------------------
# MAIN
# ----------------------------

def generate_lem(payload):
    mapping = load_mapping()
    time_entries = load_time_entries(payload.from_date, payload.to_date)

    projects, people, tasks = hydrate(time_entries)

    rows = []

    for r in time_entries:
        f = r["fields"]

        row = {
            "time": f,
            "project": projects.get(first_link(f.get("Project")), {}),
            "person": people.get(first_link(f.get("Person")), {}),
            "task": tasks.get(first_link(f.get("Task")), {}),
        }

        out = {}

        for m in mapping:
            if not m["lem_field"]:
                continue

            out[m["lem_field"]] = extract(row, m)

        rows.append(out)

    csv_path = write_csv(rows)

    return {
        "status": "csv_generated",
        "row_count": len(rows),
        "file_path": csv_path,
    }
