import json
from datetime import datetime, timezone

from app.clients.airtable import create_airtable_record


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def write_sync_log(
    sync_type,
    started_at,
    status,
    created=0,
    updated=0,
    skipped=0,
    failed=0,
    details=None,
):
    finished_at = utc_now_iso()

    fields = {
        "Name": f"{sync_type} - {finished_at}",
        "Sync Type": sync_type,
        "Started At": started_at,
        "Finished At": finished_at,
        "Status": status,
        "Created": created,
        "Updated": updated,
        "Skipped": skipped,
        "Failed": failed,
        "Details": json.dumps(details or {}, default=str)[:95000],
    }

    try:
        response = create_airtable_record("Sync Log", fields)
        return response.status_code in [200, 201]
    except Exception:
        return False
