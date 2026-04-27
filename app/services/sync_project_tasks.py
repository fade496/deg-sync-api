from app.clients.harvest import get_harvest_records
from app.clients.airtable import (
    find_airtable_record,
    create_airtable_record,
    update_airtable_record,
)
from app.services.maps import build_project_map, build_task_map


def sync_project_tasks():
    assignments = get_harvest_records("task_assignments", "task_assignments")

    project_map = build_project_map(active_only=True)
    task_map = build_task_map()

    created = 0
    updated = 0
    skipped_inactive = 0
    skipped_missing_links = 0
    failed = []

    for assignment in assignments:
        assignment_id = assignment.get("id")

        if assignment.get("is_active") is False:
            skipped_inactive += 1
            continue

        harvest_project_id = (assignment.get("project") or {}).get("id")
        harvest_task_id = (assignment.get("task") or {}).get("id")

        project_record_id = project_map.get(str(harvest_project_id))
        task_record_id = task_map.get(str(harvest_task_id))

        if not project_record_id or not task_record_id:
            skipped_missing_links += 1
            continue

        project_name = (assignment.get("project") or {}).get("name") or ""
        task_name = (assignment.get("task") or {}).get("name") or ""
        name = f"{project_name} - {task_name}".strip(" -")

        fields = {
            "Name": name,
            "Project": [project_record_id],
            "Task": [task_record_id],
            "Harvest Task Assignment ID": assignment_id,
            "Is Active": assignment.get("is_active"),
            "Billable": assignment.get("billable"),
            "Hourly Rate": assignment.get("hourly_rate"),
        }

        try:
            existing = find_airtable_record(
                "Project Tasks",
                f"{{Harvest Task Assignment ID}}={assignment_id}",
            )

            if existing:
                response = update_airtable_record(
                    "Project Tasks",
                    existing["id"],
                    fields,
                )
                action = "update"
            else:
                response = create_airtable_record("Project Tasks", fields)
                action = "create"

            if response.status_code in [200, 201]:
                if action == "update":
                    updated += 1
                else:
                    created += 1
            else:
                failed.append({
                    "assignment": assignment_id,
                    "action": action,
                    "status_code": response.status_code,
                    "response": response.text,
                })

        except Exception as exc:
            failed.append({
                "assignment": assignment_id,
                "action": "exception",
                "response": str(exc),
            })

    return {
        "harvest_task_assignments": len(assignments),
        "created": created,
        "updated": updated,
        "skipped_inactive": skipped_inactive,
        "skipped_missing_links": skipped_missing_links,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }
