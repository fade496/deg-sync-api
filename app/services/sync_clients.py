from app.clients.harvest import get_harvest_records
from app.clients.airtable import (
    find_airtable_record,
    create_airtable_record,
    update_airtable_record,
)


def sync_clients():
    clients = get_harvest_records("clients", "clients")

    created = 0
    updated = 0
    failed = []

    for client in clients:
        harvest_id = client.get("id")

        fields = {
            "Name": client.get("name"),
            "Harvest Client ID": harvest_id,
            "Is Active": client.get("is_active"),
            "Address": client.get("address") or "",
            "Currency": client.get("currency") or "",
        }

        try:
            existing = find_airtable_record(
                "Clients",
                f"{{Harvest Client ID}}={harvest_id}",
            )

            if existing:
                response = update_airtable_record("Clients", existing["id"], fields)
                action = "update"
            else:
                response = create_airtable_record("Clients", fields)
                action = "create"

            if response.status_code in [200, 201]:
                if action == "update":
                    updated += 1
                else:
                    created += 1
            else:
                failed.append({
                    "client": client.get("name"),
                    "action": action,
                    "status_code": response.status_code,
                    "response": response.text,
                })

        except Exception as exc:
            failed.append({
                "client": client.get("name"),
                "action": "exception",
                "response": str(exc),
            })

    return {
        "harvest_clients": len(clients),
        "created": created,
        "updated": updated,
        "failed": len(failed),
        "failed_examples": failed[:3],
    }
