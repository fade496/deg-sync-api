from app.clients.harvest import get_harvest_records
from app.clients.airtable import (
    find_airtable_record,
    create_airtable_record,
    update_airtable_record,
)
from app.services.maps import build_project_map, build_people_map


def sync_project_people():
    assignments = get_harvest_records("user_assignments", "user_assignments")

    project_map = build_project_map(active_only=True)
    people_map = build_people_map(active_only=True)

    created = 0
    updated = 0
    skipped_missing_links = 0
    skipped_inactive_assignment = 0
    skipped_inactive_or_missing_project = 0
    skipped_inactive_or_missing_person = 0
    failed = []

    for assignment in assignments:
        assignment_id = assignment.get("id")

        if assignment.get("is_active") is False:
            skipped_inactive_assignment += 1
            continue

        harvest_project_id = (assignment.get("project") or {}).get("id")
        harvest_user_id = (assignment.get("user") or {}).get("id")

        project_record_id = project_map.get(str(harvest_project_id))
        person_record_id = people_map.get(str(harvest_user_id))

        if not project_record_id:
            skipped_inactive_or_missing_project += 1
            continue

        if not person_record_id:
            skipped_inactive_or_missing_person += 1
            continue

        user_name = (assignment.get("user") or {}).get("name") or ""
        project_name = (assignment.get("project") or {}).get("name") or ""
        name = f"{user_name} - {project_name}".strip(" -")

        fields = {
            "Name": name,
            "Project": [project_record_id],
            "Person": [person_record_id],
            "Harvest Assignment ID": assignment_id,
            "Is Active": assignment.get("is_active"),
            "Is Project Manager": assignment.get("is_project_manager"),
            "Use Default Rates": assignment.get("use_default_rates"),
            "Hourly Rate": assignment.get("hourly_rate"),
        }

        try:
            existing = find_airtable_record(
                "Project People",
                f"{{Harvest Assignment ID}}={assignment_id}",
            )

            if existing:
                response = update_airtable_record(
                    "Project People",
                    existing["id"],
                    fields,
                )
                action = "update"
            else:
                response = create_airtable_record("Project People", fields)
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
        "harvest_assignments": len(assignments),
        "created": created,
        "updated": updated,
        "skipped_inactive_assignment": skipped_inactive_assignment,
        "skipped_inactive_or_missing_project": skipped_inactive_or_missing_project,
        "skipped_inactive_or_missing_person": skipped_inactive_or_missing_person,
        "skipped_missing_links": skipped_missing_links,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }
