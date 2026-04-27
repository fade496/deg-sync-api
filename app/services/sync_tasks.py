from app.clients.harvest import get_harvest_records
from app.clients.airtable import (
    find_airtable_record,
    create_airtable_record,
    update_airtable_record,
)


def sync_tasks():
    tasks = get_harvest_records("tasks", "tasks")

    created = 0
    updated = 0
    failed = []

    for task in tasks:
        harvest_task_id = task.get("id")

        fields = {
            "Name": task.get("name"),
            "Harvest Task ID": harvest_task_id,
            "Is Active": task.get("is_active"),
            "Billable By Default": task.get("billable_by_default"),
            "Default Hourly Rate": task.get("default_hourly_rate"),
        }

        try:
            existing = find_airtable_record(
                "Tasks",
                f"{{Harvest Task ID}}={harvest_task_id}",
            )

            if existing:
                response = update_airtable_record("Tasks", existing["id"], fields)
                action = "update"
            else:
                response = create_airtable_record("Tasks", fields)
                action = "create"

            if response.status_code in [200, 201]:
                if action == "update":
                    updated += 1
                else:
                    created += 1
            else:
                failed.append({
                    "task": task.get("name"),
                    "action": action,
                    "status_code": response.status_code,
                    "response": response.text,
                })

        except Exception as exc:
            failed.append({
                "task": task.get("name"),
                "action": "exception",
                "response": str(exc),
            })

    return {
        "harvest_tasks": len(tasks),
        "created": created,
        "updated": updated,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }
