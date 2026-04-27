from app.clients.harvest import get_harvest_records
from app.clients.airtable import find_airtable_record, create_airtable_record, update_airtable_record
from app.services.maps import build_client_map


def sync_contacts():
    contacts = get_harvest_records("contacts", "contacts")
    client_map = build_client_map()

    created = 0
    updated = 0
    skipped_missing_client = 0
    skipped_inactive = 0
    failed = []

    for contact in contacts:
        if contact.get("is_active") is False:
            skipped_inactive += 1
            continue

        harvest_contact_id = contact.get("id")
        harvest_client = contact.get("client") or {}
        harvest_client_id = harvest_client.get("id")

        linked_client_record_id = client_map.get(str(harvest_client_id))

        if not linked_client_record_id:
            skipped_missing_client += 1
            failed.append({
                "contact": f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip(),
                "reason": "No matching Airtable client found",
                "harvest_client_id": harvest_client_id,
            })
            continue

        first_name = contact.get("first_name") or ""
        last_name = contact.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip()
        phone = contact.get("phone_office") or contact.get("phone_mobile") or ""

        fields = {
            "Full Name": full_name,
            "First Name": first_name,
            "Last Name": last_name,
            "Email": contact.get("email") or "",
            "Phone": phone,
            "Client": [linked_client_record_id],
            "Harvest Contact ID": str(harvest_contact_id),
        }

        try:
            existing = find_airtable_record(
                "Contacts",
                f"{{Harvest Contact ID}}='{harvest_contact_id}'",
            )

            if existing:
                response = update_airtable_record("Contacts", existing["id"], fields)
                action = "update"
            else:
                response = create_airtable_record("Contacts", fields)
                action = "create"

            if response.status_code in [200, 201]:
                if action == "update":
                    updated += 1
                else:
                    created += 1
            else:
                failed.append({
                    "contact": full_name,
                    "action": action,
                    "status_code": response.status_code,
                    "response": response.text,
                })

        except Exception as exc:
            failed.append({
                "contact": full_name,
                "action": "exception",
                "response": str(exc),
            })

    return {
        "harvest_contacts": len(contacts),
        "created": created,
        "updated": updated,
        "skipped_missing_client": skipped_missing_client,
        "skipped_inactive": skipped_inactive,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }
