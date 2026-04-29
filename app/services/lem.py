import os
import csv
import re
import tempfile
import zipfile
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
    "contracts": "tblSOm11yRrU6gckp",
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


def safe_filename(value):
    text = str(value or "").strip()
    text = re.sub(r"[^\w.\- ]+", "", text)
    text = text.replace(" ", "_")
    return text or "LEM"


def format_workdate(value):
    if not value:
        return ""

    try:
        return datetime.fromisoformat(str(value)).strftime("%m/%d/%Y")
    except ValueError:
        return value


def format_lem_date_name(from_date, to_date):
    start = datetime.fromisoformat(from_date)
    end = datetime.fromisoformat(to_date)
    return f"{start:%m.%d}-{end:%d.%Y}"


def extract_wo(task_value, notes_value):
    text = f"{task_value or ''} {notes_value or ''}"
    match = re.search(r"WO[-\s:]?(\d+)", text, flags=re.IGNORECASE)
    return match.group(1) if match else ""


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


def load_contracts():
    return [record.get("fields", {}) for record in airtable_list_records(TABLES["contracts"])]


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


def find_contract_for_project(project, contracts):
    project_code = str(project.get("Code", "")).strip()
    project_name = str(project.get("Name", "")).strip()
    project_short_code = str(project.get("Short Code", "")).strip()

    for contract in contracts:
        contract_projects = str(contract.get("Projects", "")).strip()
        contract_code = str(contract.get("Contract", "")).strip()
        contract_short_code = str(contract.get("Short Code", "")).strip()

        if project_code and project_code in contract_projects:
            return contract

        if project_name and project_name in contract_projects:
            return contract

        if project_short_code and project_short_code == contract_short_code:
            return contract

        if project_code and project_code == contract_code:
            return contract

    return {}


def get_contract_key(contract):
    contract_number = clean_value(contract.get("Contract"))
    short_code = clean_value(contract.get("Short Code"))

    if contract_number:
        return f"contract::{contract_number}"

    if short_code:
        return f"short::{short_code}"

    return "contract::unmatched"


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

    if source in ("airtable - contracts", "contracts"):
        return row_context["contract"]

    return {}


def extract(row_context, mapping_row):
    source = (mapping_row.get("source") or "").strip()
    field = (mapping_row.get("field") or "").strip()
    value = mapping_row.get("value")

    if source.lower() == "constant":
        return clean_value(value)

    source_table = get_source_table(row_context, source)

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

    if source_table and field:
        return clean_value(source_table.get(field))

    return ""


def get_csv_preamble_name(from_date, to_date, contract):
    date_name = format_lem_date_name(from_date, to_date)
    short_code = clean_value(contract.get("Short Code"))

    if short_code:
        return f"{date_name}.{short_code}"

    return date_name


def write_contract_csv(rows, from_date, to_date, contract):
    if not rows:
        raise HTTPException(status_code=422, detail="No LEM rows were generated")

    headers = list(rows[0].keys())
    preamble_name = get_csv_preamble_name(from_date, to_date, contract)
    contract_number = clean_value(contract.get("Contract"))

    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".csv",
        mode="w",
        newline="",
        encoding="utf-8",
    )

    with temp_file:
        writer = csv.writer(temp_file)

        writer.writerow([
            "CNRLEMLINE",
            preamble_name,
            contract_number,
            "O",
        ])

        writer.writerow(headers)

        dict_writer = csv.DictWriter(temp_file, fieldnames=headers)
        dict_writer.writerows(rows)

    return temp_file.name


def write_zip(csv_files):
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    temp_zip.close()

    with zipfile.ZipFile(temp_zip.name, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for csv_file in csv_files:
            zip_file.write(csv_file["path"], arcname=csv_file["filename"])

    return temp_zip.name


def generate_lem(payload):
    mapping = load_mapping()
    time_entries = load_time_entries(payload.from_date, payload.to_date)
    contracts = load_contracts()
    projects, people, tasks = hydrate(time_entries)

    grouped_rows = {}

    for record in time_entries:
        fields = record.get("fields", {})

        project_id = first_link(fields.get("Project"))
        person_id = first_link(fields.get("Person"))
        task_id = first_link(fields.get("Task"))

        project = projects.get(project_id, {})
        person = people.get(person_id, {})
        task = tasks.get(task_id, {})
        contract = find_contract_for_project(project, contracts)

        contract_key = get_contract_key(contract)

        row_context = {
            "time": fields,
            "project": project,
            "person": person,
            "task": task,
            "contract": contract,
        }

        output_row = {}

        for mapping_row in mapping:
            lem_field = mapping_row.get("lem_field")

            if not lem_field:
                continue

            output_row[lem_field] = extract(row_context, mapping_row)

        if contract_key not in grouped_rows:
            grouped_rows[contract_key] = {
                "contract": contract,
                "rows": [],
            }

        grouped_rows[contract_key]["rows"].append(output_row)

    if not grouped_rows:
        raise HTTPException(status_code=422, detail="No LEM rows were generated")

    csv_files = []

    for group in grouped_rows.values():
        contract = group["contract"]
        rows = group["rows"]

        preamble_name = get_csv_preamble_name(payload.from_date, payload.to_date, contract)
        filename = f"{safe_filename(preamble_name)}.csv"

        csv_path = write_contract_csv(
            rows,
            payload.from_date,
            payload.to_date,
            contract,
        )

        csv_files.append({
            "path": csv_path,
            "filename": filename,
        })

    return write_zip(csv_files)
