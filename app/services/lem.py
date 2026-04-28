import json
import shutil
import tempfile
from pathlib import Path

from fastapi import HTTPException

from app.clients.airtable import get_airtable_records
from app.models.lem_requests import LemGenerateRequest
from app.services.sync_time_entries import sync_time_entries
from app.lem_engine import make_lem


LEM_OUTPUT_ROOT = Path("/tmp/lem_outputs")


def airtable_value(value):
    if isinstance(value, list):
        if not value:
            return ""
        return value[0]
    if value is None:
        return ""
    return value


def build_staging_timesheet(records, path: Path):
    import csv

    headers = [
        "Project Code",
        "Name",
        "Date",
        "Hours",
        "Task",
        "Notes",
        "Employee Id",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()

        for record in records:
            fields = record.get("fields", {})

            writer.writerow({
                "Project Code": airtable_value(fields.get("Project Code")),
                "Name": airtable_value(fields.get("Person")),
                "Date": airtable_value(fields.get("Spent Date")),
                "Hours": airtable_value(fields.get("Hours")),
                "Task": airtable_value(fields.get("Task")),
                "Notes": airtable_value(fields.get("Notes")),
                "Employee Id": airtable_value(fields.get("Employee ID")),
            })


def build_airtable_json(projects, billing, people, path: Path):
    data = {
        "projects": [record.get("fields", {}) for record in projects],
        "project_billing": [record.get("fields", {}) for record in billing],
        "people": [record.get("fields", {}) for record in people],
    }

    path.write_text(json.dumps(data, default=str), encoding="utf-8")


def filter_time_entries_by_project_codes(records, project_codes):
    if not project_codes:
        return records

    wanted = {code.strip() for code in project_codes if code and code.strip()}

    return [
        record
        for record in records
        if str(airtable_value(record.get("fields", {}).get("Project Code"))).strip() in wanted
    ]


def generate_lem(payload: LemGenerateRequest):
    try:
        if payload.force_sync_time_entries:
            sync_time_entries(
                from_date=payload.from_date,
                to_date=payload.to_date,
            )

        filter_formula = (
            f"AND("
            f"IS_AFTER({{Spent Date}}, DATEADD('{payload.from_date}', -1, 'days')), "
            f"IS_BEFORE({{Spent Date}}, DATEADD('{payload.to_date}', 1, 'days'))"
            f")"
        )

        time_entries = get_airtable_records(
            "Time Entries",
            params={
                "filterByFormula": filter_formula,
            },
        )

        time_entries = filter_time_entries_by_project_codes(
            time_entries,
            payload.project_codes,
        )

        if not time_entries:
            raise HTTPException(
                status_code=400,
                detail="No time entries found for the selected date range.",
            )

        projects = get_airtable_records("Projects LEM")
        billing = get_airtable_records("Project Billing LEM")
        people = get_airtable_records("People LEM")

        run_id = f"{payload.from_date}_to_{payload.to_date}".replace("-", "")
        output_dir = LEM_OUTPUT_ROOT / run_id

        if output_dir.exists():
            shutil.rmtree(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            timesheet_path = tmp / "staging_timesheet.csv"
            airtable_path = tmp / "airtable.json"
            template_path = Path("app/lem_engine/assets/report_template.xlsx")

            build_staging_timesheet(time_entries, timesheet_path)
            build_airtable_json(projects, billing, people, airtable_path)

            make_lem.main_cli(
                timesheet=str(timesheet_path),
                airtable_json=str(airtable_path),
                output_dir=str(output_dir),
                template=str(template_path),
            )

        files = sorted([
            file.name
            for file in output_dir.iterdir()
            if file.is_file()
        ])

        return {
            "status": "completed",
            "from_date": payload.from_date,
            "to_date": payload.to_date,
            "project_codes": payload.project_codes or [],
            "time_entries": len(time_entries),
            "file_count": len(files),
            "output_path": str(output_dir),
            "files": files,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
