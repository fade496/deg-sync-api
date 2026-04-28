import json
import tempfile
from pathlib import Path

from fastapi import HTTPException

from app.models.lem_requests import LemGenerateRequest
from app.clients.airtable import get_airtable_records
from app.services.sync import sync_time_entries
from app.lem_engine import make_lem


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

        for r in records:
            fields = r.get("fields", {})

            writer.writerow({
                "Project Code": fields.get("Project Code", ""),
                "Name": fields.get("Person", ""),
                "Date": fields.get("Spent Date", ""),
                "Hours": fields.get("Hours", ""),
                "Task": fields.get("Task", ""),
                "Notes": fields.get("Notes", ""),
                "Employee Id": fields.get("Employee ID", ""),
            })


def build_airtable_json(projects, billing, people, path: Path):
    data = {
        "projects": [p["fields"] for p in projects],
        "project_billing": [b["fields"] for b in billing],
        "people": [p["fields"] for p in people],
    }

    path.write_text(json.dumps(data), encoding="utf-8")


def generate_lem(payload: LemGenerateRequest):
    try:
        # 1. Sync time entries
        if payload.force_sync_time_entries:
            sync_time_entries(payload.from_date, payload.to_date)

        # 2. Query Airtable
        time_entries = get_airtable_records(
            "Time Entries",
            params={
                "filterByFormula": f"AND(IS_AFTER({{Spent Date}}, '{payload.from_date}'), IS_BEFORE({{Spent Date}}, '{payload.to_date}'))"
            },
        )

        if not time_entries:
            raise HTTPException(status_code=400, detail="No time entries found for date range")

        projects = get_airtable_records("Projects LEM")
        billing = get_airtable_records("Project Billing LEM")
        people = get_airtable_records("People LEM")

        # 3. Temp working dir
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            timesheet_path = tmp / "staging_timesheet.csv"
            airtable_path = tmp / "airtable.json"
            output_dir = tmp / "output"
            output_dir.mkdir()

            # 4. Build inputs
            build_staging_timesheet(time_entries, timesheet_path)
            build_airtable_json(projects, billing, people, airtable_path)

            # 5. Run generator
            make_lem.main_cli(
                timesheet=str(timesheet_path),
                airtable_json=str(airtable_path),
                output_dir=str(output_dir),
            )

            # 6. Collect outputs
            files = []
            for f in output_dir.iterdir():
                files.append(f.name)

            return {
                "status": "completed",
                "from_date": payload.from_date,
                "to_date": payload.to_date,
                "file_count": len(files),
                "files": files,
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
