from app.clients.harvest import get_harvest_records
from app.clients.airtable import (
    find_airtable_record,
    create_airtable_record,
    update_airtable_record,
)
from app.services.maps import build_client_map


def map_project_billing_method(project):
    if project.get("is_fixed_fee"):
        return "Fixed fee"

    if not project.get("is_billable"):
        return "Non-billable"

    bill_by = project.get("bill_by")

    mapping = {
        "Project": "Project hourly rate",
        "Person": "Person hourly rate",
        "People": "Person hourly rate",
        "Task": "Task hourly rate",
        "Tasks": "Task hourly rate",
        "none": "Non-billable",
        "None": "Non-billable",
    }

    return mapping.get(bill_by)


def sync_projects():
    projects = get_harvest_records("projects", "projects")
    client_map = build_client_map()

    created = 0
    updated = 0
    skipped_missing_client = 0
    failed = []

    for project in projects:
        harvest_project_id = project.get("id")
        harvest_client = project.get("client") or {}
        harvest_client_id = harvest_client.get("id")

        linked_client_record_id = client_map.get(str(harvest_client_id))

        if not linked_client_record_id:
            skipped_missing_client += 1
            failed.append({
                "project": project.get("name"),
                "reason": "No matching Airtable client found",
                "harvest_client_id": harvest_client_id,
            })
            continue

        fields = {
            "Name": project.get("name"),
            "Harvest Project ID": harvest_project_id,
            "Client": [linked_client_record_id],
            "Code": project.get("code") or "",
            "Short Code": project.get("code") or "",
            "Is Active": project.get("is_active"),
            "Is Billable": project.get("is_billable"),
            "Is Fixed Fee": project.get("is_fixed_fee"),
            "Hourly Rate": project.get("hourly_rate"),
            "Budget": project.get("budget"),
            "Budget Is Monthly": project.get("budget_is_monthly"),
            "Fee": project.get("fee"),
            "Notes": project.get("notes") or "",
        }

        billing_method = map_project_billing_method(project)
        if billing_method:
            fields["Billing Method"] = billing_method

        try:
            existing = find_airtable_record(
                "Projects",
                f"{{Harvest Project ID}}={harvest_project_id}",
            )

            if existing:
                response = update_airtable_record("Projects", existing["id"], fields)
                action = "update"
            else:
                response = create_airtable_record("Projects", fields)
                action = "create"

            if response.status_code in [200, 201]:
                if action == "update":
                    updated += 1
                else:
                    created += 1
            else:
                failed.append({
                    "project": project.get("name"),
                    "action": action,
                    "status_code": response.status_code,
                    "response": response.text,
                })

        except Exception as exc:
            failed.append({
                "project": project.get("name"),
                "action": "exception",
                "response": str(exc),
            })

    return {
        "harvest_projects": len(projects),
        "created": created,
        "updated": updated,
        "skipped_missing_client": skipped_missing_client,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }
