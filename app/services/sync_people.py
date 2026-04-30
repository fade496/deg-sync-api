from app.clients.harvest import get_harvest_records
from app.clients.airtable import (
    find_airtable_record,
    create_airtable_record,
    update_airtable_record,
)


def format_roles(roles):
    if not roles:
        return ""

    if isinstance(roles, list):
        formatted_roles = []

        for role in roles:
            if isinstance(role, dict):
                formatted_roles.append(
                    role.get("name")
                    or role.get("label")
                    or str(role)
                )
            else:
                formatted_roles.append(str(role))

        return ", ".join(formatted_roles)

    return str(roles)


def sync_people():
    users = get_harvest_records("users", "users")

    created = 0
    updated = 0
    skipped_inactive = 0
    failed = []

    for user in users:
        harvest_user_id = user.get("id")

        if user.get("is_active") is False:
            skipped_inactive += 1
            continue

        first_name = user.get("first_name") or ""
        last_name = user.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip()

        fields = {
            "Full Name": full_name,
            "First Name": first_name,
            "Last Name": last_name,
            "Email": user.get("email") or "",
            "Telephone": user.get("telephone") or "",
            "Harvest User ID": harvest_user_id,
            "Employee ID": user.get("employee_id") or "",
            "Harvest Roles": format_roles(user.get("roles")),
            "Is Active": user.get("is_active"),
            "Is Contractor": user.get("is_contractor"),
            "Default Hourly Rate": user.get("default_hourly_rate"),
            "Cost Rate": user.get("cost_rate"),
        }

        try:
            existing = find_airtable_record(
                "People",
                f"{{Harvest User ID}}={harvest_user_id}",
            )

            if existing:
                response = update_airtable_record("People", existing["id"], fields)
                action = "update"
            else:
                response = create_airtable_record("People", fields)
                action = "create"

            if response.status_code in [200, 201]:
                if action == "update":
                    updated += 1
                else:
                    created += 1
            else:
                failed.append({
                    "user": full_name,
                    "action": action,
                    "status_code": response.status_code,
                    "response": response.text,
                })

        except Exception as exc:
            failed.append({
                "user": full_name,
                "action": "exception",
                "response": str(exc),
            })

    return {
        "harvest_users": len(users),
        "created": created,
        "updated": updated,
        "skipped_inactive": skipped_inactive,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }
