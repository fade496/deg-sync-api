import csv
import io
import os
import re
import json
import zipfile
import tempfile
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel


router = APIRouter(prefix="/lem", tags=["LEM"])


# =============================================================================
# Airtable config
# =============================================================================

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "appoW4AxlO3Gkezr4")  # DEG base

if not AIRTABLE_API_KEY:
    raise RuntimeError("AIRTABLE_API_KEY environment variable is missing")


AIRTABLE_API_ROOT = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}"
AIRTABLE_HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json",
}


# =============================================================================
# Live Airtable table IDs
# =============================================================================

TABLES = {
    "time_entries": "tblHStBhBeiBKAyDi",
    "projects": "tblDSMSWBOtotSwEX",
    "people": "tblr5TZn5JPgcLPdd",
    "tasks": "tblrzzJqP5fNH2lOn",
}


# =============================================================================
# Live Airtable field IDs
# =============================================================================

TIME_ENTRY_FIELDS = {
    "name": "fldwt6DO7c2rs8ohA",
    "harvest_time_entry_id": "fldellt24tCiC4MRA",
    "project": "fldCIpUZ4uM60sxq1",
    "task": "fldMS1grGAfRBuqAo",
    "person": "fld5pP9ZJFtXXeVVF",
    "hours": "fldlJnV1ktFxwB8ot",
    "notes": "fldTxISXsRFkH3jui",
    "billable": "fldzkivctBgZVghaU",
    "approved": "fldIapQz7rsaQyehJ",
    "spent_date": "fldKOlADGAYQAmun6",
}

PROJECT_FIELDS = {
    "name": "fldYk2FrEDWF5NaTt",
    "harvest_project_id": "flddXsvMNyGyfe8LR",
    "billing_method": "fldboj721DBRTyADg",
    "invoice_type": "fld8Fuw1cmVHrRXnj",
    "hourly_rate": "fldvNpgsbnZkEix7C",
    "budget": "fldyQXvU5B4cE2eHv",
    "fee": "fldLvEoeOFyKmNtXJ",
    "notes": "fldEsHzETJNe08g9T",
    "contacts": "fldsdMxj0Us8s4Zrc",
    "project_people": "flduNrwQWqMbPteVO",
    "project_tasks": "fldq2MuESpvpnNLTE",
    "time_entries": "fldg3wHVkhRgPUyJP",
    "client": "fldPXvbCxZfnSOeq7",
    "code": "fldnRbmshIalaBhvy",
    "short_code": "fldljc47eDNJshZBr",
    "is_active": "fldugVub7iAFljpdT",
    "is_billable": "fldMMyrZXvkkde0BW",
    "is_fixed_fee": "fldN2FhsxzzgTbjT0",
}

PEOPLE_FIELDS = {
    "full_name": "fld6vLeRhkaSZnVvk",
    "harvest_user_id": "fld6v4HWMr1aMGBxt",
    "first_name": "flducyo4L6GRQcrvS",
    "last_name": "fld6h2E8hMK2DbUwn",
    "email": "fldOYWMWABP786uYz",
    "craft1": "fldnp0XZra4SJBHAq",
    "craft1_desc": "fldzKHhnOiTIse28F",
    "craft1_801": "fldjaJRQyEbSYftgE",
    "craft2": "fldUJXvnq1KsSRuWY",
    "craft2_desc": "fld4uW6fLyIn35ooa",
    "craft2_801": "fld3IClT7nsFcYmiD",
    "craft3": "fldXSJ54o8sICOq9D",
    "craft3_desc": "fldhb7oafUiCIkuyd",
    "craft3_801": "fldaLmBJpw5OoNEBC",
}

TASK_FIELDS = {
    "name": "fldW7NAZWN7cHlopF",
    "harvest_task_id": "fld8Z4K9uwJBDoreO",
}


# =============================================================================
# Request model
# =============================================================================

class LemGenerateRequest(BaseModel):
    from_date: str
    to_date: str
    approved_only: bool = False
    billable_only: bool = False


# =============================================================================
# Airtable helpers
# =============================================================================

def airtable_list_records(
    table_id: str,
    *,
    field_ids: Optional[List[str]] = None,
    formula: Optional[str] = None,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    offset = None

    while True:
        params: Dict[str, Any] = {"pageSize": page_size}

        if field_ids:
            params["fields[]"] = field_ids

        if formula:
            params["filterByFormula"] = formula

        if offset:
            params["offset"] = offset

        url = f"{AIRTABLE_API_ROOT}/{table_id}"
        response = requests.get(url, headers=AIRTABLE_HEADERS, params=params, timeout=60)

        if response.status_code >= 400:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Airtable read failed",
                    "table_id": table_id,
                    "status": response.status_code,
                    "body": response.text,
                },
            )

        payload = response.json()
        records.extend(payload.get("records", []))
        offset = payload.get("offset")

        if not offset:
            break

    return records


def airtable_get_records_by_ids(
    table_id: str,
    record_ids: Set[str],
    *,
    field_ids: Optional[List[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    if not record_ids:
        return {}

    output: Dict[str, Dict[str, Any]] = {}
    ids = list(record_ids)

    for i in range(0, len(ids), 20):
        chunk = ids[i:i + 20]
        formula = "OR(" + ",".join([f"RECORD_ID()='{rid}'" for rid in chunk]) + ")"
        records = airtable_list_records(table_id, field_ids=field_ids, formula=formula)

        for record in records:
            output[record["id"]] = record.get("fields", {})

    return output


def airtable_date_range_formula(
    date_field_id: str,
    from_date: str,
    to_date: str,
) -> str:
    return (
        "AND("
        f"IS_AFTER({{{date_field_id}}}, DATEADD('{from_date}', -1, 'days')), "
        f"IS_BEFORE({{{date_field_id}}}, DATEADD('{to_date}', 1, 'days'))"
        ")"
    )


# =============================================================================
# Normalization helpers
# =============================================================================

def first_link(value: Any) -> Optional[str]:
    if isinstance(value, list) and value:
        return value[0]
    return None


def select_name(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        return value.get("name")
    if isinstance(value, str):
        return value
    return None


def lookup_first(value: Any) -> Optional[Any]:
    if isinstance(value, list) and value:
        return value[0]
    return value


def clean_employee_id(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    match = re.search(r"\d+", text)
    return match.group(0) if match else text


def normalize_date(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    try:
        return datetime.fromisoformat(text).strftime("%Y-%m-%d")
    except ValueError:
        return text


def is_lem_project(project: Dict[str, Any]) -> bool:
    invoice_type = project.get("invoice_type")
    return str(invoice_type or "").strip().upper() == "LEM"


def craft_for_project(
    project: Dict[str, Any],
    person: Dict[str, Any],
) -> Dict[str, Any]:
    method = str(project.get("billing_method") or "").strip().lower()

    if "craft code 2" in method or "craft 2" in method:
        return {
            "craft_code": lookup_first(person.get("craft2_desc")),
            "rate": lookup_first(person.get("craft2_801")),
        }

    if "craft code 3" in method or "craft 3" in method:
        return {
            "craft_code": lookup_first(person.get("craft3_desc")),
            "rate": lookup_first(person.get("craft3_801")),
        }

    return {
        "craft_code": lookup_first(person.get("craft1_desc")),
        "rate": lookup_first(person.get("craft1_801")),
    }


def extract_work_order(task_name: str, notes: str) -> str:
    text = f"{task_name or ''} {notes or ''}"
    match = re.search(r"\bWO[-\s:]?(\d{5,12})\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


# =============================================================================
# Main staging builder
# =============================================================================

def fetch_time_entries(from_date: str, to_date: str) -> List[Dict[str, Any]]:
    formula = airtable_date_range_formula(
        TIME_ENTRY_FIELDS["spent_date"],
        from_date,
        to_date,
    )

    fields = [
        TIME_ENTRY_FIELDS["harvest_time_entry_id"],
        TIME_ENTRY_FIELDS["project"],
        TIME_ENTRY_FIELDS["task"],
        TIME_ENTRY_FIELDS["person"],
        TIME_ENTRY_FIELDS["hours"],
        TIME_ENTRY_FIELDS["notes"],
        TIME_ENTRY_FIELDS["billable"],
        TIME_ENTRY_FIELDS["approved"],
        TIME_ENTRY_FIELDS["spent_date"],
    ]

    return airtable_list_records(
        TABLES["time_entries"],
        field_ids=fields,
        formula=formula,
    )


def hydrate_linked_records(
    time_entries: List[Dict[str, Any]],
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    project_ids: Set[str] = set()
    person_ids: Set[str] = set()
    task_ids: Set[str] = set()

    for record in time_entries:
        fields = record.get("fields", {})

        project_id = first_link(fields.get(TIME_ENTRY_FIELDS["project"]))
        person_id = first_link(fields.get(TIME_ENTRY_FIELDS["person"]))
        task_id = first_link(fields.get(TIME_ENTRY_FIELDS["task"]))

        if project_id:
            project_ids.add(project_id)
        if person_id:
            person_ids.add(person_id)
        if task_id:
            task_ids.add(task_id)

    projects = airtable_get_records_by_ids(
        TABLES["projects"],
        project_ids,
        field_ids=list(PROJECT_FIELDS.values()),
    )

    people = airtable_get_records_by_ids(
        TABLES["people"],
        person_ids,
        field_ids=list(PEOPLE_FIELDS.values()),
    )

    tasks = airtable_get_records_by_ids(
        TABLES["tasks"],
        task_ids,
        field_ids=list(TASK_FIELDS.values()),
    )

    return projects, people, tasks


def normalize_project(fields: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": fields.get(PROJECT_FIELDS["name"]),
        "harvest_project_id": fields.get(PROJECT_FIELDS["harvest_project_id"]),
        "billing_method": select_name(fields.get(PROJECT_FIELDS["billing_method"])),
        "invoice_type": fields.get(PROJECT_FIELDS["invoice_type"]),
        "code": fields.get(PROJECT_FIELDS["code"]),
        "short_code": fields.get(PROJECT_FIELDS["short_code"]),
        "hourly_rate": fields.get(PROJECT_FIELDS["hourly_rate"]),
    }


def normalize_person(fields: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "full_name": fields.get(PEOPLE_FIELDS["full_name"]),
        "harvest_user_id": fields.get(PEOPLE_FIELDS["harvest_user_id"]),
        "first_name": fields.get(PEOPLE_FIELDS["first_name"]),
        "last_name": fields.get(PEOPLE_FIELDS["last_name"]),
        "craft1_desc": fields.get(PEOPLE_FIELDS["craft1_desc"]),
        "craft1_801": fields.get(PEOPLE_FIELDS["craft1_801"]),
        "craft2_desc": fields.get(PEOPLE_FIELDS["craft2_desc"]),
        "craft2_801": fields.get(PEOPLE_FIELDS["craft2_801"]),
        "craft3_desc": fields.get(PEOPLE_FIELDS["craft3_desc"]),
        "craft3_801": fields.get(PEOPLE_FIELDS["craft3_801"]),
    }


def normalize_task(fields: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": fields.get(TASK_FIELDS["name"]),
        "harvest_task_id": fields.get(TASK_FIELDS["harvest_task_id"]),
    }


def build_staging_timesheet(
    time_entries: List[Dict[str, Any]],
    *,
    approved_only: bool,
    billable_only: bool,
) -> tuple[List[Dict[str, Any]], List[str]]:
    projects_raw, people_raw, tasks_raw = hydrate_linked_records(time_entries)

    rows: List[Dict[str, Any]] = []
    errors: List[str] = []

    for record in time_entries:
        record_id = record.get("id")
        fields = record.get("fields", {})

        if approved_only and not fields.get(TIME_ENTRY_FIELDS["approved"]):
            continue

        if billable_only and not fields.get(TIME_ENTRY_FIELDS["billable"]):
            continue

        project_id = first_link(fields.get(TIME_ENTRY_FIELDS["project"]))
        person_id = first_link(fields.get(TIME_ENTRY_FIELDS["person"]))
        task_id = first_link(fields.get(TIME_ENTRY_FIELDS["task"]))

        hours = fields.get(TIME_ENTRY_FIELDS["hours"])
        spent_date = fields.get(TIME_ENTRY_FIELDS["spent_date"])
        notes = fields.get(TIME_ENTRY_FIELDS["notes"], "")

        if not project_id:
            errors.append(f"{record_id}: missing linked Project")
            continue

        if not person_id:
            errors.append(f"{record_id}: missing linked Person")
            continue

        if not spent_date:
            errors.append(f"{record_id}: missing Spent Date")
            continue

        if hours in (None, "", 0):
            errors.append(f"{record_id}: missing or zero Hours")
            continue

        project_raw = projects_raw.get(project_id)
        person_raw = people_raw.get(person_id)
        task_raw = tasks_raw.get(task_id, {}) if task_id else {}

        if not project_raw:
            errors.append(f"{record_id}: linked Project record not found: {project_id}")
            continue

        if not person_raw:
            errors.append(f"{record_id}: linked Person record not found: {person_id}")
            continue

        project = normalize_project(project_raw)
        person = normalize_person(person_raw)
        task = normalize_task(task_raw)

        if not is_lem_project(project):
            errors.append(
                f"{record_id}: skipped non-LEM project "
                f"{project.get('code') or project.get('name')}"
            )
            continue

        if not project.get("code"):
            errors.append(f"{record_id}: project missing Code")
            continue

        if not person.get("first_name") or not person.get("last_name"):
            errors.append(f"{record_id}: person missing First Name or Last Name")
            continue

        craft = craft_for_project(project, person)

        row = {
            "Project Code": project.get("code"),
            "Project Name": project.get("name"),
            "Employee Id": clean_employee_id(person.get("harvest_user_id")),
            "First Name": person.get("first_name"),
            "Last Name": person.get("last_name"),
            "Date": normalize_date(spent_date),
            "Hours": hours,
            "Task": task.get("name") or "",
            "Notes": notes or "",
            "Billing Method": project.get("billing_method") or "",
            "Short Code": project.get("short_code") or "",
            "Craft Code": craft.get("craft_code") or "",
            "Rate": craft.get("rate") or "",
            "Work Order": extract_work_order(task.get("name") or "", notes or ""),
        }

        rows.append(row)

    return rows, errors


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
            writer.writerow({key: row.get(key, "") for key in headers})


def write_debug_csv(rows: List[Dict[str, Any]], path: Path) -> None:
    if not rows:
        return

    headers = list(rows[0].keys())

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def write_airtable_json(rows: List[Dict[str, Any]], path: Path) -> None:
    """
    This JSON is intentionally staging-derived.

    If your existing make_lem.py expects a richer airtable.json, adjust this block
    to match that script's expected schema. The staging CSV is the critical piece
    that fixes the current 'No valid rows' failure.
    """
    projects: Dict[str, Dict[str, Any]] = {}
    people: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        project_code = row["Project Code"]
        person_key = f"{row['First Name']} {row['Last Name']}"

        projects[project_code] = {
            "Project Code": project_code,
            "Project": row.get("Project Name", ""),
            "Billing Type": "LEM",
            "Billing Method": row.get("Billing Method", ""),
            "Short Code": row.get("Short Code", ""),
            "Contracts": row.get("Short Code", ""),
            "Approver First Name": "",
            "Approver Last Name": "",
            "Approver Email": "",
        }

        people[person_key] = {
            "First Name": row["First Name"],
            "Last Name": row["Last Name"],
            "Craft Code 1": row.get("Craft Code", ""),
            "Craft Code 2": row.get("Craft Code", ""),
            "Craft Code 3": row.get("Craft Code", ""),
        }

    payload = {
        "projects": list(projects.values()),
        "project_billing": [
            {
                "Project Code": project_code,
                "Billing Method": data.get("Billing Method", "Craft Code 1"),
            }
            for project_code, data in projects.items()
        ],
        "people": list(people.values()),
    }

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def zip_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                zip_file.write(file_path, file_path.relative_to(source_dir))


def run_make_lem(
    staging_csv: Path,
    airtable_json: Path,
    output_dir: Path,
) -> None:
    """
    Runs existing make_lem.py if it exists.

    Expected location:
      ./scripts/make_lem.py

    You can change MAKE_LEM_SCRIPT_PATH in Cloud Run env if needed.
    """
    script_path = Path(os.getenv("MAKE_LEM_SCRIPT_PATH", "scripts/make_lem.py"))
    template_path = Path(os.getenv("LEM_TEMPLATE_PATH", "assets/report_template.xlsx"))

    if not script_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"make_lem.py not found at {script_path}",
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

    if template_path.exists():
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


# =============================================================================
# Endpoint
# =============================================================================

@router.post("/generate")
def generate_lem(request: LemGenerateRequest):
    try:
        datetime.fromisoformat(request.from_date)
        datetime.fromisoformat(request.to_date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="from_date and to_date must be YYYY-MM-DD",
        )

    work_dir = Path(tempfile.mkdtemp(prefix="lem_"))
    output_dir = work_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    staging_csv = work_dir / "staging_timesheet.csv"
    debug_csv = work_dir / "debug_enriched_rows.csv"
    airtable_json = work_dir / "airtable.json"
    errors_txt = output_dir / "errors.txt"
    zip_path = work_dir / f"LEM_{request.from_date}_to_{request.to_date}.zip"

    time_entries = fetch_time_entries(request.from_date, request.to_date)

    if not time_entries:
        raise HTTPException(
            status_code=404,
            detail=f"No Airtable time entries found from {request.from_date} to {request.to_date}",
        )

    rows, errors = build_staging_timesheet(
        time_entries,
        approved_only=request.approved_only,
        billable_only=request.billable_only,
    )

    if not rows:
        errors_txt.write_text("\n".join(errors), encoding="utf-8")
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No valid rows were produced from Airtable time entries",
                "time_entries_found": len(time_entries),
                "errors": errors[:100],
            },
        )

    write_staging_csv(rows, staging_csv)
    write_debug_csv(rows, debug_csv)
    write_airtable_json(rows, airtable_json)

    if errors:
        errors_txt.write_text("\n".join(errors), encoding="utf-8")

    run_make_lem(staging_csv, airtable_json, output_dir)

    # Include debug/input files in the zip for verification
    debug_dir = output_dir / "_debug"
    debug_dir.mkdir(exist_ok=True)
    debug_dir.joinpath("staging_timesheet.csv").write_text(
        staging_csv.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    debug_dir.joinpath("debug_enriched_rows.csv").write_text(
        debug_csv.read_text(encoding="utf-8") if debug_csv.exists() else "",
        encoding="utf-8",
    )
    debug_dir.joinpath("airtable.json").write_text(
        airtable_json.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    zip_directory(output_dir, zip_path)

    return FileResponse(
        path=zip_path,
        filename=zip_path.name,
        media_type="application/zip",
    )
