import csv
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import HTTPException


AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appoW4AxlO3Gkezr4")
AIRTABLE_API_ROOT = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"


TABLES = {
    "time_entries": "tblHStBhBeiBKAyDi",
    "projects": "tblDSMSWBOtotSwEX",
    "people": "tblr5TZn5JPgcLPdd",
    "tasks": "tblrzzJqP5fNH2lOn",
    "contracts": "tblSOm11yRrU6gckp",
}


MAKE_LEM_SCRIPT = os.getenv("MAKE_LEM_SCRIPT", "make_lem.py")
REPORT_TEMPLATE = os.getenv("REPORT_TEMPLATE", "report_template.xlsx")


def airtable_headers() -> Dict[str, str]:
    api_key = os.getenv("AIRTABLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing AIRTABLE_API_KEY")

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def airtable_list_records(table_id: str, formula: Optional[str] = None) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    offset: Optional[str] = None

    while True:
        params: Dict[str, Any] = {"pageSize": 100}

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


def airtable_get_by_ids(table_id: str, ids: List[str]) -> Dict[str, Dict[str, Any]]:
    ids = [record_id for record_id in ids if record_id]

    if not ids:
        return {}

    output: Dict[str, Dict[str, Any]] = {}

    for i in range(0, len(ids), 20):
        chunk = ids[i:i + 20]

        formula = "OR(" + ",".join(
            [f"RECORD_ID()='{record_id}'" for record_id in chunk]
        ) + ")"

        records = airtable_list_records(table_id, formula=formula)

        for record in records:
            output[record["id"]] = record.get("fields", {})

    return output


def first_link(value: Any) -> Optional[str]:
    if isinstance(value, list) and value:
        return value[0]
    return None


def clean_value(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return ""
        if len(value) == 1:
            return clean_value(value[0])
        return ", ".join(clean_value(v) for v in value)

    if isinstance(value, dict):
        return str(value.get("name") or value.get("id") or "")

    if value is None:
        return ""

    return str(value).strip()


def load_time_entries(from_date: str, to_date: str) -> List[Dict[str, Any]]:
    formula = (
        "AND("
        f"IS_AFTER({{Spent Date}}, DATEADD('{from_date}', -1, 'days')), "
        f"IS_BEFORE({{Spent Date}}, DATEADD('{to_date}', 1, 'days'))"
        ")"
    )

    return airtable_list_records(TABLES["time_entries"], formula=formula)


def load_contracts() -> List[Dict[str, Any]]:
    return [
        record.get("fields", {})
        for record in airtable_list_records(TABLES["contracts"])
    ]


def hydrate(time_entries: List[Dict[str, Any]]):
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


def find_contract_for_project(project: Dict[str, Any], contracts: List[Dict[str, Any]]) -> Dict[str, Any]:
    project_code = clean_value(project.get("Code"))
    project_name = clean_value(project.get("Name"))
    project_short_code = clean_value(project.get("Short Code"))

    for contract in contracts:
        contract_projects = clean_value(contract.get("Projects"))
        contract_number = clean_value(contract.get("Contract"))
        contract_short_code = clean_value(contract.get("Short Code"))

        if project_code and project_code in contract_projects:
            return contract

        if project_name and project_name in contract_projects:
            return contract

        if project_short_code and project_short_code == contract_short_code:
            return contract

        if project_code and project_code == contract_number:
            return contract

    return {}


def split_first_last_from_full_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split()

    if not parts:
        return "", ""

    if len(parts) == 1:
        return parts[0], ""

    return parts[0], " ".join(parts[1:])


def make_staging_timesheet(
    time_entries: List[Dict[str, Any]],
    projects: Dict[str, Dict[str, Any]],
    people: Dict[str, Dict[str, Any]],
    tasks: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for record in time_entries:
        fields = record.get("fields", {})

        project_id = first_link(fields.get("Project"))
        person_id = first_link(fields.get("Person"))
        task_id = first_link(fields.get("Task"))

        project = projects.get(project_id, {})
        person = people.get(person_id, {})
        task = tasks.get(task_id, {})

        first_name = clean_value(person.get("First Name"))
        last_name = clean_value(person.get("Last Name"))

        if not first_name and not last_name:
            first_name, last_name = split_first_last_from_full_name(
                clean_value(person.get("Full Name"))
            )

        rows.append({
            "Project Code": clean_value(project.get("Code")),
            "Employee Id": clean_value(person.get("Harvest User ID")),
            "First Name": first_name,
            "Last Name": last_name,
            "Date": clean_value(fields.get("Spent Date")),
            "Hours": clean_value(fields.get("Hours")),
            "Task": clean_value(task.get("Name")),
            "Notes": clean_value(fields.get("Notes")),
        })

    return rows


def make_airtable_json(
    time_entries: List[Dict[str, Any]],
    projects: Dict[str, Dict[str, Any]],
    people: Dict[str, Dict[str, Any]],
    contracts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    project_items: Dict[str, Dict[str, Any]] = {}
    project_billing_items: Dict[str, Dict[str, Any]] = {}
    people_items: Dict[str, Dict[str, Any]] = {}

    for record in time_entries:
        fields = record.get("fields", {})

        project_id = first_link(fields.get("Project"))
        person_id = first_link(fields.get("Person"))

        project = projects.get(project_id, {})
        person = people.get(person_id, {})
        contract = find_contract_for_project(project, contracts)

        project_code = clean_value(project.get("Code"))
        if project_code:
            approver_name = clean_value(project.get("Approver"))
            approver_first, approver_last = split_first_last_from_full_name(approver_name)

            project_items[project_code] = {
                "Project Code": project_code,
                "Project": clean_value(project.get("Name")),
                "Billing Type": clean_value(project.get("Billing Type") or project.get("Invoice Type") or "LEM"),
                "Approver First Name": approver_first,
                "Approver Last Name": approver_last,
                "Approver Email": clean_value(project.get("Email (from Approver)")),
                "Contracts": clean_value(contract.get("Contract")),
                "Short Code": clean_value(contract.get("Short Code") or project.get("Short Code")),
            }

            project_billing_items[project_code] = {
                "Project Code": project_code,
                "Billing Method": normalize_billing_method(
                    clean_value(project.get("Billing Method"))
                ),
            }

        first_name = clean_value(person.get("First Name"))
        last_name = clean_value(person.get("Last Name"))

        if not first_name and not last_name:
            first_name, last_name = split_first_last_from_full_name(
                clean_value(person.get("Full Name"))
            )

        person_key = f"{first_name} {last_name}".strip()

        if person_key:
            people_items[person_key] = {
                "First Name": first_name,
                "Last Name": last_name,
                "Craft Code 1": clean_value(
                    person.get("Description (from Craft1)")
                    or person.get("Craft1")
                ),
                "Craft Code 2": clean_value(
                    person.get("Description (from Craft2)")
                    or person.get("Craft2")
                ),
                "Craft Code 3": clean_value(
                    person.get("Description (from Craft3)")
                    or person.get("Craft3")
                ),
            }

    return {
        "projects": list(project_items.values()),
        "project_billing": list(project_billing_items.values()),
        "people": list(people_items.values()),
    }


def normalize_billing_method(value: str) -> str:
    text = value.strip().lower()

    if "craft code 2" in text or text == "craft 2":
        return "Craft 2"

    if "craft code 3" in text or text == "craft 3":
        return "Craft 3"

    return "Craft 1"


def write_staging_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    headers = [
        "Project Code",
        "Employee Id",
        "First Name",
        "Last Name",
        "Date",
        "Hours",
        "Task",
        "Notes",
    ]

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()

        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def write_airtable_json(payload: Dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def find_existing_path(candidates: List[str]) -> Optional[Path]:
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    return None


def run_make_lem(staging_csv: Path, airtable_json: Path, output_dir: Path) -> None:
    script_path = find_existing_path([
        MAKE_LEM_SCRIPT,
        "app/services/make_lem.py",
        "make_lem.py",
    ])

    if not script_path:
        raise HTTPException(
            status_code=500,
            detail="make_lem.py not found. Place it at repo root or app/services/make_lem.py",
        )

    command = [
        "python",
        str(script_path),
        "--timesheet",
        str(staging_csv),
        "--airtable-json",
        str(airtable_json),
        "--output-dir",
        str(output_dir),
    ]

    template_path = find_existing_path([
        REPORT_TEMPLATE,
        "report_template.xlsx",
        "app/services/report_template.xlsx",
    ])

    if template_path:
        command.extend(["--template", str(template_path)])

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "make_lem.py failed",
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
        )


def zip_output_dir(output_dir: Path) -> Path:
    zip_path = output_dir.parent / "lem_outputs.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for path in output_dir.rglob("*"):
            if path.is_file():
                zip_file.write(path, arcname=path.relative_to(output_dir))

    return zip_path


def generate_lem(payload):
    work_dir = Path(tempfile.mkdtemp(prefix="lem_"))
    output_dir = work_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    staging_csv = work_dir / "staging_timesheet.csv"
    airtable_json_path = work_dir / "airtable.json"

    time_entries = load_time_entries(payload.from_date, payload.to_date)

    if not time_entries:
        raise HTTPException(
            status_code=404,
            detail=f"No time entries found from {payload.from_date} to {payload.to_date}",
        )

    contracts = load_contracts()
    projects, people, tasks = hydrate(time_entries)

    staging_rows = make_staging_timesheet(time_entries, projects, people, tasks)
    airtable_payload = make_airtable_json(time_entries, projects, people, contracts)

    write_staging_csv(staging_rows, staging_csv)
    write_airtable_json(airtable_payload, airtable_json_path)

    run_make_lem(staging_csv, airtable_json_path, output_dir)

    return str(zip_output_dir(output_dir))
