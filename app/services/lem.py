import os
import csv
import re
import tempfile
from datetime import datetime
from typing import Any

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


def airtable_get_by_ids(table_id, ids):
    ids = [x for x in ids if x]
    if not ids:
        return {}

    output = {}

    for i in range(0, len(ids), 20):
        chunk = ids[i:i + 20]
        formula = "OR(" + ",".join(
            [f"RECORD_ID()='{record_id}'" for record_id in chunk]
        ) + ")"

        records = airtable_list_records(table_id, formula=formula)

        for record in records:
            output[record["id"]] = record.get("fields", {})

    return output


def first_link(value):
    if isinstance(value, list) and value:
        return value[0]
    return None


def clean_value(value: Any):
    if isinstance(value, list):
        if not value:
            return ""
        if len(value) == 1:
            return clean_value(value[0])
        return ", ".join(str(clean_value(v)) for v in value)

    if isinstance(value, dict):
        return value.get("name") or value.get("id") or str(value)

    if value is None:
        return ""

    return value


def format_workdate(value):
    if not value:
        return ""

    try:
        return datetime.fromisoformat(str(value)).strftime("%m/%d/%Y")
    except ValueError:
        return value


def extract_wo(task_value, notes_value):
    text = f"{task_value or ''} {notes_value or ''}"

    match = re.search(r"WO[-\s:]?(\d+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)

    return ""


def load_mapping():
    records = airtable_list_records(TABLES["mapping"])
    mapping = []

    for record in records:
        fields = record.get("fields", {})

        mapping.append({
            "index": fields.get("Index", 9999),
            "source": fields.get("Source", ""),
            "field": fields.get("Field", ""),
            "value": fields.get("Value", ""),
            "lem_field": fields.get("LEM Field", ""),
            "report_field": fields.get("Report Field", ""),
        })

    return sorted(mapping, key=lambda row: row["index"])


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

    for record in time_entries:
        fields = record.get("fields", {})

        project_ids.add(first_link(fields.get("Project")))
        person_ids.add(first_link(fields.get("Person")))
        task_ids.add(first_link(fields.get("Task")))

    projects = airtable_get_by_ids(TABLES["projects"], list(project_ids))
    people = airtable_get_by_ids(TABLES["people"], list(person_ids))
    tasks = airtable_get_by_ids(TABLES["tasks"], list(task_ids))

    return projects, people, tasks


def get_source_table(row_context, source):
    source = (source or "").strip().lower()

    if source == "constant":
        return None

    if source in ("airtable - time entries", "time entries"):
        return row_context["time"]

    if source in ("airtable - projects", "projects"):
        return row_context["project"]

    if source in ("airtable - people", "people"):
        return row_context["person"]

    if source in ("airtable - tasks", "tasks"):
        return row_context["task"]

    return {}


def extract(row_context, mapping_row):
    source = (mapping_row.get("source") or "").strip()
    field = (mapping_row.get("field") or "").strip()
    value = mapping_row.get("value")

    # Only rows marked constant use the literal Value column.
    if source.lower() == "constant":
        return clean_value(value)

    source_table = get_source_table(row_context, source)

    # Special mapping rules from your Mapping table.
    if field == "Spent Date":
        return format_workdate(row_context["time"].get("Spent Date"))

    if field == "Task/Notes":
        task_name = row_context["task"].get("Name")
        notes = row_context["time"].get("Notes")
        return extract_wo(task_name, notes)

    if field == "Task":
        return clean_value(row_context["task"].get("Name"))

    if field == "Person":
        return clean_value(row_context["person"].get("Full Name"))

    if field in ("Craft Code 1/Craft Code 2/Craft Code 3", "Craft"):
        return clean_value(
            row_context["person"].get("Description (from Craft1)")
            or row_context["person"].get("Craft1")
        )

    # Normal table-field lookup.
    if source_table and field:
        return clean_value(source_table.get(field))

    return ""


def write_csv(rows):
    if not rows:
        raise HTTPException(status_code=422, detail="No LEM rows were generated")

    headers = list(rows[0].keys())

    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".csv",
        mode="w",
        newline="",
        encoding="utf-8",
    )

    with temp_file:
        writer = csv.DictWriter(temp_file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    return temp_file.name


def generate_lem(payload):
    mapping = load_mapping()
    time_entries = load_time_entries(payload.from_date, payload.to_date)
    projects, people, tasks = hydrate(time_entries)

    rows = []

    for record in time_entries:
        fields = record.get("fields", {})

        project_id = first_link(fields.get("Project"))
        person_id = first_link(fields.get("Person"))
        task_id = first_link(fields.get("Task"))

        row_context = {
            "time": fields,
            "project": projects.get(project_id, {}),
            "person": people.get(person_id, {}),
            "task": tasks.get(task_id, {}),
        }

        output_row = {}

        for mapping_row in mapping:
            lem_field = mapping_row.get("lem_field")

            if not lem_field:
                continue

            output_row[lem_field] = extract(row_context, mapping_row)

        rows.append(output_row)

    return write_csv(rows)
