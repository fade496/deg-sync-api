import requests

from app.clients.harvest import harvest_headers
from app.clients.airtable import (
    get_airtable_records,
    create_airtable_record,
    update_airtable_record,
)
from app.core.sync_log import utc_now_iso, write_sync_log
from app.services.maps import build_client_map


def sync_invoices(from_date: str, to_date: str):
    started_at = utc_now_iso()

    invoices = []
    page = 1

    while True:
        response = requests.get(
            "https://api.harvestapp.com/v2/invoices",
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

        invoices.extend(data.get("invoices", []))

        if not data.get("next_page"):
            break

        page = data.get("next_page")

    client_map = build_client_map()

    existing_invoice_map = {}

    for record in get_airtable_records("Invoices"):
        fields = record.get("fields", {})
        harvest_invoice_id = fields.get("Harvest Invoice ID")

        if harvest_invoice_id is not None:
            existing_invoice_map[str(harvest_invoice_id)] = record["id"]

    created = 0
    updated = 0
    skipped_missing_client = 0
    failed = []

    for invoice in invoices:
        invoice_id = invoice.get("id")

        client_id = (invoice.get("client") or {}).get("id")
        client_record_id = client_map.get(str(client_id))

        if not client_record_id:
            skipped_missing_client += 1
            continue

        fields = {
            "Invoice Number": invoice.get("number"),
            "Harvest Invoice ID": invoice_id,
            "Client": [client_record_id],
            "Amount": invoice.get("amount"),
            "Due Amount": invoice.get("due_amount"),
            "Issue Date": invoice.get("issue_date"),
            "Due Date": invoice.get("due_date"),
            "State": invoice.get("state") or "",
        }

        try:
            existing_record_id = existing_invoice_map.get(str(invoice_id))

            if existing_record_id:
                response = update_airtable_record(
                    "Invoices",
                    existing_record_id,
                    fields,
                )

                if response.status_code in [200, 201]:
                    updated += 1
                else:
                    failed.append({
                        "invoice": invoice_id,
                        "action": "update",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

            else:
                response = create_airtable_record("Invoices", fields)

                if response.status_code in [200, 201]:
                    created += 1

                    try:
                        existing_invoice_map[str(invoice_id)] = response.json()["id"]
                    except Exception:
                        pass

                else:
                    failed.append({
                        "invoice": invoice_id,
                        "action": "create",
                        "status_code": response.status_code,
                        "response": response.text,
                    })

        except Exception as exc:
            failed.append({
                "invoice": invoice_id,
                "action": "exception",
                "response": str(exc),
            })

    skipped = skipped_missing_client
    status_value = "success" if len(failed) == 0 else "partial"

    result = {
        "from_date": from_date,
        "to_date": to_date,
        "harvest_invoices": len(invoices),
        "created": created,
        "updated": updated,
        "skipped_missing_client": skipped_missing_client,
        "failed": len(failed),
        "failed_examples": failed[:5],
    }

    write_sync_log(
        sync_type="invoices",
        started_at=started_at,
        status=status_value,
        created=created,
        updated=updated,
        skipped=skipped,
        failed=len(failed),
        details=result,
    )

    return result
