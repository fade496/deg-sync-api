import requests

from app.clients.harvest import harvest_headers
from app.clients.airtable import get_airtable_records, create_airtable_record, update_airtable_record
from app.core.sync_log import utc_now_iso, write_sync_log
from app.services.maps import build_project_map, build_people_map, build_task_map


def sync_time_entries(from_date: str, to_date: str):
    started_at = utc_now_iso()

    entries = []
    page = 1

    while True:
        response = requests.get(
            "https://api.harvestapp.com/v2/time_entries",
            headers=harvest_headers(),
            params={
                "from": from_date,
                "to": to_date,
                "page": page,
                "per_page": 100,
            },
            timeout=30,
        )

        response.raise_for_status()
        data = response.json()

        entries.extend(data.get("time_entries", []))

        if not data.get("next_page"):
            break

        page = data.get("next_page")

    project_map = build_project_map()
    people_map = build_people_map()
    task_map = build_task_map()

    existing_time_entry_map = {}

    for record in get_airtable_records("Time Entries"):
        fields = record.get("fields", {})
        harvest_time_entry_id = fields.get("Harvest Time Entry ID")

        if harvest_time_entry_id is not None:
            existing_time_entry_map[str(harvest_time_entry_id)] = record["id"]

    created = 0
    updated = 0
    skipped_missing_links = 0
    failed = []

    for entry in entries:
        entry_id = entry.get("id")

        project_id = (entry.get("project") or {}).get("id")
        task_id = (entry.get("task") or {}).get("id")
        user_id = (entry.get("user") or {}).get("id")

        project_record_id = project_map.get(str(project_id))
        task_record_id = task_map.get(str(task_id))
        person_record_id = people_map.get(str(user_id))

        if not project_record_id or not task_record_id or not person_record_id:
            skipped_missing_links += 1
            continue

        spent_date = entry.get("spent_date")
        hours = entry.get("hours")

        project_name = (entry.get("project") or {}).get("name") or ""
        task_name = (entry.get("task") or {}).get("name") or ""
        user_name = (entry.get("user") or {}).get("name") or ""

        name = f"{spent_date} - {user_name} - {project_name} - {task_name}"

        fields = {
            "Name": name,
            "Harvest Time Entry ID": entry_id,
            "Project": [project_record_id],
            "Task": [task_record_id],
            "Person": [person_record_id],
            "Hours": hours,
            "Notes": entry.get("notes") or "",
            "Billable": entry.get("billable"),
            "Approved": entry.get("is_approved"),
            "Spent Date": spent_date,
        }

        try:
            existing_record_id = existing_time_entry_map.get(str(entry_id))

            if existing_record_id:
                response = update_airtable_record(
                    "Time Entries",
                    existing_record_id,
                    fields,
                )

                if response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append({
                        "entry": entry_id,
                        "action": "update",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

            else:
                response = create_airtable_record("Time Entries", fields)

                if response.status_code in [200, 201]:
                    created += 1

                    try:
                        existing_time_entry_map[str(entry_id)] = response.json()["id"]
                    except Exception:
                        pass

                else:
                    failed.append({
                        "entry": entry_id,
                        "action": "create",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

        except Exception as exc:
            failed.append({
                "entry": entry_id,
                "action": "exception",
                "response": str(exc),
            })

    skipped = skipped_missing_links
    status_value = "success" if len(failed) == 0 else "partial"

    result = {
        "from_date": from_date,
        "to_date": to_date,
        "harvest_time_entries": len(entries),
        "created": created,
        "updated": updated,
        "skipped_missing_links": skipped_missing_links,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }

    write_sync_log(
        sync_type="time-entries",
        started_at=started_at,
        status=status_value,
        created=created,
        updated=updated,
        skipped=skipped,
        failed=len(failed),
        details=result,
    )

    return result
